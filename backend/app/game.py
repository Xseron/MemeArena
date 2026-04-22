import random
from datetime import timedelta

from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from .models import GameRoom, MemeCard, PlayerCard, Round, Situation, Submission, Vote

SUBMITTING_SECONDS = 30
VOTING_SECONDS = 20
RESULTS_SECONDS = 5
TOTAL_ROUNDS = 8
RESET_DELAY_SECONDS = 10
HAND_SIZE = 5


def get_room() -> GameRoom:
    return GameRoom.objects.get(pk=1)


def active_round(room: GameRoom):
    threshold = timezone.now() + timedelta(hours=1)
    return (
        room.rounds
        .exclude(phase=Round.PHASE_DONE)
        .filter(phase_deadline__lt=threshold)
        .order_by('number')
        .first()
    )


def add_player(room: GameRoom, user) -> bool:
    with transaction.atomic():
        locked = GameRoom.objects.select_for_update().get(pk=room.pk)
        if locked.status != GameRoom.STATUS_WAITING:
            return False
        if locked.players.filter(pk=user.pk).exists():
            return False
        if locked.players.count() >= 4:
            return False
        locked.players.add(user)
        return True


def pick_situations_for_game(room: GameRoom) -> list[Situation]:
    situations = list(Situation.objects.order_by('?')[:TOTAL_ROUNDS])
    if len(situations) < TOTAL_ROUNDS:
        raise ValueError('not_enough_situations')
    return situations


def draw_card(room: GameRoom, player) -> PlayerCard:
    meme_card = MemeCard.objects.order_by('?').first()
    if meme_card is None:
        raise ValueError('not_enough_memes')
    return PlayerCard.objects.create(room=room, player=player, meme_card=meme_card)


def deal_hand(room: GameRoom) -> None:
    for player in room.players.all():
        for _ in range(HAND_SIZE):
            draw_card(room, player)


def start_game(room: GameRoom) -> Round:
    situations = pick_situations_for_game(room)
    room.status = GameRoom.STATUS_PLAYING
    room.save(update_fields=['status'])

    now = timezone.now()
    far_future = now + timedelta(days=1)
    for i, situation in enumerate(situations, start=1):
        deadline = now + timedelta(seconds=SUBMITTING_SECONDS) if i == 1 else far_future
        Round.objects.create(
            room=room,
            number=i,
            situation=situation,
            phase=Round.PHASE_SUBMITTING,
            phase_deadline=deadline,
        )
    deal_hand(room)
    return Round.objects.get(room=room, number=1)


def reset_game(room: GameRoom) -> None:
    PlayerCard.objects.filter(room=room).delete()
    Round.objects.filter(room=room).delete()
    room.players.clear()
    room.status = GameRoom.STATUS_WAITING
    room.save(update_fields=['status'])


def advance_phase(round: Round) -> Round:
    with transaction.atomic():
        locked = Round.objects.select_for_update().get(pk=round.pk)
        if locked.phase != round.phase:
            return locked
        now = timezone.now()

        if locked.phase == Round.PHASE_SUBMITTING:
            auto_submit_random_for_missing(locked)
            locked.phase = Round.PHASE_VOTING
            locked.phase_deadline = now + timedelta(seconds=VOTING_SECONDS)
            locked.save(update_fields=['phase', 'phase_deadline'])
            return locked

        if locked.phase == Round.PHASE_VOTING:
            winner = tally_winner(locked)
            locked.winner = winner
            locked.phase = Round.PHASE_RESULTS
            locked.phase_deadline = now + timedelta(seconds=RESULTS_SECONDS)
            locked.save(update_fields=['phase', 'phase_deadline', 'winner'])
            return locked

        if locked.phase == Round.PHASE_RESULTS:
            locked.phase = Round.PHASE_DONE
            locked.save(update_fields=['phase'])
            if locked.number < TOTAL_ROUNDS:
                next_round = Round.objects.select_for_update().get(
                    room=locked.room, number=locked.number + 1
                )
                next_round.phase_deadline = now + timedelta(seconds=SUBMITTING_SECONDS)
                next_round.save(update_fields=['phase_deadline'])
                return next_round
            room = locked.room
            room.status = GameRoom.STATUS_FINISHED
            room.save(update_fields=['status'])
            return locked

        raise ValueError(f'advance_phase called on round in phase {locked.phase}')


def submit_card(round: Round, player, player_card_id: int) -> Submission:
    with transaction.atomic():
        locked = Round.objects.select_for_update().get(pk=round.pk)
        if locked.phase != Round.PHASE_SUBMITTING:
            raise ValueError('wrong_phase')
        if not locked.room.players.filter(pk=player.pk).exists():
            raise ValueError('not_in_game')
        if Submission.objects.filter(round=locked, player=player).exists():
            raise ValueError('already_submitted')
        try:
            pc = PlayerCard.objects.get(pk=player_card_id, room=locked.room, player=player)
        except PlayerCard.DoesNotExist:
            raise ValueError('card_not_yours')

        submission = Submission.objects.create(round=locked, player=player, meme_card=pc.meme_card)
        pc.delete()
        try:
            draw_card(locked.room, player)
        except ValueError:
            pass
        return submission


def auto_submit_random_for_missing(round: Round) -> None:
    submitted_ids = set(
        Submission.objects.filter(round=round).values_list('player_id', flat=True)
    )
    for player in round.room.players.all():
        if player.pk in submitted_ids:
            continue
        pc = PlayerCard.objects.filter(room=round.room, player=player).order_by('?').first()
        if pc is None:
            try:
                pc = draw_card(round.room, player)
            except ValueError:
                continue
        Submission.objects.create(round=round, player=player, meme_card=pc.meme_card)
        pc.delete()
        try:
            draw_card(round.room, player)
        except ValueError:
            pass


def cast_vote(round: Round, voter, submission_id: int) -> Vote:
    with transaction.atomic():
        locked = Round.objects.select_for_update().get(pk=round.pk)
        if locked.phase != Round.PHASE_VOTING:
            raise ValueError('wrong_phase')
        if not locked.room.players.filter(pk=voter.pk).exists():
            raise ValueError('not_in_game')
        try:
            submission = Submission.objects.get(pk=submission_id, round=locked)
        except Submission.DoesNotExist:
            raise ValueError('submission_not_found')
        if submission.player_id == voter.pk:
            raise ValueError('own_submission')
        if Vote.objects.filter(round=locked, voter=voter).exists():
            raise ValueError('already_voted')
        return Vote.objects.create(round=locked, voter=voter, submission=submission)


def remove_player_from_waiting(room: GameRoom, user) -> bool:
    with transaction.atomic():
        locked = GameRoom.objects.select_for_update().get(pk=room.pk)
        if locked.status != GameRoom.STATUS_WAITING:
            return False
        if not locked.players.filter(pk=user.pk).exists():
            return False
        locked.players.remove(user)
        return True


def tally_winner(round: Round) -> Submission | None:
    annotated = list(
        round.submissions.annotate(n_votes=Count('votes')).order_by('-n_votes')
    )
    if not annotated:
        return None
    top = annotated[0].n_votes
    winners = [s for s in annotated if s.n_votes == top]
    return random.choice(winners)


def all_submitted(round: Round) -> bool:
    return round.submissions.count() == round.room.players.count()


def all_voted(round: Round) -> bool:
    return round.votes.count() == round.room.players.count()
