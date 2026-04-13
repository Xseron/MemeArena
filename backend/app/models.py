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
    
class Meme(models.Model):
    room = models.ForeignKey(GameRoom, on_delete=models.CASCADE, related_name="memes")
    player = models.ForeignKey(User, on_delete=models.CASCADE)
    situation = models.ForeignKey(Situation, on_delete=models.CASCADE, related_name="memes")
    image = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
   

class Vote(models.Model):
    room = models.ForeignKey(GameRoom, on_delete=models.CASCADE)
    voter = models.ForeignKey(User, on_delete=models.CASCADE)
    meme = models.ForeignKey(Meme, on_delete=models.CASCADE)

    class Meta:
        unique_together = ['room', 'voter']
