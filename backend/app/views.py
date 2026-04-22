from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken

from .serializers import RegisterSerializer, LoginSerializer


@api_view(['POST'])
@permission_classes([AllowAny])
def register_view(request):
    serializer = RegisterSerializer(data=request.data)
    if serializer.is_valid():
        user = serializer.save()
        return Response(
            {"message": "User registered successfully", "username": user.username},
            status=status.HTTP_201_CREATED,
        )
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


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
            'username': user.username,
        }, status=status.HTTP_200_OK)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


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


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def me_view(request):
    return Response({'id': request.user.id, 'username': request.user.username})


from . import game
from .consumers import broadcast_state, trigger_phase_cancel, trigger_phase_restart
from asgiref.sync import async_to_sync


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def submit_view(request):
    room = game.get_room()
    round = game.active_round(room)
    if round is None:
        return Response({'error': 'no_round'}, status=400)
    try:
        player_card_id = int(request.data.get('player_card_id'))
    except (TypeError, ValueError):
        return Response({'error': 'missing_player_card_id'}, status=400)
    try:
        game.submit_card(round, request.user, player_card_id)
    except ValueError as e:
        return Response({'error': str(e)}, status=400)

    if game.all_submitted(round):
        game.advance_phase(round)
        async_to_sync(trigger_phase_restart)()

    async_to_sync(broadcast_state)()
    return Response(status=204)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def vote_view(request):
    room = game.get_room()
    round = game.active_round(room)
    if round is None:
        return Response({'error': 'no_round'}, status=400)
    try:
        submission_id = int(request.data.get('submission_id'))
    except (TypeError, ValueError):
        return Response({'error': 'missing_submission_id'}, status=400)
    try:
        game.cast_vote(round, request.user, submission_id)
    except ValueError as e:
        return Response({'error': str(e)}, status=400)

    if game.all_voted(round):
        game.advance_phase(round)
        async_to_sync(trigger_phase_restart)()

    async_to_sync(broadcast_state)()
    return Response(status=204)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def reset_view(request):
    room = game.get_room()
    game.reset_game(room)
    async_to_sync(trigger_phase_cancel)()
    async_to_sync(broadcast_state)()
    return Response(status=204)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def kick_view(request):
    from django.contrib.auth.models import User

    try:
        user_id = int(request.data.get('user_id'))
    except (TypeError, ValueError):
        return Response({'error': 'missing_user_id'}, status=400)
    if user_id == request.user.id:
        return Response({'error': 'cannot_kick_self'}, status=400)
    room = game.get_room()
    if room.status != 'waiting':
        return Response({'error': 'not_in_waiting'}, status=400)
    if not room.players.filter(pk=request.user.id).exists():
        return Response({'error': 'not_a_participant'}, status=403)
    try:
        victim = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        return Response({'error': 'user_not_found'}, status=404)
    if not room.players.filter(pk=user_id).exists():
        return Response({'error': 'not_in_room'}, status=400)
    room.players.remove(victim)
    async_to_sync(broadcast_state)()
    return Response(status=204)
