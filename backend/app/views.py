from django.contrib.auth.models import User
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from rest_framework.generics import ListCreateAPIView, RetrieveUpdateDestroyAPIView
from rest_framework_simplejwt.tokens import RefreshToken

from .models import GameRoom, Situation, Meme, Vote
from .serializers import (
    RegisterSerializer,
    LoginSerializer,
    GameRoomSerializer,
    SituationSerializer,
    MemeSerializer,
    VoteSerializer
)


# =========================
# FBV 1: Register
# =========================
@api_view(['POST'])
@permission_classes([AllowAny])
def register_view(request):
    serializer = RegisterSerializer(data=request.data)
    if serializer.is_valid():
        user = serializer.save()
        return Response(
            {"message": "User registered successfully", "username": user.username},
            status=status.HTTP_201_CREATED
        )
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# =========================
# FBV 2: Login
# =========================
@api_view(['POST'])
@permission_classes([AllowAny])
def login_view(request):
    serializer = LoginSerializer(data=request.data)
    if serializer.is_valid():
        user = serializer.validated_data['user']
        refresh = RefreshToken.for_user(user)

        return Response({
            'message': 'Login successful',
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'username': user.username
        }, status=status.HTTP_200_OK)

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# =========================
# FBV 3: Logout
# =========================
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def logout_view(request):
    refresh_token = request.data.get("refresh")
    if not refresh_token:
        return Response({"error": "Refresh token is required"}, status=400)

    try:
        token = RefreshToken(refresh_token)
        token.blacklist()
        return Response({"message": "Logout successful"}, status=205)
    except Exception:
        return Response({"error": "Invalid token"}, status=400)


# =========================
# FBV 4: Vote for meme
# =========================
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def vote_for_meme(request, meme_id):
    try:
        meme = Meme.objects.get(id=meme_id)
    except Meme.DoesNotExist:
        return Response({"error": "Meme not found"}, status=404)

    if Vote.objects.filter(user=request.user, meme=meme).exists():
        return Response({"error": "You already voted for this meme"}, status=400)

    vote = Vote.objects.create(user=request.user, meme=meme)
    serializer = VoteSerializer(vote)
    return Response(serializer.data, status=201)



# =========================
# CBV 1: Room List/Create
# =========================
class GameRoomListCreateView(ListCreateAPIView):
    queryset = GameRoom.objects.all()
    serializer_class = GameRoomSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


# =========================
# CBV 2: Situation List/Create
# =========================
class SituationListCreateView(ListCreateAPIView):
    queryset = Situation.objects.all()
    serializer_class = SituationSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


# =========================
# CBV 3: Meme List/Create
# CRUD: Create + Read list
# =========================
class MemeListCreateView(ListCreateAPIView):
    queryset = Meme.objects.all()
    serializer_class = MemeSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)


# =========================
# CBV 4: Meme Detail
# CRUD: Read one + Update + Delete
# =========================
class MemeDetailView(RetrieveUpdateDestroyAPIView):
    queryset = Meme.objects.all()
    serializer_class = MemeSerializer
    permission_classes = [IsAuthenticated]