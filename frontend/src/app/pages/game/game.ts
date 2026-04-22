import { Component, OnDestroy, OnInit, computed, inject, signal } from '@angular/core';

import { ApiService } from '../../core/api.service';
import { AuthService } from '../../core/auth.service';
import { GameStateService } from '../../core/game-state.service';
import { WsService } from '../../core/ws.service';
import { CardHandComponent } from '../../components/card-hand/card-hand';
import { WaitingRoomComponent } from './waiting-room/waiting-room';
import { FinalScreenComponent } from './final-screen/final-screen';

const ERROR_TEXT: Record<string, string> = {
  wrong_phase: 'The phase has already changed',
  already_submitted: 'You have already played this round',
  already_voted: 'You have already voted',
  own_submission: 'You cannot vote for your own card',
  card_not_yours: 'Card is outdated, refresh the page',
  submission_not_found: 'Card not found',
  not_in_game: 'You are not in the game',
  cannot_kick_self: 'You cannot kick yourself',
  not_in_waiting: 'Kicking is only allowed before the game starts',
  not_in_room: 'That player is no longer in the room',
};

@Component({
  selector: 'app-game',
  standalone: true,
  imports: [CardHandComponent, WaitingRoomComponent, FinalScreenComponent],
  templateUrl: './game.html',
  styleUrl: './game.css',
})
export class GameComponent implements OnInit, OnDestroy {
  private auth = inject(AuthService);
  private ws = inject(WsService);
  private api = inject(ApiService);
  protected state = inject(GameStateService);

  protected otherPlayers = computed(() => {
    const myId = this.state.youId();
    const all = this.state.players();
    return myId != null ? all.filter((p) => p.id !== myId) : all.slice(0, 3);
  });

  protected yourUsername = computed(() => {
    const myId = this.state.youId();
    if (myId == null) return '';
    const me = this.state.players().find((p) => p.id === myId);
    return me?.username ?? '';
  });

  protected errorMsg = signal<string | null>(null);
  private errorTimer: ReturnType<typeof setTimeout> | null = null;

  private showError(code: string) {
    this.errorMsg.set(ERROR_TEXT[code] ?? `Error: ${code}`);
    if (this.errorTimer) clearTimeout(this.errorTimer);
    this.errorTimer = setTimeout(() => this.errorMsg.set(null), 3500);
  }

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

  async onPickCard(playerCardId: number) {
    try {
      await this.api.submit(playerCardId);
    } catch (err) {
      const code = err instanceof Error ? err.message : 'unknown';
      this.showError(code);
    }
  }

  async onVoteSubmission(submissionId: number) {
    try {
      await this.api.vote(submissionId);
    } catch (err) {
      const code = err instanceof Error ? err.message : 'unknown';
      this.showError(code);
    }
  }

  async stopGame() {
    if (!confirm('Stop the game and reset the room?')) return;
    try {
      await this.api.resetGame();
    } catch (err) {
      console.error('reset failed', err);
    }
  }

  async onKick(userId: number) {
    try {
      await this.api.kickPlayer(userId);
    } catch (err) {
      const code = err instanceof Error ? err.message : 'unknown';
      this.showError(code);
    }
  }
}
