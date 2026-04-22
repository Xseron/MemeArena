from django.contrib.auth.models import User
from django.db import models


class GameRoom(models.Model):
    STATUS_WAITING = 'waiting'
    STATUS_PLAYING = 'playing'
    STATUS_FINISHED = 'finished'
    STATUS_CHOICES = [
        (STATUS_WAITING, 'Waiting'),
        (STATUS_PLAYING, 'Playing'),
        (STATUS_FINISHED, 'Finished'),
    ]

    name = models.CharField(max_length=100, default='arena')
    players = models.ManyToManyField(User, blank=True, related_name='rooms')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_WAITING)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.name} [{self.status}]'


class Situation(models.Model):
    text = models.TextField()
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='situations')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.text[:80]


class MemeCard(models.Model):
    title = models.CharField(max_length=100)
    image_url = models.CharField(max_length=255)
    caption = models.CharField(max_length=255, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


class Round(models.Model):
    PHASE_SUBMITTING = 'submitting'
    PHASE_VOTING = 'voting'
    PHASE_RESULTS = 'results'
    PHASE_DONE = 'done'
    PHASE_CHOICES = [
        (PHASE_SUBMITTING, 'Submitting'),
        (PHASE_VOTING, 'Voting'),
        (PHASE_RESULTS, 'Results'),
        (PHASE_DONE, 'Done'),
    ]

    room = models.ForeignKey(GameRoom, on_delete=models.CASCADE, related_name='rounds')
    number = models.PositiveSmallIntegerField()
    situation = models.ForeignKey(
        Situation, on_delete=models.PROTECT, null=True, related_name='used_in_rounds'
    )
    phase = models.CharField(max_length=20, choices=PHASE_CHOICES, default=PHASE_SUBMITTING)
    phase_deadline = models.DateTimeField()
    winner = models.ForeignKey(
        'Submission', null=True, blank=True, on_delete=models.SET_NULL, related_name='+'
    )

    class Meta:
        unique_together = ('room', 'number')
        ordering = ['-number']

    def __str__(self):
        return f'Round {self.number} [{self.phase}]'


class PlayerCard(models.Model):
    room = models.ForeignKey(GameRoom, on_delete=models.CASCADE, related_name='hand_cards')
    player = models.ForeignKey(User, on_delete=models.CASCADE, related_name='hand_cards')
    meme_card = models.ForeignKey(MemeCard, on_delete=models.PROTECT)


class Submission(models.Model):
    round = models.ForeignKey(Round, on_delete=models.CASCADE, related_name='submissions')
    player = models.ForeignKey(User, on_delete=models.CASCADE, related_name='submissions')
    meme_card = models.ForeignKey(MemeCard, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('round', 'player')


class Vote(models.Model):
    round = models.ForeignKey(Round, on_delete=models.CASCADE, related_name='votes')
    voter = models.ForeignKey(User, on_delete=models.CASCADE, related_name='votes_cast')
    submission = models.ForeignKey(Submission, on_delete=models.CASCADE, related_name='votes')

    class Meta:
        unique_together = ('round', 'voter')
