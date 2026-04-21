from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.contrib.auth.models import AnonymousUser, User
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import UntypedToken


@database_sync_to_async
def _get_user(user_id: int) -> User | AnonymousUser:
    try:
        return User.objects.get(pk=user_id)
    except User.DoesNotExist:
        return AnonymousUser()


class JWTAuthMiddleware(BaseMiddleware):
    async def __call__(self, scope, receive, send):
        query = parse_qs((scope.get('query_string') or b'').decode())
        token = (query.get('token') or [None])[0]
        scope['user'] = AnonymousUser()
        if token:
            try:
                decoded = UntypedToken(token)
                scope['user'] = await _get_user(decoded['user_id'])
            except (InvalidToken, TokenError):
                pass
        return await super().__call__(scope, receive, send)
