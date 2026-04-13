from rest_framework.routers import DefaultRouter   
from .views import GameRoomViewSet

router = DefaultRouter()
router.register(r'rooms', GameRoomViewSet)

urlpatterns = router.urls