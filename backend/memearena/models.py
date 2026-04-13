from django.db import models
from django.contrib.auth.models import User

class GameRoom(models.Model):
    name = models.CharField(max_length=100)
    players = models.ManyToManyField(User, blank=True)
    status = models.CharField(max_length=20, default='waiting')

    def __str__(self):
        return self.name
    
class Situation(models.Model):
    text = models.TextField()
    def __str__(self):
        return self.text
