from django.db import models
from django.contrib.auth.models import User

class GameRoom(models.Model):
    name = models.CharField(max_length=100)
    players = models.ManyToManyField(User, blank=True)
    status = models.CharField(max_length=20, default='waiting')

    def __str__(self):
        return self.name
    
class Situation(models.Model):
    text = models.CharField()
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='situations')
    created_at = models.DateTimeField(auto_now_add=True)
    def __str__(self):
        return self.text
    
class Meme(models.Model):
    title = models.CharField(max_length=100, default="Untitled meme")
    image_url = models.URLField(default="https://example.com/default.jpg")
    caption = models.CharField(max_length=255, default="No caption")
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='memes')
    room = models.ForeignKey(GameRoom, on_delete=models.CASCADE, related_name='memes')
    situation = models.ForeignKey(Situation, on_delete=models.CASCADE, related_name='memes')
    created_at = models.DateTimeField(auto_now_add=True)

class Vote(models.Model):
    room = models.ForeignKey(GameRoom, on_delete=models.CASCADE)
    voter = models.ForeignKey(User, on_delete=models.CASCADE)
    meme = models.ForeignKey(Meme, on_delete=models.CASCADE)

    class Meta:
        unique_together = ['room', 'voter']
