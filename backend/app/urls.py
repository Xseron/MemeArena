from django.urls import path
from .views import (
    register_view,
    login_view,
    logout_view,
    vote_for_meme,
    GameRoomListCreateView,
    SituationListCreateView,
    MemeListCreateView,
    MemeDetailView,
)

urlpatterns = [
    path('register/', register_view, name='register'),
    path('login/', login_view, name='login'),
    path('logout/', logout_view, name='logout'),

    path('rooms/', GameRoomListCreateView.as_view(), name='rooms'),
    path('situations/', SituationListCreateView.as_view(), name='situations'),

    path('memes/', MemeListCreateView.as_view(), name='meme-list-create'),
    path('memes/<int:pk>/', MemeDetailView.as_view(), name='meme-detail'),

    path('memes/<int:meme_id>/vote/', vote_for_meme, name='vote-meme'),
]