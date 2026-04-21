# MemeArena Walking-Skeleton Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the MemeArena walking-skeleton: JWT auth, an Angular shell that can log in and view raw game state, and a Django server-side phase state machine (singleton room, 4-player matchmaking, 8 rounds × 3 phases on asyncio timers, auto-reset). Card/meme/voting mechanics are deliberately deferred to a follow-up plan.

**Architecture:** "Dead simple" — single Django app (`app/`), DB as source of truth for room state, Django Channels + WebSocket for server→client state push, REST for auth actions (and for the next-spec game actions). One singleton `GameRoom(id=1)` created by data migration. Phase transitions fire from a single `asyncio.create_task` loop inside the Channels consumer. Frontend is Angular 21 standalone components with signals, one `GameStateService` that subscribes to the WS stream and feeds signals to components.

**Tech Stack:**
- Backend: Django 6 + DRF + `djangorestframework-simplejwt` (+ `token_blacklist`) + `channels` + `daphne` + `django-cors-headers`, SQLite in dev.
- Frontend: Angular 21 standalone + signals + RxJS + native `fetch`/HttpClient + WebSocket.

**Reference spec:** `docs/superpowers/specs/2026-04-21-memearena-skeleton-design.md`.

---

## File Structure

### Backend (`backend/`)

Files to **create**:
- `backend/requirements.txt` — pinned deps.
- `backend/app/game.py` — pure sync ORM game-engine functions.
- `backend/app/consumers.py` — `GameConsumer` + module-level `broadcast_state()`.
- `backend/app/ws_auth.py` — `JWTAuthMiddleware` for Channels.
- `backend/app/routing.py` — WebSocket URL patterns.
- `backend/app/migrations/0002_singleton_room.py` — data migration creating `GameRoom(id=1)`.

Files to **modify**:
- `backend/memearena/settings.py` — add Channels/daphne, CORS middleware, REST/SimpleJWT config.
- `backend/memearena/asgi.py` — `ProtocolTypeRouter` with JWT-middleware-wrapped WebSocket router.
- `backend/memearena/urls.py` — change prefix from `app/` to `api/`.
- `backend/app/models.py` — trim `GameRoom`, delete `Situation/Meme/Vote`, add `Round`.
- `backend/app/admin.py` — unregister deleted models.
- `backend/app/urls.py` — nest auth under `auth/`, add `me/` and `refresh/` endpoints, drop CRUD routes.
- `backend/app/views.py` — drop CRUD and vote views, add `me_view`.
- `backend/app/serializers.py` — drop non-auth serializers.
- `backend/app/tests.py` — add auth + game-engine + consumer tests.

Files to **delete**:
- `backend/app/migrations/0001_initial.py` — regenerated from scratch.
- `backend/db.sqlite3` — dev data, clean slate.

### Frontend (`frontend/src/`)

Files to **create**:
- `environments/environment.ts` — `apiUrl`, `wsUrl`.
- `environments/environment.development.ts` — same, for dev builds.
- `app/core/models.ts` — TS types (`User`, `AuthTokens`, `Player`, `RoundDto`, `StateMessage`).
- `app/core/auth.service.ts` — register/login/logout + JWT storage + `currentUser` signal.
- `app/core/auth.interceptor.ts` — function-style interceptor attaching `Authorization` header.
- `app/core/auth.guard.ts` — redirects unauthenticated users to `/login`.
- `app/core/api.service.ts` — thin `HttpClient` wrapper for `/api/auth/*`.
- `app/core/ws.service.ts` — single WebSocket connection + reconnect.
- `app/core/game-state.service.ts` — signals holding room state, wired to `WsService`.
- `app/pages/login/login.ts`, `.html`, `.css` — auth form.
- `app/pages/game/game.ts`, `.html`, `.css` — placeholder state viewer.
- `app/components/timer/timer.ts`, `.html`, `.css` — countdown to `phase_deadline`.
- `app/components/player-badge/player-badge.ts`, `.html`, `.css` — one-player chip.
- `app/core/auth.service.spec.ts`, `app/core/game-state.service.spec.ts` — Vitest specs.

Files to **modify**:
- `frontend/src/app/app.routes.ts` — real route table.
- `frontend/src/app/app.config.ts` — `provideHttpClient(withInterceptors([authInterceptor]))`.
- `frontend/src/app/app.ts` — strip `CardHandComponent` import/usage; become a plain `<router-outlet>`.
- `frontend/src/app/app.html` — `<router-outlet />`.

Files **untouched** (kept for the next-spec):
- `frontend/src/app/components/card-hand/*` — preserved on disk, not routed anywhere.

---

## Implementation Tasks

Tasks are ordered so the repo compiles / tests green at each commit. Early tasks establish the baseline (cleanup, settings, models); middle tasks build the backend skeleton with TDD; later tasks build the frontend; final task is an end-to-end manual smoke.

### Task 1: Remove teammate's REST scaffolding

Teammate's commit `6afce32` added multi-room CRUD that conflicts with our singleton+WS design. We delete all of it in one swoop. No tests here — pure removal verified by a clean `python manage.py check`.

**Files:**
- Modify: `backend/app/views.py`
- Modify: `backend/app/serializers.py`
- Modify: `backend/app/urls.py`
- Modify: `backend/app/admin.py`

- [ ] **Step 1: Overwrite `backend/app/views.py` with auth-only content**

```python
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
```

- [ ] **Step 2: Overwrite `backend/app/serializers.py` with auth-only content**

```python
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from rest_framework import serializers


class RegisterSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(write_only=True)
    email = serializers.EmailField(required=False)

    def create(self, validated_data):
        return User.objects.create_user(
            username=validated_data['username'],
            password=validated_data['password'],
            email=validated_data.get('email', ''),
        )


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        user = authenticate(username=attrs['username'], password=attrs['password'])
        if not user:
            raise serializers.ValidationError("Invalid username or password")
        attrs['user'] = user
        return attrs
```

- [ ] **Step 3: Overwrite `backend/app/urls.py` to remove CRUD routes (we'll re-add `me`/`refresh` in Task 8)**

```python
from django.urls import path
from .views import register_view, login_view, logout_view

urlpatterns = [
    path('auth/register/', register_view, name='register'),
    path('auth/login/', login_view, name='login'),
    path('auth/logout/', logout_view, name='logout'),
]
```

- [ ] **Step 4: Overwrite `backend/app/admin.py` to remove registrations for deleted models**

```python
from django.contrib import admin  # noqa: F401
```

- [ ] **Step 5: Verify Django still loads**

Run: `cd backend && python manage.py check`
Expected: `System check identified no issues (0 silenced).`

> If it fails complaining about `Situation / Meme / Vote` imports anywhere, grep the app for leftover references and remove them — models are about to change too.

- [ ] **Step 6: Commit**

```bash
git add backend/app/views.py backend/app/serializers.py backend/app/urls.py backend/app/admin.py
git commit -m "chore: drop teammate's non-auth REST scaffolding"
```

---

### Task 2: Lock dependencies (channels + daphne)

**Files:**
- Create: `backend/requirements.txt`

- [ ] **Step 1: Create `backend/requirements.txt`**

```
django>=6.0,<6.1
djangorestframework>=3.15
djangorestframework-simplejwt>=5.3
channels>=4.1
daphne>=4.1
django-cors-headers>=4.3
```

- [ ] **Step 2: Install**

Run: `cd backend && pip install -r requirements.txt`
Expected: installs `channels`, `daphne` (and confirms already-installed `djangorestframework-simplejwt`, `corsheaders`, etc.).

- [ ] **Step 3: Verify**

Run: `cd backend && python -c "import channels, daphne, corsheaders, rest_framework_simplejwt; print('ok')"`
Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add backend/requirements.txt
git commit -m "chore: pin backend dependencies"
```

---

### Task 3: Configure settings.py for channels + CORS + JWT

**Files:**
- Modify: `backend/memearena/settings.py`

- [ ] **Step 1: Replace `INSTALLED_APPS`, add the middleware/CORS/REST/JWT/Channels blocks**

Open `backend/memearena/settings.py` and replace its contents with:

```python
"""
Django settings for memearena project.
"""

from datetime import timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = 'django-insecure-kc#z0(%1x#@^-f08uc%*p*7v6cy!y31q-+k(5mble9jvr*w%+d'
DEBUG = True
ALLOWED_HOSTS = ['*']

INSTALLED_APPS = [
    'daphne',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'channels',
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'corsheaders',
    'app',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'memearena.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'memearena.wsgi.application'
ASGI_APPLICATION = 'memearena.asgi.application'

CHANNEL_LAYERS = {
    'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer'},
}

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=1),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': False,
    'BLACKLIST_AFTER_ROTATION': True,
}

CORS_ALLOWED_ORIGINS = ['http://localhost:4200']
```

- [ ] **Step 2: Verify `python manage.py check` passes**

Run: `cd backend && python manage.py check`
Expected: `System check identified no issues (0 silenced).`

- [ ] **Step 3: Commit**

```bash
git add backend/memearena/settings.py
git commit -m "feat(settings): wire channels, CORS, JWT, daphne"
```

---

### Task 4: Rewrite models.py (trim GameRoom, add Round, delete rest)

**Files:**
- Modify: `backend/app/models.py`

- [ ] **Step 1: Replace `backend/app/models.py` contents**

```python
from django.contrib.auth.models import User
from django.db import models


class GameRoom(models.Model):
    STATUS_WAITING = 'waiting'
    STATUS_PLAYING = 'playing'
    STATUS_FINISHED = 'finished'
    STATUS_CHOICES = [
        (STATUS_WAITING, 'Waiting'),
        (STATUS_PLAYING, 'Playing'),
        (STATUS_FINISHED, 'Finished'),
    ]

    name = models.CharField(max_length=100, default='arena')
    players = models.ManyToManyField(User, blank=True, related_name='rooms')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_WAITING)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.name} [{self.status}]'


class Round(models.Model):
    PHASE_SUBMITTING = 'submitting'
    PHASE_VOTING = 'voting'
    PHASE_RESULTS = 'results'
    PHASE_DONE = 'done'
    PHASE_CHOICES = [
        (PHASE_SUBMITTING, 'Submitting'),
        (PHASE_VOTING, 'Voting'),
        (PHASE_RESULTS, 'Results'),
        (PHASE_DONE, 'Done'),
    ]

    room = models.ForeignKey(GameRoom, on_delete=models.CASCADE, related_name='rounds')
    number = models.PositiveSmallIntegerField()
    phase = models.CharField(max_length=20, choices=PHASE_CHOICES, default=PHASE_SUBMITTING)
    phase_deadline = models.DateTimeField()

    class Meta:
        unique_together = ('room', 'number')
        ordering = ['-number']

    def __str__(self):
        return f'Round {self.number} [{self.phase}]'
```

- [ ] **Step 2: Verify `python manage.py check` passes**

Run: `cd backend && python manage.py check`
Expected: `System check identified no issues (0 silenced).`

- [ ] **Step 3: Commit**

```bash
git add backend/app/models.py
git commit -m "feat(models): trim GameRoom and add Round; drop legacy models"
```

---

### Task 5: Regenerate initial migration and add singleton data migration

**Files:**
- Delete: `backend/app/migrations/0001_initial.py`
- Delete: `backend/db.sqlite3`
- Create: `backend/app/migrations/0001_initial.py` (regenerated)
- Create: `backend/app/migrations/0002_singleton_room.py`

- [ ] **Step 1: Delete legacy migration and dev DB**

```bash
rm backend/app/migrations/0001_initial.py
rm backend/db.sqlite3
```

- [ ] **Step 2: Regenerate the initial migration**

Run: `cd backend && python manage.py makemigrations app`
Expected: `Migrations for 'app': app/migrations/0001_initial.py - Create model GameRoom - Create model Round`

- [ ] **Step 3: Create the singleton data migration**

Create file `backend/app/migrations/0002_singleton_room.py`:

```python
from django.db import migrations


def create_singleton_room(apps, schema_editor):
    GameRoom = apps.get_model('app', 'GameRoom')
    GameRoom.objects.update_or_create(pk=1, defaults={'name': 'arena', 'status': 'waiting'})


def delete_singleton_room(apps, schema_editor):
    GameRoom = apps.get_model('app', 'GameRoom')
    GameRoom.objects.filter(pk=1).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(create_singleton_room, delete_singleton_room),
    ]
```

- [ ] **Step 4: Apply migrations**

Run: `cd backend && python manage.py migrate`
Expected: runs `app.0001_initial`, `app.0002_singleton_room`, `token_blacklist.*`, and stock Django migrations. Final line contains `OK`.

- [ ] **Step 5: Verify the singleton exists**

Run: `cd backend && python manage.py shell -c "from app.models import GameRoom; r = GameRoom.objects.get(pk=1); print(r.name, r.status)"`
Expected: `arena waiting`

- [ ] **Step 6: Commit**

```bash
git add backend/app/migrations/ backend/db.sqlite3
git commit -m "feat(migrations): fresh initial + singleton room data migration"
```

---

### Task 6: Restructure project URLs under `/api/`

**Files:**
- Modify: `backend/memearena/urls.py`
- Modify: `backend/app/urls.py` (add `me/`, `refresh/`)

- [ ] **Step 1: Replace `backend/memearena/urls.py`**

```python
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('app.urls')),
]
```

- [ ] **Step 2: Replace `backend/app/urls.py` to include `me/` and `refresh/`**

```python
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
```

- [ ] **Step 3: Verify the routing**

Run: `cd backend && python manage.py check`
Expected: `System check identified no issues (0 silenced).`

Run: `cd backend && python manage.py runserver 8000 &` (start in background), then:
```bash
curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost:8000/api/auth/register/ \
  -H "Content-Type: application/json" \
  -d '{"username":"smoke","password":"smoke-pw-123"}'
```
Expected: `201`

Then stop the background server.

- [ ] **Step 4: Commit**

```bash
git add backend/memearena/urls.py backend/app/urls.py
git commit -m "feat(urls): move to /api/ prefix, add me and refresh endpoints"
```

---

### Task 7: Auth endpoint tests

**Files:**
- Modify: `backend/app/tests.py`

- [ ] **Step 1: Write failing tests**

Replace `backend/app/tests.py`:

```python
from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework.test import APITestCase


class AuthEndpointsTests(APITestCase):
    def test_register_creates_user_and_returns_201(self):
        resp = self.client.post(
            reverse('register'),
            {'username': 'alice', 'password': 'pw-12345'},
            format='json',
        )
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(User.objects.filter(username='alice').exists())
        self.assertEqual(resp.data['username'], 'alice')

    def test_register_rejects_duplicate_username(self):
        User.objects.create_user(username='bob', password='x')
        resp = self.client.post(
            reverse('register'),
            {'username': 'bob', 'password': 'pw-12345'},
            format='json',
        )
        self.assertEqual(resp.status_code, 400)

    def test_login_returns_access_and_refresh(self):
        User.objects.create_user(username='carol', password='pw-12345')
        resp = self.client.post(
            reverse('login'),
            {'username': 'carol', 'password': 'pw-12345'},
            format='json',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn('access', resp.data)
        self.assertIn('refresh', resp.data)
        self.assertEqual(resp.data['username'], 'carol')

    def test_login_rejects_wrong_password(self):
        User.objects.create_user(username='dave', password='correct')
        resp = self.client.post(
            reverse('login'),
            {'username': 'dave', 'password': 'wrong'},
            format='json',
        )
        self.assertEqual(resp.status_code, 400)

    def test_me_requires_auth(self):
        resp = self.client.get(reverse('me'))
        self.assertEqual(resp.status_code, 401)

    def test_me_returns_current_user(self):
        user = User.objects.create_user(username='erin', password='pw-12345')
        login = self.client.post(
            reverse('login'),
            {'username': 'erin', 'password': 'pw-12345'},
            format='json',
        )
        access = login.data['access']
        resp = self.client.get(reverse('me'), HTTP_AUTHORIZATION=f'Bearer {access}')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data, {'id': user.id, 'username': 'erin'})

    def test_logout_blacklists_refresh_token(self):
        User.objects.create_user(username='frank', password='pw-12345')
        login = self.client.post(
            reverse('login'),
            {'username': 'frank', 'password': 'pw-12345'},
            format='json',
        )
        access = login.data['access']
        refresh = login.data['refresh']
        logout = self.client.post(
            reverse('logout'),
            {'refresh': refresh},
            format='json',
            HTTP_AUTHORIZATION=f'Bearer {access}',
        )
        self.assertEqual(logout.status_code, 205)
        # Refreshing with the blacklisted token must now fail.
        refreshed = self.client.post(
            reverse('token_refresh'),
            {'refresh': refresh},
            format='json',
        )
        self.assertEqual(refreshed.status_code, 401)

    def test_refresh_returns_new_access(self):
        User.objects.create_user(username='gina', password='pw-12345')
        login = self.client.post(
            reverse('login'),
            {'username': 'gina', 'password': 'pw-12345'},
            format='json',
        )
        refresh = login.data['refresh']
        resp = self.client.post(
            reverse('token_refresh'),
            {'refresh': refresh},
            format='json',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn('access', resp.data)
```

- [ ] **Step 2: Run tests, verify they pass**

Run: `cd backend && python manage.py test app.tests.AuthEndpointsTests -v 2`
Expected: `Ran 8 tests in <time>. OK`

> If any test fails, the auth FBVs or URL wiring is off — fix the offending file (not the test).

- [ ] **Step 3: Commit**

```bash
git add backend/app/tests.py
git commit -m "test: auth endpoint coverage"
```

---

### Task 8: Implement `app/game.py` — pure engine functions (TDD)

We build five functions, each test-first: `get_room`, `add_player`, `start_game`, `advance_phase`, `reset_game`.

**Files:**
- Create: `backend/app/game.py`
- Modify: `backend/app/tests.py`

- [ ] **Step 1: Add failing tests for `get_room` and `add_player`**

Append to `backend/app/tests.py`:

```python
from django.test import TestCase
from django.utils import timezone

from app import game
from app.models import GameRoom, Round


class GameEngineTests(TestCase):
    def setUp(self):
        self.room = GameRoom.objects.get(pk=1)
        self.users = [
            User.objects.create_user(username=f'p{i}', password='x') for i in range(5)
        ]

    def test_get_room_returns_singleton(self):
        self.assertEqual(game.get_room().pk, 1)

    def test_add_player_adds_up_to_four(self):
        self.assertTrue(game.add_player(self.room, self.users[0]))
        self.assertTrue(game.add_player(self.room, self.users[1]))
        self.assertTrue(game.add_player(self.room, self.users[2]))
        self.assertTrue(game.add_player(self.room, self.users[3]))
        self.assertEqual(self.room.players.count(), 4)

    def test_add_player_returns_false_when_full(self):
        for u in self.users[:4]:
            game.add_player(self.room, u)
        self.assertFalse(game.add_player(self.room, self.users[4]))
        self.assertEqual(self.room.players.count(), 4)

    def test_add_player_returns_false_when_not_waiting(self):
        self.room.status = GameRoom.STATUS_PLAYING
        self.room.save()
        self.assertFalse(game.add_player(self.room, self.users[0]))

    def test_add_player_is_idempotent_for_same_user(self):
        self.assertTrue(game.add_player(self.room, self.users[0]))
        # Already in — second call returns False, count stays 1.
        self.assertFalse(game.add_player(self.room, self.users[0]))
        self.assertEqual(self.room.players.count(), 1)
```

- [ ] **Step 2: Run — expect failures about missing module `app.game`**

Run: `cd backend && python manage.py test app.tests.GameEngineTests -v 2`
Expected: errors — `ModuleNotFoundError: No module named 'app.game'`.

- [ ] **Step 3: Create `backend/app/game.py` with `get_room`, `add_player`**

```python
from datetime import timedelta

from django.utils import timezone

from .models import GameRoom, Round

SUBMITTING_SECONDS = 30
VOTING_SECONDS = 20
RESULTS_SECONDS = 5
TOTAL_ROUNDS = 8
RESET_DELAY_SECONDS = 10


def get_room() -> GameRoom:
    return GameRoom.objects.get(pk=1)


def add_player(room: GameRoom, user) -> bool:
    """Add user to the room. Returns True on add, False if spectator."""
    if room.status != GameRoom.STATUS_WAITING:
        return False
    if room.players.filter(pk=user.pk).exists():
        return False
    if room.players.count() >= 4:
        return False
    room.players.add(user)
    return True
```

- [ ] **Step 4: Re-run the tests — expect PASS**

Run: `cd backend && python manage.py test app.tests.GameEngineTests -v 2`
Expected: `Ran 5 tests ... OK`

- [ ] **Step 5: Add failing tests for `start_game`**

Append to `GameEngineTests`:

```python
    def test_start_game_sets_status_and_creates_round_1(self):
        for u in self.users[:4]:
            game.add_player(self.room, u)
        round1 = game.start_game(self.room)
        self.room.refresh_from_db()
        self.assertEqual(self.room.status, GameRoom.STATUS_PLAYING)
        self.assertEqual(round1.number, 1)
        self.assertEqual(round1.phase, Round.PHASE_SUBMITTING)
        self.assertGreater(round1.phase_deadline, timezone.now())
        self.assertLessEqual(
            round1.phase_deadline,
            timezone.now() + timedelta(seconds=game.SUBMITTING_SECONDS + 1),
        )
```

- [ ] **Step 6: Run — expect failure**

Run: `cd backend && python manage.py test app.tests.GameEngineTests.test_start_game_sets_status_and_creates_round_1 -v 2`
Expected: `AttributeError: module 'app.game' has no attribute 'start_game'`.

- [ ] **Step 7: Implement `start_game` in `game.py`**

Append:

```python
def start_game(room: GameRoom) -> Round:
    room.status = GameRoom.STATUS_PLAYING
    room.save(update_fields=['status'])
    return Round.objects.create(
        room=room,
        number=1,
        phase=Round.PHASE_SUBMITTING,
        phase_deadline=timezone.now() + timedelta(seconds=SUBMITTING_SECONDS),
    )
```

- [ ] **Step 8: Re-run — expect PASS**

Run: `cd backend && python manage.py test app.tests.GameEngineTests -v 2`
Expected: `Ran 6 tests ... OK`

- [ ] **Step 9: Add failing tests for `advance_phase`**

Append to `GameEngineTests`:

```python
    def _seed_round(self, number=1, phase=Round.PHASE_SUBMITTING):
        return Round.objects.create(
            room=self.room,
            number=number,
            phase=phase,
            phase_deadline=timezone.now() + timedelta(seconds=1),
        )

    def test_advance_submitting_to_voting(self):
        r = self._seed_round(phase=Round.PHASE_SUBMITTING)
        out = game.advance_phase(r)
        self.assertEqual(out.pk, r.pk)
        self.assertEqual(out.phase, Round.PHASE_VOTING)
        self.assertLessEqual(
            out.phase_deadline,
            timezone.now() + timedelta(seconds=game.VOTING_SECONDS + 1),
        )

    def test_advance_voting_to_results(self):
        r = self._seed_round(phase=Round.PHASE_VOTING)
        out = game.advance_phase(r)
        self.assertEqual(out.phase, Round.PHASE_RESULTS)

    def test_advance_results_creates_next_round(self):
        r = self._seed_round(number=3, phase=Round.PHASE_RESULTS)
        out = game.advance_phase(r)
        self.assertNotEqual(out.pk, r.pk)
        self.assertEqual(out.number, 4)
        self.assertEqual(out.phase, Round.PHASE_SUBMITTING)
        # Old round unchanged (still results).
        r.refresh_from_db()
        self.assertEqual(r.phase, Round.PHASE_RESULTS)

    def test_advance_results_of_last_round_finishes_game(self):
        self.room.status = GameRoom.STATUS_PLAYING
        self.room.save()
        r = self._seed_round(number=game.TOTAL_ROUNDS, phase=Round.PHASE_RESULTS)
        out = game.advance_phase(r)
        self.room.refresh_from_db()
        self.assertEqual(out.phase, Round.PHASE_DONE)
        self.assertEqual(self.room.status, GameRoom.STATUS_FINISHED)
```

- [ ] **Step 10: Run — expect failure**

Run: `cd backend && python manage.py test app.tests.GameEngineTests -v 2`
Expected: failures on the four `test_advance_*` tests — `advance_phase` not defined.

- [ ] **Step 11: Implement `advance_phase`**

Append to `backend/app/game.py`:

```python
def advance_phase(round: Round) -> Round:
    now = timezone.now()
    if round.phase == Round.PHASE_SUBMITTING:
        round.phase = Round.PHASE_VOTING
        round.phase_deadline = now + timedelta(seconds=VOTING_SECONDS)
        round.save(update_fields=['phase', 'phase_deadline'])
        return round

    if round.phase == Round.PHASE_VOTING:
        round.phase = Round.PHASE_RESULTS
        round.phase_deadline = now + timedelta(seconds=RESULTS_SECONDS)
        round.save(update_fields=['phase', 'phase_deadline'])
        return round

    if round.phase == Round.PHASE_RESULTS:
        if round.number < TOTAL_ROUNDS:
            return Round.objects.create(
                room=round.room,
                number=round.number + 1,
                phase=Round.PHASE_SUBMITTING,
                phase_deadline=now + timedelta(seconds=SUBMITTING_SECONDS),
            )
        # Last round — finish game.
        round.phase = Round.PHASE_DONE
        round.phase_deadline = now
        round.save(update_fields=['phase', 'phase_deadline'])
        room = round.room
        room.status = GameRoom.STATUS_FINISHED
        room.save(update_fields=['status'])
        return round

    raise ValueError(f'advance_phase called on round in phase {round.phase}')
```

- [ ] **Step 12: Re-run — expect PASS**

Run: `cd backend && python manage.py test app.tests.GameEngineTests -v 2`
Expected: `Ran 10 tests ... OK`

- [ ] **Step 13: Add failing test for `reset_game`**

Append to `GameEngineTests`:

```python
    def test_reset_game_clears_rounds_players_and_resets_status(self):
        for u in self.users[:4]:
            game.add_player(self.room, u)
        game.start_game(self.room)
        game.advance_phase(Round.objects.first())
        self.room.refresh_from_db()
        self.assertEqual(self.room.status, GameRoom.STATUS_PLAYING)

        self.room.status = GameRoom.STATUS_FINISHED
        self.room.save()
        game.reset_game(self.room)
        self.room.refresh_from_db()
        self.assertEqual(self.room.status, GameRoom.STATUS_WAITING)
        self.assertEqual(self.room.players.count(), 0)
        self.assertEqual(Round.objects.filter(room=self.room).count(), 0)
```

- [ ] **Step 14: Run — expect failure**

Run: `cd backend && python manage.py test app.tests.GameEngineTests.test_reset_game_clears_rounds_players_and_resets_status -v 2`
Expected: `AttributeError: module 'app.game' has no attribute 'reset_game'`.

- [ ] **Step 15: Implement `reset_game`**

Append to `backend/app/game.py`:

```python
def reset_game(room: GameRoom) -> None:
    Round.objects.filter(room=room).delete()
    room.players.clear()
    room.status = GameRoom.STATUS_WAITING
    room.save(update_fields=['status'])
```

- [ ] **Step 16: Re-run — expect PASS**

Run: `cd backend && python manage.py test app.tests.GameEngineTests -v 2`
Expected: `Ran 11 tests ... OK`

- [ ] **Step 17: Commit**

```bash
git add backend/app/game.py backend/app/tests.py
git commit -m "feat(game): phase state machine with full TDD coverage"
```

---

### Task 9: WebSocket JWT middleware

**Files:**
- Create: `backend/app/ws_auth.py`

- [ ] **Step 1: Create `backend/app/ws_auth.py`**

```python
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
```

- [ ] **Step 2: Sanity-import**

Run: `cd backend && python -c "from app.ws_auth import JWTAuthMiddleware; print(JWTAuthMiddleware)"`
Expected: `<class 'app.ws_auth.JWTAuthMiddleware'>`

- [ ] **Step 3: Commit**

```bash
git add backend/app/ws_auth.py
git commit -m "feat(ws): JWT auth middleware for channels"
```

---

### Task 10: GameConsumer + broadcast + phase loop

**Files:**
- Create: `backend/app/consumers.py`
- Create: `backend/app/routing.py`
- Modify: `backend/memearena/asgi.py`

- [ ] **Step 1: Create `backend/app/consumers.py`**

```python
import asyncio
import logging

from asgiref.sync import sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.layers import get_channel_layer
from django.utils import timezone

from . import game
from .models import GameRoom, Round

log = logging.getLogger(__name__)

GROUP_NAME = 'game'


def _serialize_state() -> dict:
    room = game.get_room()
    players = [{'id': u.id, 'username': u.username} for u in room.players.all()]
    current = room.rounds.first()  # ordering=['-number']
    current_dto = None
    if current is not None:
        current_dto = {
            'number': current.number,
            'phase': current.phase,
            'phase_deadline': current.phase_deadline.isoformat(),
        }
    return {
        'type': 'state',
        'payload': {
            'room': {'status': room.status},
            'players': players,
            'current_round': current_dto,
        },
    }


async def broadcast_state() -> None:
    snapshot = await sync_to_async(_serialize_state)()
    layer = get_channel_layer()
    await layer.group_send(GROUP_NAME, {'type': 'state.event', 'payload': snapshot})


class GameConsumer(AsyncJsonWebsocketConsumer):
    _phase_task: asyncio.Task | None = None

    async def connect(self):
        if self.scope['user'].is_anonymous:
            await self.close(code=4401)
            return

        await self.channel_layer.group_add(GROUP_NAME, self.channel_name)
        await self.accept()

        room = await sync_to_async(game.get_room)()
        added = await sync_to_async(game.add_player)(room, self.scope['user'])

        if added and await sync_to_async(lambda: room.players.count())() == 4:
            await sync_to_async(game.start_game)(room)

        room = await sync_to_async(game.get_room)()
        if room.status == GameRoom.STATUS_PLAYING:
            GameConsumer._ensure_phase_loop()

        await broadcast_state()

    async def disconnect(self, code):
        await self.channel_layer.group_discard(GROUP_NAME, self.channel_name)

    async def state_event(self, event):
        await self.send_json(event['payload'])

    @classmethod
    def _ensure_phase_loop(cls):
        if cls._phase_task is None or cls._phase_task.done():
            cls._phase_task = asyncio.create_task(cls._phase_loop())

    @classmethod
    async def _phase_loop(cls):
        try:
            while True:
                room = await sync_to_async(game.get_room)()
                if room.status != GameRoom.STATUS_PLAYING:
                    await asyncio.sleep(game.RESET_DELAY_SECONDS)
                    await sync_to_async(game.reset_game)(room)
                    await broadcast_state()
                    return
                current = await sync_to_async(lambda: room.rounds.first())()
                if current is None:
                    return
                delay = (current.phase_deadline - timezone.now()).total_seconds()
                await asyncio.sleep(max(0, delay))
                await sync_to_async(game.advance_phase)(current)
                await broadcast_state()
        except Exception:
            log.exception('phase loop crashed')
            raise
```

- [ ] **Step 2: Create `backend/app/routing.py`**

```python
from django.urls import path

from .consumers import GameConsumer

websocket_urlpatterns = [
    path('ws/game/', GameConsumer.as_asgi()),
]
```

- [ ] **Step 3: Replace `backend/memearena/asgi.py`**

```python
import os

from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'memearena.settings')

django_asgi_app = get_asgi_application()

from app.routing import websocket_urlpatterns  # noqa: E402 (must come after settings)
from app.ws_auth import JWTAuthMiddleware  # noqa: E402

application = ProtocolTypeRouter({
    'http': django_asgi_app,
    'websocket': JWTAuthMiddleware(URLRouter(websocket_urlpatterns)),
})
```

- [ ] **Step 4: Verify Django + Channels load**

Run: `cd backend && python manage.py check`
Expected: `System check identified no issues (0 silenced).`

Run: `cd backend && python -c "from memearena.asgi import application; print(application)"`
Expected: `<channels.routing.ProtocolTypeRouter object at 0x...>`

- [ ] **Step 5: Commit**

```bash
git add backend/app/consumers.py backend/app/routing.py backend/memearena/asgi.py
git commit -m "feat(ws): GameConsumer, phase loop, ASGI wiring"
```

---

### Task 11: WebSocket integration smoke test

Two tests: a happy-path 4-connect that asserts the `status=playing` broadcast after the 4th connect, and an anonymous-reject test. Kept simple — no monkey-patching of timers (we assert on the broadcast that fires immediately on connect, not on loop-driven transitions). `asyncio.run` wraps the async bodies; `TransactionTestCase` gives DB isolation that plays nicely with async ORM.

**Files:**
- Modify: `backend/app/tests.py`

- [ ] **Step 1: Append the WS tests to `backend/app/tests.py`**

Add at the top of `tests.py` (merge with existing imports):

```python
import asyncio

from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.test import TransactionTestCase
from rest_framework_simplejwt.tokens import RefreshToken

from memearena.asgi import application
from app.consumers import GameConsumer
```

Then append the test classes:

```python
class GameWebSocketTests(TransactionTestCase):
    def setUp(self):
        # Reset any phase-loop task left over by a previous test so tasks
        # don't leak across event loops.
        task = GameConsumer._phase_task
        if task is not None and not task.done():
            task.cancel()
        GameConsumer._phase_task = None
        # Ensure the singleton room exists and is clean.
        GameRoom.objects.update_or_create(
            pk=1, defaults={'name': 'arena', 'status': 'waiting'}
        )
        GameRoom.objects.get(pk=1).players.clear()
        Round.objects.all().delete()

    def test_rejects_anonymous_connection(self):
        async def inner():
            comm = WebsocketCommunicator(application, '/ws/game/?token=invalid')
            connected, _ = await comm.connect()
            self.assertFalse(connected)
        asyncio.run(inner())

    def test_four_connects_start_game_and_broadcast_playing(self):
        async def connect_as(username):
            user = await database_sync_to_async(User.objects.create_user)(
                username=username, password='x'
            )
            token = str(RefreshToken.for_user(user).access_token)
            comm = WebsocketCommunicator(application, f'/ws/game/?token={token}')
            connected, _ = await comm.connect()
            self.assertTrue(connected, f'{username} failed to connect')
            return comm

        async def inner():
            comms = []
            for i in range(4):
                comms.append(await connect_as(f'ws{i}'))

            # On the 4th connect, start_game runs and broadcast_state fires.
            # Drain messages until we see status=='playing' on the last comm,
            # which shares the group with all other connects.
            seen_playing = False
            try:
                for _ in range(10):  # cap iterations so the test can't hang
                    msg = await asyncio.wait_for(
                        comms[-1].receive_json_from(), timeout=2.0
                    )
                    if msg['payload']['room']['status'] == 'playing':
                        seen_playing = True
                        break
            except asyncio.TimeoutError:
                pass

            for comm in comms:
                await comm.disconnect()

            self.assertTrue(seen_playing, 'never saw status=playing in broadcasts')

        asyncio.run(inner())
```

- [ ] **Step 2: Run the WS test suite**

Run: `cd backend && python manage.py test app.tests.GameWebSocketTests -v 2`
Expected: `Ran 2 tests ... OK`.

> If `test_four_connects_start_game_and_broadcast_playing` times out, confirm `CHANNEL_LAYERS` uses `InMemoryChannelLayer` (Task 3) and that `daphne` is first in `INSTALLED_APPS`.

- [ ] **Step 3: Run ALL backend tests to confirm no regressions**

Run: `cd backend && python manage.py test app -v 2`
Expected: all tests (auth, engine, WS) pass.

- [ ] **Step 4: Commit**

```bash
git add backend/app/tests.py
git commit -m "test(ws): integration tests for 4-connect start and anonymous reject"
```

---

### Task 12: Frontend environment + TS models

**Files:**
- Create: `frontend/src/environments/environment.ts`
- Create: `frontend/src/environments/environment.development.ts`
- Create: `frontend/src/app/core/models.ts`

- [ ] **Step 1: Create the two environment files**

Create `frontend/src/environments/environment.ts`:

```typescript
export const environment = {
  production: true,
  apiUrl: 'http://localhost:8000',
  wsUrl: 'ws://localhost:8000',
};
```

Create `frontend/src/environments/environment.development.ts`:

```typescript
export const environment = {
  production: false,
  apiUrl: 'http://localhost:8000',
  wsUrl: 'ws://localhost:8000',
};
```

- [ ] **Step 2: Create `frontend/src/app/core/models.ts`**

```typescript
export interface User {
  id: number;
  username: string;
}

export interface AuthTokens {
  access: string;
  refresh: string;
  username: string;
}

export interface Player {
  id: number;
  username: string;
}

export type Phase = 'submitting' | 'voting' | 'results' | 'done';
export type RoomStatus = 'waiting' | 'playing' | 'finished';

export interface RoundDto {
  number: number;
  phase: Phase;
  phase_deadline: string;
}

export interface GameState {
  room: { status: RoomStatus };
  players: Player[];
  current_round: RoundDto | null;
}

export interface StateMessage {
  type: 'state';
  payload: GameState;
}
```

- [ ] **Step 3: Verify TS compiles**

Run: `cd frontend && npx tsc --noEmit -p tsconfig.json`
Expected: no output (success).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/environments frontend/src/app/core/models.ts
git commit -m "feat(frontend): environment config and TS models"
```

---

### Task 13: AuthService

**Files:**
- Create: `frontend/src/app/core/auth.service.ts`
- Create: `frontend/src/app/core/auth.service.spec.ts`

- [ ] **Step 1: Write the failing spec**

Create `frontend/src/app/core/auth.service.spec.ts`:

```typescript
import { TestBed } from '@angular/core/testing';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideRouter } from '@angular/router';
import { describe, it, expect, beforeEach, afterEach } from 'vitest';

import { AuthService } from './auth.service';
import { environment } from '../../environments/environment';

describe('AuthService', () => {
  let svc: AuthService;
  let httpCtrl: HttpTestingController;

  beforeEach(() => {
    localStorage.clear();
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
        AuthService,
      ],
    });
    svc = TestBed.inject(AuthService);
    httpCtrl = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpCtrl.verify();
    localStorage.clear();
  });

  it('login stores access and refresh and username', async () => {
    const p = svc.login('alice', 'pw');
    const req = httpCtrl.expectOne(`${environment.apiUrl}/api/auth/login/`);
    expect(req.request.method).toBe('POST');
    req.flush({ access: 'A', refresh: 'R', username: 'alice', message: 'ok' });
    await p;
    expect(localStorage.getItem('access')).toBe('A');
    expect(localStorage.getItem('refresh')).toBe('R');
    expect(svc.token()).toBe('A');
    expect(svc.currentUser()?.username).toBe('alice');
  });

  it('logout clears tokens and user', async () => {
    localStorage.setItem('access', 'A');
    localStorage.setItem('refresh', 'R');
    localStorage.setItem('username', 'alice');
    const svc2 = TestBed.inject(AuthService);
    svc2.logout();
    // logout fires a POST to blacklist; swallow it.
    const req = httpCtrl.expectOne(`${environment.apiUrl}/api/auth/logout/`);
    req.flush({ message: 'ok' });
    expect(localStorage.getItem('access')).toBeNull();
    expect(svc2.token()).toBeNull();
    expect(svc2.currentUser()).toBeNull();
  });
});
```

- [ ] **Step 2: Run spec — expect failure (no `AuthService` yet)**

Run: `cd frontend && npx ng test --watch=false --include=src/app/core/auth.service.spec.ts`
Expected: compilation error — `Cannot find module './auth.service'`.

- [ ] **Step 3: Implement `frontend/src/app/core/auth.service.ts`**

```typescript
import { HttpClient } from '@angular/common/http';
import { Injectable, computed, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { firstValueFrom } from 'rxjs';

import { environment } from '../../environments/environment';
import { AuthTokens, User } from './models';

const ACCESS_KEY = 'access';
const REFRESH_KEY = 'refresh';
const USERNAME_KEY = 'username';

@Injectable({ providedIn: 'root' })
export class AuthService {
  private http = inject(HttpClient);
  private router = inject(Router);

  private accessSig = signal<string | null>(localStorage.getItem(ACCESS_KEY));
  private refreshSig = signal<string | null>(localStorage.getItem(REFRESH_KEY));
  private userSig = signal<User | null>(this.hydrateUser());

  token = computed(() => this.accessSig());
  currentUser = computed(() => this.userSig());

  private hydrateUser(): User | null {
    const name = localStorage.getItem(USERNAME_KEY);
    return name ? { id: 0, username: name } : null;
  }

  async register(username: string, password: string): Promise<void> {
    await firstValueFrom(
      this.http.post(`${environment.apiUrl}/api/auth/register/`, { username, password }),
    );
    await this.login(username, password);
  }

  async login(username: string, password: string): Promise<void> {
    const tokens = await firstValueFrom(
      this.http.post<AuthTokens>(`${environment.apiUrl}/api/auth/login/`, {
        username,
        password,
      }),
    );
    localStorage.setItem(ACCESS_KEY, tokens.access);
    localStorage.setItem(REFRESH_KEY, tokens.refresh);
    localStorage.setItem(USERNAME_KEY, tokens.username);
    this.accessSig.set(tokens.access);
    this.refreshSig.set(tokens.refresh);
    this.userSig.set({ id: 0, username: tokens.username });
  }

  logout(): void {
    const refresh = this.refreshSig();
    if (refresh) {
      this.http
        .post(`${environment.apiUrl}/api/auth/logout/`, { refresh })
        .subscribe({ error: () => {} });
    }
    localStorage.removeItem(ACCESS_KEY);
    localStorage.removeItem(REFRESH_KEY);
    localStorage.removeItem(USERNAME_KEY);
    this.accessSig.set(null);
    this.refreshSig.set(null);
    this.userSig.set(null);
    this.router.navigate(['/login']);
  }
}
```

- [ ] **Step 4: Re-run spec**

Run: `cd frontend && npx ng test --watch=false --include=src/app/core/auth.service.spec.ts`
Expected: both tests pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/core/auth.service.ts frontend/src/app/core/auth.service.spec.ts
git commit -m "feat(frontend): AuthService with JWT storage and signals"
```

---

### Task 14: authInterceptor + authGuard

**Files:**
- Create: `frontend/src/app/core/auth.interceptor.ts`
- Create: `frontend/src/app/core/auth.guard.ts`

- [ ] **Step 1: Create `frontend/src/app/core/auth.interceptor.ts`**

```typescript
import { HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';

import { AuthService } from './auth.service';

const PUBLIC_PATHS = ['/api/auth/login/', '/api/auth/register/', '/api/auth/refresh/'];

export const authInterceptor: HttpInterceptorFn = (req, next) => {
  if (PUBLIC_PATHS.some((p) => req.url.endsWith(p))) {
    return next(req);
  }
  const token = inject(AuthService).token();
  if (!token) return next(req);
  return next(
    req.clone({ setHeaders: { Authorization: `Bearer ${token}` } }),
  );
};
```

- [ ] **Step 2: Create `frontend/src/app/core/auth.guard.ts`**

```typescript
import { CanActivateFn, Router } from '@angular/router';
import { inject } from '@angular/core';

import { AuthService } from './auth.service';

export const authGuard: CanActivateFn = () => {
  const auth = inject(AuthService);
  const router = inject(Router);
  if (auth.token()) return true;
  router.navigate(['/login']);
  return false;
};
```

- [ ] **Step 3: Verify TS compiles**

Run: `cd frontend && npx tsc --noEmit -p tsconfig.json`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/core/auth.interceptor.ts frontend/src/app/core/auth.guard.ts
git commit -m "feat(frontend): auth HTTP interceptor and route guard"
```

---

### Task 15: WsService

**Files:**
- Create: `frontend/src/app/core/ws.service.ts`

- [ ] **Step 1: Create `frontend/src/app/core/ws.service.ts`**

```typescript
import { Injectable } from '@angular/core';
import { Subject } from 'rxjs';

import { environment } from '../../environments/environment';
import { StateMessage } from './models';

const MAX_RECONNECT = 5;
const RECONNECT_DELAY_MS = 1000;

@Injectable({ providedIn: 'root' })
export class WsService {
  readonly message$ = new Subject<StateMessage>();

  private socket: WebSocket | null = null;
  private token: string | null = null;
  private reconnectAttempts = 0;
  private shouldReconnect = false;

  connect(token: string): void {
    this.token = token;
    this.shouldReconnect = true;
    this.reconnectAttempts = 0;
    this.open();
  }

  disconnect(): void {
    this.shouldReconnect = false;
    this.socket?.close(1000, 'client disconnect');
    this.socket = null;
  }

  private open(): void {
    const url = `${environment.wsUrl}/ws/game/?token=${encodeURIComponent(this.token ?? '')}`;
    const sock = new WebSocket(url);
    this.socket = sock;
    sock.onmessage = (ev) => {
      try {
        this.message$.next(JSON.parse(ev.data) as StateMessage);
      } catch {
        /* ignore malformed */
      }
    };
    sock.onclose = (ev) => {
      this.socket = null;
      if (ev.code === 4401) {
        this.message$.error(new Error('unauthorized'));
        return;
      }
      if (!this.shouldReconnect) return;
      if (this.reconnectAttempts >= MAX_RECONNECT) return;
      this.reconnectAttempts += 1;
      setTimeout(() => this.open(), RECONNECT_DELAY_MS);
    };
  }
}
```

- [ ] **Step 2: Verify TS compiles**

Run: `cd frontend && npx tsc --noEmit -p tsconfig.json`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/core/ws.service.ts
git commit -m "feat(frontend): WsService with reconnect and 4401 handling"
```

---

### Task 16: GameStateService + spec

**Files:**
- Create: `frontend/src/app/core/game-state.service.ts`
- Create: `frontend/src/app/core/game-state.service.spec.ts`

- [ ] **Step 1: Write the failing spec**

Create `frontend/src/app/core/game-state.service.spec.ts`:

```typescript
import { TestBed } from '@angular/core/testing';
import { Subject } from 'rxjs';
import { describe, it, expect, beforeEach } from 'vitest';

import { GameStateService } from './game-state.service';
import { WsService } from './ws.service';
import { StateMessage } from './models';

class FakeWs {
  message$ = new Subject<StateMessage>();
}

describe('GameStateService', () => {
  let svc: GameStateService;
  let fakeWs: FakeWs;

  beforeEach(() => {
    fakeWs = new FakeWs();
    TestBed.configureTestingModule({
      providers: [
        GameStateService,
        { provide: WsService, useValue: fakeWs },
      ],
    });
    svc = TestBed.inject(GameStateService);
  });

  it('initial signals are empty', () => {
    expect(svc.status()).toBe('waiting');
    expect(svc.players()).toEqual([]);
    expect(svc.currentRound()).toBeNull();
  });

  it('absorbs a state message into signals', () => {
    fakeWs.message$.next({
      type: 'state',
      payload: {
        room: { status: 'playing' },
        players: [{ id: 1, username: 'alice' }],
        current_round: { number: 3, phase: 'voting', phase_deadline: '2026-04-22T10:00:00Z' },
      },
    });
    expect(svc.status()).toBe('playing');
    expect(svc.players()).toEqual([{ id: 1, username: 'alice' }]);
    expect(svc.currentRound()?.number).toBe(3);
  });
});
```

- [ ] **Step 2: Run spec — expect failure (module missing)**

Run: `cd frontend && npx ng test --watch=false --include=src/app/core/game-state.service.spec.ts`
Expected: compile error.

- [ ] **Step 3: Implement `frontend/src/app/core/game-state.service.ts`**

```typescript
import { Injectable, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';

import { Player, RoomStatus, RoundDto, StateMessage } from './models';
import { WsService } from './ws.service';

@Injectable({ providedIn: 'root' })
export class GameStateService {
  private ws = inject(WsService);

  readonly status = signal<RoomStatus>('waiting');
  readonly players = signal<Player[]>([]);
  readonly currentRound = signal<RoundDto | null>(null);

  constructor() {
    this.ws.message$.pipe(takeUntilDestroyed()).subscribe((msg: StateMessage) => {
      if (msg.type !== 'state') return;
      this.status.set(msg.payload.room.status);
      this.players.set(msg.payload.players);
      this.currentRound.set(msg.payload.current_round);
    });
  }
}
```

- [ ] **Step 4: Re-run spec**

Run: `cd frontend && npx ng test --watch=false --include=src/app/core/game-state.service.spec.ts`
Expected: both tests pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/core/game-state.service.ts frontend/src/app/core/game-state.service.spec.ts
git commit -m "feat(frontend): GameStateService backed by signals"
```

---

### Task 17: LoginComponent

**Files:**
- Create: `frontend/src/app/pages/login/login.ts`
- Create: `frontend/src/app/pages/login/login.html`
- Create: `frontend/src/app/pages/login/login.css`

- [ ] **Step 1: Create the component TS**

```typescript
// frontend/src/app/pages/login/login.ts
import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';

import { AuthService } from '../../core/auth.service';

@Component({
  selector: 'app-login',
  standalone: true,
  imports: [FormsModule],
  templateUrl: './login.html',
  styleUrl: './login.css',
})
export class LoginComponent {
  private auth = inject(AuthService);
  private router = inject(Router);

  mode = signal<'login' | 'register'>('login');
  username = '';
  password = '';
  error = signal<string | null>(null);
  busy = signal(false);

  setMode(m: 'login' | 'register') {
    this.mode.set(m);
    this.error.set(null);
  }

  async submit() {
    if (!this.username || !this.password) {
      this.error.set('Username and password are required');
      return;
    }
    this.busy.set(true);
    this.error.set(null);
    try {
      if (this.mode() === 'register') {
        await this.auth.register(this.username, this.password);
      } else {
        await this.auth.login(this.username, this.password);
      }
      this.router.navigate(['/game']);
    } catch (e: any) {
      const detail = e?.error?.detail ?? e?.error ?? e?.message ?? 'Request failed';
      this.error.set(typeof detail === 'string' ? detail : JSON.stringify(detail));
    } finally {
      this.busy.set(false);
    }
  }
}
```

- [ ] **Step 2: Create the template**

```html
<!-- frontend/src/app/pages/login/login.html -->
<section class="login">
  <h1>MemeArena</h1>
  <nav class="tabs">
    <button
      type="button"
      [class.active]="mode() === 'login'"
      (click)="setMode('login')"
    >Login</button>
    <button
      type="button"
      [class.active]="mode() === 'register'"
      (click)="setMode('register')"
    >Register</button>
  </nav>

  <form (submit)="$event.preventDefault(); submit()">
    <label>
      Username
      <input name="username" [(ngModel)]="username" autocomplete="username" required />
    </label>
    <label>
      Password
      <input
        name="password"
        type="password"
        [(ngModel)]="password"
        autocomplete="current-password"
        required
      />
    </label>
    @if (error()) {
      <p class="err">{{ error() }}</p>
    }
    <button type="submit" [disabled]="busy()">
      {{ mode() === 'login' ? 'Log in' : 'Create account' }}
    </button>
  </form>
</section>
```

- [ ] **Step 3: Create the styles**

```css
/* frontend/src/app/pages/login/login.css */
.login {
  max-width: 360px;
  margin: 8vh auto;
  padding: 24px;
  font-family: system-ui, sans-serif;
}
.login h1 { text-align: center; margin-bottom: 16px; }
.tabs { display: flex; gap: 8px; margin-bottom: 16px; }
.tabs button {
  flex: 1;
  padding: 8px;
  background: #eee;
  border: 1px solid #ccc;
  cursor: pointer;
}
.tabs button.active { background: #333; color: #fff; }
form { display: flex; flex-direction: column; gap: 12px; }
label { display: flex; flex-direction: column; font-size: 14px; }
input { padding: 6px; font: inherit; border: 1px solid #ccc; }
.err { color: #b00; margin: 0; }
button[type='submit'] {
  padding: 10px;
  background: #222;
  color: #fff;
  border: none;
  cursor: pointer;
}
button[type='submit']:disabled { opacity: 0.5; }
```

- [ ] **Step 4: Verify TS compiles**

Run: `cd frontend && npx tsc --noEmit -p tsconfig.json`
Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/pages/login
git commit -m "feat(frontend): LoginComponent with register/login tabs"
```

---

### Task 18: Timer + PlayerBadge components

**Files:**
- Create: `frontend/src/app/components/timer/timer.ts`, `.html`, `.css`
- Create: `frontend/src/app/components/player-badge/player-badge.ts`, `.html`, `.css`

- [ ] **Step 1: Create `Timer`**

```typescript
// frontend/src/app/components/timer/timer.ts
import { Component, DestroyRef, Input, OnChanges, SimpleChanges, inject, signal } from '@angular/core';

@Component({
  selector: 'app-timer',
  standalone: true,
  templateUrl: './timer.html',
  styleUrl: './timer.css',
})
export class TimerComponent implements OnChanges {
  @Input() deadline: string | null = null;

  private destroyRef = inject(DestroyRef);
  private handle: ReturnType<typeof setInterval> | null = null;

  readonly remaining = signal('—');

  ngOnChanges(changes: SimpleChanges): void {
    this.stop();
    if (!this.deadline) {
      this.remaining.set('—');
      return;
    }
    this.tick();
    this.handle = setInterval(() => this.tick(), 100);
    this.destroyRef.onDestroy(() => this.stop());
  }

  private stop(): void {
    if (this.handle) {
      clearInterval(this.handle);
      this.handle = null;
    }
  }

  private tick(): void {
    if (!this.deadline) return;
    const ms = Math.max(0, new Date(this.deadline).getTime() - Date.now());
    this.remaining.set((ms / 1000).toFixed(1) + 's');
    if (ms === 0) this.stop();
  }
}
```

```html
<!-- frontend/src/app/components/timer/timer.html -->
<span class="timer">{{ remaining() }}</span>
```

```css
/* frontend/src/app/components/timer/timer.css */
.timer { font-family: monospace; font-size: 1.2em; }
```

- [ ] **Step 2: Create `PlayerBadge`**

```typescript
// frontend/src/app/components/player-badge/player-badge.ts
import { Component, Input } from '@angular/core';

import { Player } from '../../core/models';

@Component({
  selector: 'app-player-badge',
  standalone: true,
  templateUrl: './player-badge.html',
  styleUrl: './player-badge.css',
})
export class PlayerBadgeComponent {
  @Input({ required: true }) player!: Player;
}
```

```html
<!-- frontend/src/app/components/player-badge/player-badge.html -->
<span class="badge">{{ player.username }}</span>
```

```css
/* frontend/src/app/components/player-badge/player-badge.css */
.badge {
  display: inline-block;
  padding: 4px 10px;
  background: #eef;
  border-radius: 12px;
  font-size: 14px;
}
```

- [ ] **Step 3: Verify TS compiles**

Run: `cd frontend && npx tsc --noEmit -p tsconfig.json`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/components/timer frontend/src/app/components/player-badge
git commit -m "feat(frontend): Timer and PlayerBadge components"
```

---

### Task 19: GameComponent (placeholder viewer)

**Files:**
- Create: `frontend/src/app/pages/game/game.ts`
- Create: `frontend/src/app/pages/game/game.html`
- Create: `frontend/src/app/pages/game/game.css`

- [ ] **Step 1: Create the component TS**

```typescript
// frontend/src/app/pages/game/game.ts
import { Component, OnDestroy, OnInit, inject } from '@angular/core';

import { AuthService } from '../../core/auth.service';
import { GameStateService } from '../../core/game-state.service';
import { WsService } from '../../core/ws.service';
import { PlayerBadgeComponent } from '../../components/player-badge/player-badge';
import { TimerComponent } from '../../components/timer/timer';

@Component({
  selector: 'app-game',
  standalone: true,
  imports: [PlayerBadgeComponent, TimerComponent],
  templateUrl: './game.html',
  styleUrl: './game.css',
})
export class GameComponent implements OnInit, OnDestroy {
  private auth = inject(AuthService);
  private ws = inject(WsService);
  protected state = inject(GameStateService);

  ngOnInit(): void {
    const token = this.auth.token();
    if (token) this.ws.connect(token);
  }

  ngOnDestroy(): void {
    this.ws.disconnect();
  }

  logout() {
    this.auth.logout();
  }
}
```

- [ ] **Step 2: Create the template**

```html
<!-- frontend/src/app/pages/game/game.html -->
<section class="game">
  <header>
    <h1>MemeArena</h1>
    <button type="button" class="logout" (click)="logout()">Log out</button>
  </header>

  <p class="status">Status: <strong>{{ state.status() }}</strong></p>

  <h3>Players ({{ state.players().length }}/4)</h3>
  <div class="players">
    @for (p of state.players(); track p.id) {
      <app-player-badge [player]="p"></app-player-badge>
    }
    @if (state.players().length === 0) {
      <em>no one yet</em>
    }
  </div>

  @if (state.currentRound(); as r) {
    <section class="round">
      <h3>Round {{ r.number }}/8 — phase: {{ r.phase }}</h3>
      <p>Time left: <app-timer [deadline]="r.phase_deadline"></app-timer></p>
    </section>
  } @else if (state.status() === 'waiting') {
    <p>Waiting for players…</p>
  } @else if (state.status() === 'finished') {
    <p>Game over — resetting in 10s…</p>
  }
</section>
```

- [ ] **Step 3: Create the styles**

```css
/* frontend/src/app/pages/game/game.css */
.game {
  max-width: 600px;
  margin: 24px auto;
  padding: 16px;
  font-family: system-ui, sans-serif;
}
.game header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.logout {
  background: transparent;
  border: 1px solid #888;
  padding: 4px 10px;
  cursor: pointer;
}
.players {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.round {
  margin-top: 16px;
  padding: 12px;
  background: #f7f7f7;
  border-radius: 6px;
}
```

- [ ] **Step 4: Verify TS compiles**

Run: `cd frontend && npx tsc --noEmit -p tsconfig.json`
Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/pages/game
git commit -m "feat(frontend): GameComponent placeholder viewer"
```

---

### Task 20: Wire routes, app config, and strip card-hand from root

**Files:**
- Modify: `frontend/src/app/app.routes.ts`
- Modify: `frontend/src/app/app.config.ts`
- Modify: `frontend/src/app/app.ts`
- Modify: `frontend/src/app/app.html`

- [ ] **Step 1: Rewrite `app.routes.ts`**

```typescript
// frontend/src/app/app.routes.ts
import { Routes } from '@angular/router';

import { authGuard } from './core/auth.guard';

export const routes: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'game' },
  {
    path: 'login',
    loadComponent: () =>
      import('./pages/login/login').then((m) => m.LoginComponent),
  },
  {
    path: 'game',
    canActivate: [authGuard],
    loadComponent: () =>
      import('./pages/game/game').then((m) => m.GameComponent),
  },
  { path: '**', redirectTo: 'login' },
];
```

- [ ] **Step 2: Rewrite `app.config.ts`**

```typescript
// frontend/src/app/app.config.ts
import { ApplicationConfig, provideBrowserGlobalErrorListeners } from '@angular/core';
import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { provideRouter } from '@angular/router';

import { authInterceptor } from './core/auth.interceptor';
import { routes } from './app.routes';

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    provideRouter(routes),
    provideHttpClient(withInterceptors([authInterceptor])),
  ],
};
```

- [ ] **Step 3: Replace `app.ts`**

```typescript
// frontend/src/app/app.ts
import { Component } from '@angular/core';
import { RouterOutlet } from '@angular/router';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [RouterOutlet],
  templateUrl: './app.html',
  styleUrl: './app.css',
})
export class App {}
```

- [ ] **Step 4: Replace `app.html`**

```html
<!-- frontend/src/app/app.html -->
<router-outlet />
```

- [ ] **Step 5: Build check**

Run: `cd frontend && npx ng build --configuration development`
Expected: build completes without errors. Bundle produced under `dist/frontend/`.

- [ ] **Step 6: Run all frontend tests**

Run: `cd frontend && npx ng test --watch=false`
Expected: all specs pass.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/app/app.routes.ts frontend/src/app/app.config.ts frontend/src/app/app.ts frontend/src/app/app.html
git commit -m "feat(frontend): wire routes, HTTP client, and router outlet"
```

---

### Task 21: Manual end-to-end smoke test

No automated E2E in this iteration — we verify the integration by driving the real stack with four browser sessions.

**Files:** none

- [ ] **Step 1: Start the backend**

Run (in terminal 1): `cd backend && python manage.py runserver 8000`
Expected: Starts with "Daphne running on …" (because `daphne` is first in `INSTALLED_APPS`). Any reference to Channels in the startup log is expected.

- [ ] **Step 2: Start the frontend**

Run (in terminal 2): `cd frontend && npm start`
Expected: Angular dev server at `http://localhost:4200/`.

- [ ] **Step 3: Register and log in four users**

Open `http://localhost:4200/login` in **four separate incognito windows**. In each:
1. Click "Register", fill `p1`/`p2`/`p3`/`p4` with any password (`pw-12345`).
2. After redirect to `/game`, confirm the page shows the status and player list.

Expected after the **4th** window connects:
- All four pages show `Status: playing`.
- `Players (4/4)` listing all four usernames.
- `Round 1/8 — phase: submitting` with a countdown ticking down from ~30.0s.
- After 30s, phase switches to `voting` (20s), then `results` (5s), then `Round 2/8` starts.

- [ ] **Step 4: Let the game finish**

Wait ~8 × (30 + 20 + 5) = 440 seconds (~7:20) for all 8 rounds to complete. Expected final state:
- `Status: finished`, page shows "Game over — resetting in 10s…".
- After ~10s, `Status: waiting`, players list empty (all four cleared).

> If you don't want to wait: reduce phase constants in `backend/app/game.py` locally, restart the backend, and re-run this step. Revert the constants afterwards.

- [ ] **Step 5: Verify rejection of anonymous connect**

Run:
```bash
# From a shell with wscat or websocat installed. Skip if neither is available
# — the integration test in Task 11 already covers this.
wscat -c ws://localhost:8000/ws/game/?token=bogus
```
Expected: connection closed immediately with code 4401.

- [ ] **Step 6: Commit any dev-only notes (optional)**

If you added an `.env.example` or updated the README during smoke, commit:

```bash
git add <any touched files>
git commit -m "docs: smoke-test notes"
```

---

## Post-Implementation

Run the whole test suite one more time to confirm nothing regressed:

```bash
cd backend && python manage.py test app -v 2
cd frontend && npx ng test --watch=false
cd frontend && npx ng build --configuration development
```

All green? Skeleton is done. Next plan will add the card/meme/situation/vote layer on top.
