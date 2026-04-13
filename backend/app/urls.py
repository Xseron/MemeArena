from rest_framework import DefaultRouter
from .views import GameRoomViewSet

router = DefaultRouter()
router.register(r'rooms', GameRoomViewSet)

urlpatterns = router.urls