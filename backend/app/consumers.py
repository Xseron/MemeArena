import asyncio
import logging

from asgiref.sync import sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.layers import get_channel_layer
from django.utils import timezone

from . import game
from .models import GameRoom, Round, Submission

log = logging.getLogger(__name__)

GROUP_NAME = 'game'


def _serialize_state(user) -> dict:
    room = game.get_room()
    player_rows = list(room.players.all())
    in_game = any(p.pk == user.pk for p in player_rows)
    current = game.active_round(room)

    def score_for(u):
        return Round.objects.filter(room=room, winner__player=u).count()

    players = [{'id': u.id, 'username': u.username, 'score': score_for(u)} for u in player_rows]

    current_round = None
    if current is not None:
        all_subs = list(current.submissions.select_related('meme_card').all())
        you_submitted = any(s.player_id == user.pk for s in all_subs) if in_game else False

        your_hand = []
        if in_game and current.phase != Round.PHASE_DONE:
            hand_qs = room.hand_cards.filter(player=user).select_related('meme_card')
            for pc in hand_qs:
                your_hand.append({
                    'id': pc.id,
                    'meme_card': _meme_card_dto(pc.meme_card),
                })

        voted_qs = current.votes.filter(voter=user) if in_game else []
        you_voted = bool(list(voted_qs))

        if current.phase == Round.PHASE_SUBMITTING:
            submissions_out = []
        elif current.phase == Round.PHASE_VOTING:
            submissions_out = [
                {'id': s.id, 'meme_card': _meme_card_dto(s.meme_card), 'player_id': None}
                for s in all_subs if s.player_id != user.pk
            ]
        else:
            submissions_out = [
                {'id': s.id, 'meme_card': _meme_card_dto(s.meme_card), 'player_id': s.player_id}
                for s in all_subs
            ]

        if current.phase in (Round.PHASE_RESULTS, Round.PHASE_DONE):
            vote_counts = {s.id: s.votes.count() for s in all_subs}
        else:
            vote_counts = {}

        current_round = {
            'number': current.number,
            'phase': current.phase,
            'phase_deadline': current.phase_deadline.isoformat(),
            'situation': current.situation.text if current.situation else '',
            'you_submitted': you_submitted,
            'you_voted': you_voted,
            'your_hand': your_hand,
            'submissions': submissions_out,
            'winner_submission_id': current.winner_id,
            'vote_counts': vote_counts,
        }

    final_scores = None
    round_summaries = None
    if room.status == GameRoom.STATUS_FINISHED:
        rows = [
            {'player_id': u.id, 'score': Round.objects.filter(room=room, winner__player=u).count()}
            for u in player_rows
        ]
        rows.sort(key=lambda r: -r['score'])
        final_scores = rows

        round_summaries = []
        finished_rounds = (
            room.rounds
            .select_related('situation', 'winner__meme_card', 'winner__player')
            .order_by('number')
        )
        for r in finished_rounds:
            win_sub = r.winner
            summary = {
                'round_number': r.number,
                'situation': r.situation.text if r.situation else '',
                'winner': None,
            }
            if win_sub is not None:
                summary['winner'] = {
                    'user_id': win_sub.player_id,
                    'username': win_sub.player.username,
                    'meme_card': _meme_card_dto(win_sub.meme_card),
                    'votes': win_sub.votes.count(),
                }
            round_summaries.append(summary)

    return {
        'type': 'state',
        'payload': {
            'room': {'status': room.status},
            'you_id': user.id,
            'players': players,
            'current_round': current_round,
            'final_scores': final_scores,
            'round_summaries': round_summaries,
        },
    }


def _meme_card_dto(mc):
    return {
        'id': mc.id,
        'title': mc.title,
        'image_url': mc.image_url,
        'caption': mc.caption,
    }


async def broadcast_state() -> None:
    layer = get_channel_layer()
    await layer.group_send(GROUP_NAME, {'type': 'state.event'})


async def trigger_phase_restart() -> None:
    layer = get_channel_layer()
    await layer.group_send(GROUP_NAME, {'type': 'phase.trigger', 'action': 'restart'})


async def trigger_phase_cancel() -> None:
    layer = get_channel_layer()
    await layer.group_send(GROUP_NAME, {'type': 'phase.trigger', 'action': 'cancel'})


class GameConsumer(AsyncJsonWebsocketConsumer):
    _phase_task: asyncio.Task | None = None

    async def connect(self):
        if self.scope['user'].is_anonymous:
            await self.close(code=4401)
            return

        await self.channel_layer.group_add(GROUP_NAME, self.channel_name)
        await self.accept()

        room = await sync_to_async(game.get_room)()
        added = await sync_to_async(game.add_player)(room, self.scope['user'])

        if added and await sync_to_async(lambda: room.players.count())() == 4:
            try:
                await sync_to_async(game.start_game)(room)
            except ValueError as e:
                await sync_to_async(room.players.remove)(self.scope['user'])
                await self.send_json({'type': 'error', 'payload': {'code': str(e)}})
                await broadcast_state()
                await self.close(code=4422)
                return

        room = await sync_to_async(game.get_room)()
        if room.status == GameRoom.STATUS_PLAYING:
            GameConsumer._ensure_phase_loop()

        await broadcast_state()

    async def disconnect(self, code):
        await self.channel_layer.group_discard(GROUP_NAME, self.channel_name)
        user = self.scope.get('user')
        if user is None or user.is_anonymous:
            return
        room = await sync_to_async(game.get_room)()
        removed = await sync_to_async(game.remove_player_from_waiting)(room, user)
        if removed:
            await broadcast_state()

    async def state_event(self, event):
        snapshot = await sync_to_async(_serialize_state)(self.scope['user'])
        await self.send_json(snapshot)

    async def phase_trigger(self, event):
        if event.get('action') == 'cancel':
            GameConsumer.cancel_phase_loop()
        else:
            GameConsumer.restart_phase_loop()

    @classmethod
    def _ensure_phase_loop(cls):
        if cls._phase_task is None or cls._phase_task.done():
            cls._phase_task = asyncio.create_task(cls._phase_loop())

    @classmethod
    def restart_phase_loop(cls):
        if cls._phase_task is not None and not cls._phase_task.done():
            cls._phase_task.cancel()
        cls._phase_task = None
        cls._ensure_phase_loop()

    @classmethod
    def cancel_phase_loop(cls):
        if cls._phase_task is not None and not cls._phase_task.done():
            cls._phase_task.cancel()
        cls._phase_task = None

    @classmethod
    async def _phase_loop(cls):
        try:
            while True:
                room = await sync_to_async(game.get_room)()
                if room.status != GameRoom.STATUS_PLAYING:
                    await asyncio.sleep(game.RESET_DELAY_SECONDS)
                    await sync_to_async(game.reset_game)(room)
                    await broadcast_state()
                    return
                current = await sync_to_async(game.active_round)(room)
                if current is None:
                    return
                delay = (current.phase_deadline - timezone.now()).total_seconds()
                await asyncio.sleep(max(0, delay))
                await sync_to_async(game.advance_phase)(current)
                await broadcast_state()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception('phase loop crashed')
            raise
