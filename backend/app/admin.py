from django.contrib import admin

from .models import GameRoom, Meme, Round, Situation, Vote

admin.site.register(GameRoom)
admin.site.register(Round)
admin.site.register(Situation)
admin.site.register(Meme)
admin.site.register(Vote)
