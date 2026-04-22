from django.contrib import admin

from .models import GameRoom, MemeCard, PlayerCard, Round, Situation, Submission, Vote

admin.site.register(GameRoom)
admin.site.register(Round)
admin.site.register(Situation)
admin.site.register(MemeCard)
admin.site.register(PlayerCard)
admin.site.register(Submission)
admin.site.register(Vote)
