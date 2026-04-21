# MemeArena — Walking-Skeleton Design

**Date:** 2026-04-21
**Status:** Draft — pending user review
**Scope:** First iteration of the multiplayer MemeArena online game. This spec covers ONLY the foundation: authentication, frontend shell, and the server-side round/phase state machine. Deck/cards/situations/voting mechanics are deliberately postponed to a follow-up spec.

---

## 1. Context

Current state of the repo (as of commit `6afce32` by teammate, 2026-04-21):

- **Backend** (`backend/`, Django 6 + DRF + SQLite):
  - Auth (partial): `register_view` / `login_view` / `logout_view` FBVs with `djangorestframework-simplejwt` + `token_blacklist`. URL prefix is `app/` (not `/api/`).
  - Multi-room REST CRUD (`GameRoomListCreateView`, `SituationListCreateView`, `MemeListCreateView`, `MemeDetailView`) and `vote_for_meme` FBV — **these conflict with the singleton-room + WS + phase design of this spec and will be removed.**
  - Models: original `GameRoom / Situation / Meme / Vote` plus teammate-added fields (`Meme.caption/title`, `Situation.created_by/created_at`).
  - Settings: `rest_framework_simplejwt.token_blacklist` and `corsheaders` in `INSTALLED_APPS`; `corsheaders` is NOT in `MIDDLEWARE` and `CORS_ALLOWED_ORIGINS` is not set (broken). No `REST_FRAMEWORK` default auth, no `SIMPLE_JWT` config, no Channels, no ASGI.
  - **Known bugs in teammate's code** (see §3.10 for cleanup):
    - `vote_for_meme`: uses `Vote.user` — model has `voter`; missing `room`.
    - `MemeSerializer`: `author` field / `source='author.username'` / `perform_create(author=...)` — `Meme` has `player`, not `author`.
    - `MemeSerializer.get_votes_count`: `obj.votes.count()` — `Vote.meme` FK has no `related_name='votes'`; reverse is `vote_set`.
    - `GameRoomSerializer` / `GameRoomListCreateView.perform_create`: reference `created_by` — `GameRoom` has no such field.
    - `Situation.created_by` was added to the model but no migration exists.
  - Re-usable as-is (with tweaks): `RegisterSerializer`, `LoginSerializer`, `register_view`, `logout_view`, the `token_blacklist` wiring.
- **Frontend** (`frontend/`, Angular 21 + animejs): single component `card-hand/` that shows a visual demo — 4 hands around a table, cards flying to center on a 10-second loop. All memes are hardcoded, no backend calls, no routing, no auth. Untouched by teammate.

Target product: an online 4-player party game. Players see a situation prompt, each plays one meme from their hand, everyone votes (not for themselves), the most-voted meme wins the round. 8 rounds, highest score wins.

Decisions locked in during brainstorming:

- 4 players per room (exactly; game starts only when 4 have connected).
- 8 rounds; phase timers `submitting 30s / voting 20s / results 5s`.
- Round format: **voting** (everyone plays, everyone votes — not judge-style).
- Meme catalog: fixed set, images live in frontend `assets/`.
- Auth: full register/login with `djangorestframework-simplejwt` (JWT access + refresh).
- Real-time: **Django Channels + WebSocket** (server→client state broadcast only; client actions go through REST).
- One singleton shared room (no lobby, no room picker).
- Architecture style: "dead simple" — single Django app, DB as source of truth, `asyncio.create_task` timers in the WS consumer, no Celery, no Redis in dev.
- Disconnect is NOT a special case — game just keeps running on its timer; returning users reconnect by opening `/game` again.

## 2. Scope of this spec (walking skeleton)

**In scope:**

1. **Auth** — backend JWT endpoints + frontend login/register form + interceptor + guard.
2. **Frontend shell** — routing, services, page skeletons, raw state viewer on `/game`.
3. **Game engine skeleton** — singleton `GameRoom`, `Round` model, phase state machine, WS endpoint with JWT middleware, `asyncio` phase-loop task, auto-start on 4th connection, auto-reset after game end.

**Out of scope (next spec):**

- `MemeCard` catalog + fixtures.
- `PlayerCard` / hand dealing.
- `Situation` model + prompt display.
- `Submission` model + `/api/game/submit/` endpoint.
- `Vote` model + `/api/game/vote/` endpoint + tallying + `Round.winner`.
- Frontend gameplay screens (`submit-phase`, `voting-phase`, `results-phase`) — this iteration renders only a raw phase indicator.
- Final scoreboard and scoring.

By the end of this iteration, running the stack gives you: four users log in, open `/game`, get matched into the singleton room, and watch the phase state machine tick through `submitting → voting → results` for 8 rounds with no actual gameplay, then auto-reset. It's a hollow frame, but every transport layer (HTTP + JWT + WS + Channels group broadcast + asyncio timers) is real.

## 3. Backend

### 3.1 Dependencies

Teammate already installed `djangorestframework-simplejwt`, `corsheaders`, and Django itself. Still missing for this spec: Channels + daphne. Consolidate into `backend/requirements.txt` (create if missing):

```
django>=6.0,<6.1
djangorestframework>=3.15
djangorestframework-simplejwt>=5.3
channels>=4.1
daphne>=4.1
django-cors-headers>=4.3
```

### 3.2 Settings changes (`backend/memearena/settings.py`)

- `INSTALLED_APPS`: ensure contains `'daphne'` (must come before `django.contrib.staticfiles`), `'channels'`, `'rest_framework'`, `'rest_framework_simplejwt'`, `'rest_framework_simplejwt.token_blacklist'`, `'corsheaders'`. `rest_framework_simplejwt`, `token_blacklist`, and `corsheaders` are already there from teammate's commit; `daphne` and `channels` are the ones we add.
- `MIDDLEWARE`: prepend `'corsheaders.middleware.CorsMiddleware'` (teammate added the app but forgot the middleware — this is a bug fix).
- `ASGI_APPLICATION = 'memearena.asgi.application'`.
- `CHANNEL_LAYERS = {'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer'}}` (dev). Production would swap to `channels_redis`.
- `REST_FRAMEWORK = {'DEFAULT_AUTHENTICATION_CLASSES': ['rest_framework_simplejwt.authentication.JWTAuthentication']}`.
- `SIMPLE_JWT = {'ACCESS_TOKEN_LIFETIME': timedelta(hours=1), 'REFRESH_TOKEN_LIFETIME': timedelta(days=7)}`.
- `CORS_ALLOWED_ORIGINS = ['http://localhost:4200']`.
- `SECRET_KEY` → read from env with a dev fallback; add a note. (We keep the insecure dev key — production hardening is out of scope.)

### 3.3 Models (`backend/app/models.py`)

Models `Situation`, `Meme`, `Vote` — including teammate's additions (`Meme.caption/title`, `Situation.created_by/created_at`) — are all deleted in this iteration. `GameRoom` is kept but trimmed to what the skeleton needs; a new `Round` is added.

```python
class GameRoom(models.Model):
    # Singleton: exactly one row, id=1, created by data migration.
    STATUS_CHOICES = [('waiting', 'Waiting'), ('playing', 'Playing'), ('finished', 'Finished')]
    name = models.CharField(max_length=100, default='arena')
    players = models.ManyToManyField(User, blank=True, related_name='rooms')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='waiting')
    created_at = models.DateTimeField(auto_now_add=True)

class Round(models.Model):
    PHASE_CHOICES = [
        ('submitting', 'Submitting'),
        ('voting', 'Voting'),
        ('results', 'Results'),
        ('done', 'Done'),
    ]
    room = models.ForeignKey(GameRoom, on_delete=models.CASCADE, related_name='rounds')
    number = models.PositiveSmallIntegerField()           # 1..8
    phase = models.CharField(max_length=20, choices=PHASE_CHOICES, default='submitting')
    phase_deadline = models.DateTimeField()               # when the current phase ends
    class Meta:
        unique_together = ('room', 'number')
        ordering = ['-number']
```

No `MemeCard`, `PlayerCard`, `Situation`, `Submission`, `Vote` yet. The next spec will add them.

### 3.4 Migrations

1. Delete the existing initial migration `backend/app/migrations/0001_initial.py` (the current DB only contains dev data; a clean slate is fine). Teammate's `Situation.created_by` change never had a migration created, so nothing else to clean up in the `migrations/` folder.
2. Delete `backend/db.sqlite3`.
3. `python manage.py makemigrations app` → new `0001_initial.py` with the two models above.
4. Add a data migration `0002_singleton_room.py` that creates `GameRoom(id=1, name='arena')` so it always exists.
5. `python manage.py migrate` — includes `token_blacklist` tables from `simplejwt`.

### 3.5 Game engine (`backend/app/game.py`)

Pure synchronous ORM functions. No WS/HTTP knowledge. Called from REST views and from the Channels consumer via `sync_to_async`.

```python
SUBMITTING_SECONDS = 30
VOTING_SECONDS = 20
RESULTS_SECONDS = 5
TOTAL_ROUNDS = 8
RESET_DELAY_SECONDS = 10

def get_room() -> GameRoom:
    return GameRoom.objects.get(pk=1)

def add_player(room, user) -> bool:
    # Returns True if the user was added as a player, False if joined as spectator.
    # Only adds when status=='waiting' and player_count < 4.
    ...

def start_game(room) -> Round:
    # Called when the 4th player joins.
    # Sets room.status='playing', creates Round 1 (phase=submitting, deadline=now+30s).
    ...

def advance_phase(round: Round) -> Round:
    # submitting -> voting: phase='voting', deadline=now+20s
    # voting    -> results: phase='results', deadline=now+5s
    # results   -> next round: if round.number<8 -> new Round with number+1, phase=submitting, deadline=now+30s;
    #                         if round.number==8 -> round.phase='done', deadline=now (unused);
    #                                               room.status='finished'
    # Returns the ROUND that is now "current" (either the advanced round or the newly created next one).

def reset_game(room) -> None:
    # Deletes all Round rows for the room, clears players M2M, sets status='waiting'.
    # Called after the post-finish delay.
```

Skeleton rationale: this iteration has no cards/votes to tally, so `advance_phase` is just a timer-driven state progression with no side effects beyond writing the next row.

### 3.6 WebSocket layer

**URL:** `ws://host/ws/game/?token=<access_jwt>`

**JWT middleware (`backend/app/ws_auth.py`):**

- Parses `token` from query string, decodes it via `simplejwt`, resolves the `User`, puts it in `scope['user']`.
- On missing/invalid token, closes the socket immediately with a 4401 code (custom close code since 1008 is the nearest standard).

**Consumer (`backend/app/consumers.py`):**

```python
class GameConsumer(AsyncJsonWebsocketConsumer):
    GROUP_NAME = 'game'
    _phase_task: asyncio.Task | None = None   # class-level; single singleton room

    async def connect(self):
        if self.scope['user'].is_anonymous:
            await self.close(code=4401); return
        await self.channel_layer.group_add(self.GROUP_NAME, self.channel_name)
        await self.accept()

        room = await sync_to_async(get_room)()
        added = await sync_to_async(add_player)(room, self.scope['user'])

        # If this was the 4th player, start the game.
        if added and await sync_to_async(lambda: room.players.count())() == 4:
            await sync_to_async(start_game)(room)

        # Always make sure the phase loop is running if a game is in progress
        # (handles process restarts + reconnects mid-game).
        room = await sync_to_async(get_room)()
        if room.status == 'playing':
            self._ensure_phase_loop()

        await broadcast_state()

    async def disconnect(self, code):
        await self.channel_layer.group_discard(self.GROUP_NAME, self.channel_name)

    async def state_event(self, event):
        await self.send_json(event['payload'])

    @classmethod
    def _ensure_phase_loop(cls):
        if cls._phase_task is None or cls._phase_task.done():
            cls._phase_task = asyncio.create_task(cls._phase_loop())

    @classmethod
    async def _phase_loop(cls):
        while True:
            room = await sync_to_async(get_room)()
            if room.status != 'playing':
                # game ended; schedule reset then exit
                await asyncio.sleep(RESET_DELAY_SECONDS)
                await sync_to_async(reset_game)(room)
                await broadcast_state()
                return
            round = await sync_to_async(lambda: room.rounds.first())()
            delay = max(0, (round.phase_deadline - timezone.now()).total_seconds())
            await asyncio.sleep(delay)
            await sync_to_async(advance_phase)(round)
            await broadcast_state()
```

`broadcast_state()` is a module-level coroutine that serializes the current snapshot and calls `channel_layer.group_send('game', {'type': 'state.event', 'payload': <snapshot>})`.

**Snapshot shape** (client receives this on every update):

```json
{
  "type": "state",
  "payload": {
    "room": {"status": "waiting|playing|finished"},
    "players": [{"id": 1, "username": "alice"}],
    "current_round": {
      "number": 3,
      "phase": "submitting|voting|results|done",
      "phase_deadline": "2026-04-21T12:34:56Z"
    }
  }
}
```

No `hand`, `situation`, `submissions`, `votes`, `scores` yet — those come with the next spec.

### 3.7 REST (`backend/app/urls.py`, `backend/memearena/urls.py`)

Move the app URL prefix from `app/` (teammate's current) to `/api/`, and nest auth under `/api/auth/`:

```
POST /api/auth/register/   {username, password}   → 201 {message, username}     (existing FBV — reused)
POST /api/auth/login/      {username, password}   → 200 {access, refresh, username}  (existing FBV — reused)
POST /api/auth/logout/     {refresh}              → 205                         (existing FBV — reused; blacklists refresh)
POST /api/auth/refresh/    {refresh}              → 200 {access}                (new — simplejwt stock TokenRefreshView)
GET  /api/auth/me/                                 → 200 {id, username}         (new — custom FBV returning request.user)
```

Reuse teammate's `register_view`, `login_view`, `logout_view`, `RegisterSerializer`, `LoginSerializer` as-is. Add two new endpoints:

- `refresh/` → `rest_framework_simplejwt.views.TokenRefreshView.as_view()` (stock, zero code).
- `me/` → new FBV `@api_view(['GET']) @permission_classes([IsAuthenticated]) def me_view(request): return Response({'id': request.user.id, 'username': request.user.username})`.

**Note on register response shape.** Teammate's `register_view` returns `{message, username}` (no tokens), so the frontend must call `login` immediately after a successful register to get JWTs. We keep that flow — simpler than changing the view.

All of teammate's other REST routes — `rooms/`, `situations/`, `memes/`, `memes/<id>/`, `memes/<id>/vote/` — are **removed** (see §3.10). Corresponding views (`GameRoomListCreateView`, `SituationListCreateView`, `MemeListCreateView`, `MemeDetailView`, `vote_for_meme`) and serializers (`GameRoomSerializer`, `MemeSerializer`, `VoteSerializer`, `SituationSerializer`) are deleted.

### 3.8 ASGI (`backend/memearena/asgi.py`)

```python
from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application
from app.ws_auth import JWTAuthMiddleware
from app.routing import websocket_urlpatterns

application = ProtocolTypeRouter({
    'http': get_asgi_application(),
    'websocket': JWTAuthMiddleware(URLRouter(websocket_urlpatterns)),
})
```

`backend/app/routing.py`:
```python
from django.urls import path
from .consumers import GameConsumer
websocket_urlpatterns = [path('ws/game/', GameConsumer.as_asgi())]
```

### 3.9 Tests (`backend/app/tests.py`)

Skeleton-level only — enough to exercise every function without mocking the whole stack. Use Django's stock `TestCase` / `APITestCase`.

- `test_register_returns_tokens` — POST to `/api/auth/register/` creates a user and returns `access`/`refresh`.
- `test_me_requires_auth` — `/api/auth/me/` returns 401 without JWT, returns user on valid JWT.
- `test_add_player_fills_room` — add 4 users via `add_player`; count goes 1→2→3→4, 5th call returns `False` (spectator).
- `test_start_game_creates_round_1` — `start_game(room)` after 4 players; `room.status=='playing'`, `Round.objects.count()==1`, `round.phase=='submitting'`.
- `test_advance_phase_submitting_to_voting` — phase and deadline move as expected.
- `test_advance_phase_last_round_to_finished` — at round 8 results→done, `room.status=='finished'`.
- `test_reset_game` — clears rounds and players, status back to `waiting`.

WebSocket consumer integration test (one, happy-path):
- `test_ws_broadcasts_state_on_connect` — connect 4 users through `ApplicationCommunicator`, assert each receives a `state` message after their connect, last one triggers `status='playing'` in the broadcast.

Timer behavior isn't unit-tested (real `asyncio.sleep` would be flaky); `advance_phase` is tested directly with synthetic `Round` rows, and the phase-loop is covered only by the one WS integration test smoke-checking transitions (kept short by monkey-patching the phase-second constants to `0`).

### 3.10 Cleanup of teammate's partial work

Before implementing the skeleton, these pieces of teammate's commit `6afce32` must be removed:

**Delete (files / functions / imports):**
- `views.py`: `vote_for_meme`, `GameRoomListCreateView`, `SituationListCreateView`, `MemeListCreateView`, `MemeDetailView` (and their imports of `GameRoom/Situation/Meme/Vote`, `ListCreateAPIView`, `RetrieveUpdateDestroyAPIView`).
- `serializers.py`: `GameRoomSerializer`, `MemeSerializer`, `VoteSerializer`, `SituationSerializer`.
- `urls.py`: the paths `rooms/`, `situations/`, `memes/`, `memes/<int:pk>/`, `memes/<int:meme_id>/vote/`.
- `models.py`: `Situation`, `Meme`, `Vote` models entirely.
- `admin.py`: registrations for `Situation`, `Meme`, `Vote`.

**Don't bother fixing the known bugs** (`Vote.user`, `Meme.author`, `obj.votes`, `GameRoom.created_by`, missing `Situation.created_by` migration) — the code that carries them is being deleted anyway. Listed in §1 only so the reader understands why we're not salvaging those views.

**Keep (with tweaks):**
- `register_view`, `login_view`, `logout_view` in `views.py`.
- `RegisterSerializer`, `LoginSerializer` in `serializers.py`.
- `'rest_framework_simplejwt.token_blacklist'` and `'corsheaders'` in `INSTALLED_APPS`.

**Fix:**
- Add `'corsheaders.middleware.CorsMiddleware'` to `MIDDLEWARE` (step 3.2).
- Add `CORS_ALLOWED_ORIGINS = ['http://localhost:4200']` to `settings.py`.
- Add `REST_FRAMEWORK` and `SIMPLE_JWT` blocks (step 3.2).
- Move `memearena/urls.py` `include('app.urls')` from `app/` to `api/`.
- In `app/urls.py`, restructure so auth endpoints are under `auth/` prefix (nested) — so full paths are `/api/auth/register/` etc.

After this cleanup, `backend/app/` contains only: auth FBVs + serializers, `models.py` with `GameRoom` + `Round`, `game.py`, `consumers.py`, `ws_auth.py`, `routing.py`.

## 4. Frontend

### 4.1 Routes (`frontend/src/app/app.routes.ts`)

```
''         → redirect('/game')
'login'    → LoginComponent
'game'     → GameComponent            (canActivate: authGuard)
'**'       → redirect('/login')
```

### 4.2 Folder structure

```
src/app/
  app.ts
  app.config.ts            provideHttpClient(withInterceptors([authInterceptor]))
  app.routes.ts
  core/
    models.ts              TS types for State, Player, Round, User, AuthTokens
    auth.service.ts        register/login/logout; JWT in localStorage; currentUser signal
    auth.interceptor.ts    attaches `Authorization: Bearer <access>` to /api/ calls
    auth.guard.ts          no token → navigate /login
    api.service.ts         thin wrapper around HttpClient for /api/auth/*
    ws.service.ts          single WS connection; connect(token); message$ Observable; reconnect on close; disconnect()
    game-state.service.ts  signals: status, players, currentRound; subscribes to ws.message$
  pages/
    login/
      login.ts             form (tab register/login); calls AuthService; redirects /game
      login.html
      login.css
    game/
      game.ts              on init: call ws.connect(token); on destroy: ws.disconnect()
      game.html            minimal viewer — reads from GameStateService signals
      game.css
  components/
    timer/                 input: phaseDeadline; ticks 10 Hz and shows "12.3s"
    player-badge/          input: player; shows username
```

The existing `components/card-hand/` is kept on disk but **not routed anywhere** this iteration. It stays as a future asset for the next spec when we add card rendering. No edits yet.

### 4.3 Services

**AuthService:**
- `access` / `refresh` signals, hydrated from `localStorage` on construction.
- `currentUser: Signal<{id, username} | null>` — populated by `/api/auth/me/` after login or on app boot if a token exists.
- `register({username, password})` / `login({username, password})` — POST to `/api/auth/`, store tokens, set signals, then load `currentUser`.
- `logout()` — clears storage + signals, navigates `/login`.
- `token()` getter — returns current access token or `null`.
- Token refresh on 401 is **out of scope** for this spec (access lives 1h, good enough to play a session; users re-login if expired).

**authInterceptor** — function-style interceptor; if `AuthService.token()` is set, appends header. Skips `/api/auth/login|register|refresh`.

**authGuard** — `inject(AuthService).token() !== null` → true, else `router.navigate(['/login']); return false`.

**WsService:**
- `connect(token: string)` — opens `new WebSocket(environment.wsUrl + '/ws/game/?token=' + token)`.
- Exposes `message$: Subject<StateMessage>` that emits parsed JSON on `onmessage`.
- Reconnect policy: on `onclose` with code !== 1000 and !== 4401, wait 1s then reconnect (up to 5 attempts). On 4401, emit a `message$.error` — UI can catch and redirect to `/login`.
- `disconnect()` — closes with 1000, stops reconnect.

**GameStateService:**
- Signals: `status = signal<'waiting'|'playing'|'finished'>('waiting')`, `players = signal<Player[]>([])`, `currentRound = signal<RoundDto|null>(null)`.
- On construction, subscribes to `WsService.message$` and writes payload into signals.
- Exposes `youAreIn = computed(() => players().some(p => p.id === authService.currentUser()?.id))`.

**Environment** (`frontend/src/environments/environment.ts`):
```ts
export const environment = {
  apiUrl: 'http://localhost:8000',
  wsUrl: 'ws://localhost:8000',
};
```

### 4.4 `/login` page

Single form component with a tab toggle (`'login' | 'register'`). Fields: username, password. Submit calls `AuthService.login` or `.register` → on success `router.navigate(['/game'])`. Error message area for 400/401 responses.

Styling is minimal in this iteration — inherits global styles from `styles.css`. The MemeArena visual identity can be redone later.

### 4.5 `/game` page (placeholder viewer)

Reads from `GameStateService`. Renders:

```
MemeArena — status: {{ status() }}
Players ({{ players().length }}/4):
  - alice
  - bob
  - ...
Round {{ currentRound()?.number }}/8 — phase: {{ currentRound()?.phase }}
Time left: <app-timer [deadline]="currentRound()?.phase_deadline" />
```

When `status() === 'waiting'` and `players().length < 4`: show "Waiting for players... {n}/4".
When `status() === 'finished'`: show "Game over — resetting in 10s…".

No meme cards, hand, situation, submit/vote buttons, scoreboard. Those come with the next spec.

### 4.6 Tests

Vitest is already wired (`ng test` runs it). For this skeleton, one smoke test per service is enough:

- `auth.service.spec.ts` — `login` stores token in localStorage; `logout` clears it.
- `game-state.service.spec.ts` — feeding a fake `state` message through a mock `WsService` updates the `players`/`currentRound` signals.

E2E is not set up and is out of scope.

## 5. Protocol summary

| Direction | Transport | When | Shape |
|---|---|---|---|
| C→S | `POST /api/auth/register` | user submits register form | `{username, password}` |
| C→S | `POST /api/auth/login` | user submits login form | `{username, password}` |
| C→S | `POST /api/auth/refresh` | *(not used by frontend this iteration)* | `{refresh}` |
| C→S | `GET /api/auth/me` | after login to confirm identity | — |
| C→S | `WS connect /ws/game/?token=<jwt>` | user lands on `/game` | — |
| S→C | `{"type":"state","payload":{...}}` via WS group broadcast | any state mutation or phase tick | see §3.6 |

## 6. Rollout / run instructions (dev)

```bash
# backend
cd backend
python -m venv .venv && .venv\Scripts\activate   # or source on Unix
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver   # daphne auto-picks up ASGI_APPLICATION

# frontend (separate terminal)
cd frontend
npm install
npm start                    # ng serve on :4200
```

Open four incognito windows, register four users, each opens `/game`. After the 4th connects, watch the phase state machine tick through 8 rounds and auto-reset.

## 7. Open questions / deliberate deferrals

- **Singleton-room concurrency.** We rely on Django's transaction atomicity + the fact that WS connect races are rare at 4 users. No row-level locking. Fine for dev/hobby; re-evaluate when the next spec adds submit/vote (where races are more frequent).
- **Post-finish reset timer.** Lives in the phase loop. If the server restarts while a room is `finished`, the room stays `finished` forever. Acceptable — a fresh user connecting will not auto-reset it; we'd need a manual admin action or restart-hook. Deferred to prod-readiness spec.
- **Refresh-token rotation.** Not used by the frontend in this iteration; access tokens last 1 hour. Re-login on expiry.
- **i18n, styling, mobile layout.** Out of scope for the skeleton.

## 8. Next spec (preview, not part of this doc)

The follow-up spec will add, on top of this skeleton:

- `MemeCard`, `Situation`, `PlayerCard`, `Submission`, `Vote` models.
- Fixtures for mem images (from `frontend/public/memes/`) and situation prompts.
- `POST /api/game/submit/` and `POST /api/game/vote/` endpoints with validation.
- Deal-on-start and refill-on-submit logic in `start_game` / `advance_phase`.
- Winner tallying, `Round.winner`, score computation.
- Frontend `submit-phase`, `voting-phase`, `results-phase` components using the existing `card-hand` visual.
- Final scoreboard.
