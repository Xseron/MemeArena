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


class Situation(models.Model):
    text = models.TextField()
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='situations')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.text[:80]


class MemeCard(models.Model):
    title = models.CharField(max_length=100)
    # Relative path under frontend/public/, e.g. "/memes/giga.png"
    image_url = models.CharField(max_length=255)
    caption = models.CharField(max_length=255, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


class Meme(models.Model):
    title = models.CharField(max_length=100, default='Untitled meme')
    image_url = models.URLField(default='https://example.com/default.jpg')
    caption = models.CharField(max_length=255, default='No caption')
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='memes')
    room = models.ForeignKey(GameRoom, on_delete=models.CASCADE, related_name='memes')
    situation = models.ForeignKey(Situation, on_delete=models.CASCADE, related_name='memes')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


class Vote(models.Model):
    room = models.ForeignKey(GameRoom, on_delete=models.CASCADE, related_name='votes')
    voter = models.ForeignKey(User, on_delete=models.CASCADE, related_name='cast_votes')
    meme = models.ForeignKey(Meme, on_delete=models.CASCADE, related_name='votes')

    class Meta:
        unique_together = ('room', 'voter')
