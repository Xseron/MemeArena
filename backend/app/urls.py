from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    register_view,
    login_view,
    logout_view,
    me_view,
    submit_view,
    vote_view,
    reset_view,
    kick_view,
)

urlpatterns = [
    path('auth/register/', register_view, name='register'),
    path('auth/login/', login_view, name='login'),
    path('auth/logout/', logout_view, name='logout'),
    path('auth/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('auth/me/', me_view, name='me'),
    path('game/submit/', submit_view, name='game_submit'),
    path('game/vote/', vote_view, name='game_vote'),
    path('game/reset/', reset_view, name='game_reset'),
    path('game/kick/', kick_view, name='game_kick'),
]
