from django.contrib import admin

from .models import GameRoom, Meme, MemeCard, Round, Situation, Vote

admin.site.register(GameRoom)
admin.site.register(Round)
admin.site.register(Situation)
admin.site.register(MemeCard)
admin.site.register(Meme)
admin.site.register(Vote)
