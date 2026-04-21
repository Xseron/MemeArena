from django.contrib import admin
from .models import GameRoom, Situation, Meme, Vote

admin.site.register(GameRoom)
admin.site.register(Situation)
admin.site.register(Meme)
admin.site.register(Vote)