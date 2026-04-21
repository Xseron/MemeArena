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
    phase = models.CharField(max_length=20, choices=PHASE_CHOICES, default=PHASE_SUBMITTING)
    phase_deadline = models.DateTimeField()

    class Meta:
        unique_together = ('room', 'number')
        ordering = ['-number']

    def __str__(self):
        return f'Round {self.number} [{self.phase}]'
