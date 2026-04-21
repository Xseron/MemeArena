from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import register_view, login_view, logout_view, me_view

urlpatterns = [
    path('auth/register/', register_view, name='register'),
    path('auth/login/', login_view, name='login'),
    path('auth/logout/', logout_view, name='logout'),
    path('auth/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('auth/me/', me_view, name='me'),
]
