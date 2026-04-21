from datetime import timedelta

from django.utils import timezone

from .models import GameRoom, Round

SUBMITTING_SECONDS = 30
VOTING_SECONDS = 20
RESULTS_SECONDS = 5
TOTAL_ROUNDS = 8
RESET_DELAY_SECONDS = 10


def get_room() -> GameRoom:
    return GameRoom.objects.get(pk=1)


def add_player(room: GameRoom, user) -> bool:
    """Add user to the room. Returns True on add, False if spectator."""
    if room.status != GameRoom.STATUS_WAITING:
        return False
    if room.players.filter(pk=user.pk).exists():
        return False
    if room.players.count() >= 4:
        return False
    room.players.add(user)
    return True


def start_game(room: GameRoom) -> Round:
    room.status = GameRoom.STATUS_PLAYING
    room.save(update_fields=['status'])
    return Round.objects.create(
        room=room,
        number=1,
        phase=Round.PHASE_SUBMITTING,
        phase_deadline=timezone.now() + timedelta(seconds=SUBMITTING_SECONDS),
    )


def advance_phase(round: Round) -> Round:
    now = timezone.now()
    if round.phase == Round.PHASE_SUBMITTING:
        round.phase = Round.PHASE_VOTING
        round.phase_deadline = now + timedelta(seconds=VOTING_SECONDS)
        round.save(update_fields=['phase', 'phase_deadline'])
        return round

    if round.phase == Round.PHASE_VOTING:
        round.phase = Round.PHASE_RESULTS
        round.phase_deadline = now + timedelta(seconds=RESULTS_SECONDS)
        round.save(update_fields=['phase', 'phase_deadline'])
        return round

    if round.phase == Round.PHASE_RESULTS:
        if round.number < TOTAL_ROUNDS:
            return Round.objects.create(
                room=round.room,
                number=round.number + 1,
                phase=Round.PHASE_SUBMITTING,
                phase_deadline=now + timedelta(seconds=SUBMITTING_SECONDS),
            )
        # Last round — finish game.
        round.phase = Round.PHASE_DONE
        round.phase_deadline = now
        round.save(update_fields=['phase', 'phase_deadline'])
        room = round.room
        room.status = GameRoom.STATUS_FINISHED
        room.save(update_fields=['status'])
        return round

    raise ValueError(f'advance_phase called on round in phase {round.phase}')


def reset_game(room: GameRoom) -> None:
    Round.objects.filter(room=room).delete()
    room.players.clear()
    room.status = GameRoom.STATUS_WAITING
    room.save(update_fields=['status'])
