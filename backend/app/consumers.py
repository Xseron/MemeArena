import asyncio
import logging

from asgiref.sync import sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.layers import get_channel_layer
from django.utils import timezone

from . import game
from .models import GameRoom, Round

log = logging.getLogger(__name__)

GROUP_NAME = 'game'

def _serialize_state() -> dict:
    room = game.get_room()
    players = [{'id': u.id, 'username': u.username} for u in room.players.all()]
    current = room.rounds.first()  # ordering=['-number']
    current_dto = None
    if current is not None:
        current_dto = {
            'number': current.number,
            'phase': current.phase,
            'phase_deadline': current.phase_deadline.isoformat(),
        }
    return {
        'type': 'state',
        'payload': {
            'room': {'status': room.status},
            'players': players,
            'current_round': current_dto,
        },
    }


async def broadcast_state() -> None:
    snapshot = await sync_to_async(_serialize_state)()
    layer = get_channel_layer()
    await layer.group_send(GROUP_NAME, {'type': 'state.event', 'payload': snapshot})


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
            await sync_to_async(game.start_game)(room)

        room = await sync_to_async(game.get_room)()
        if room.status == GameRoom.STATUS_PLAYING:
            GameConsumer._ensure_phase_loop()

        await broadcast_state()

    async def disconnect(self, code):
        await self.channel_layer.group_discard(GROUP_NAME, self.channel_name)

    async def state_event(self, event):
        await self.send_json(event['payload'])

    @classmethod
    def _ensure_phase_loop(cls):
        if cls._phase_task is None or cls._phase_task.done():
            cls._phase_task = asyncio.create_task(cls._phase_loop())

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
                current = await sync_to_async(lambda: room.rounds.first())()
                if current is None:
                    return
                delay = (current.phase_deadline - timezone.now()).total_seconds()
                await asyncio.sleep(max(0, delay))
                await sync_to_async(game.advance_phase)(current)
                await broadcast_state()
        except Exception:
            log.exception('phase loop crashed')
            raise
