import { Injectable, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';

import { FinalScore, Player, RoomStatus, RoundDto, RoundSummary, ServerMessage } from './models';
import { WsService } from './ws.service';

@Injectable({ providedIn: 'root' })
export class GameStateService {
  private ws = inject(WsService);

  readonly status = signal<RoomStatus>('waiting');
  readonly youId = signal<number | null>(null);
  readonly players = signal<Player[]>([]);
  readonly currentRound = signal<RoundDto | null>(null);
  readonly finalScores = signal<FinalScore[] | null>(null);
  readonly roundSummaries = signal<RoundSummary[] | null>(null);
  readonly lastError = signal<string | null>(null);

  constructor() {
    this.ws.message$.pipe(takeUntilDestroyed()).subscribe((msg: ServerMessage) => {
      if (msg.type === 'error') {
        this.lastError.set(msg.payload.code);
        return;
      }
      this.lastError.set(null);
      this.status.set(msg.payload.room.status);
      this.youId.set(msg.payload.you_id);
      this.players.set(msg.payload.players);
      this.currentRound.set(msg.payload.current_round);
      this.finalScores.set(msg.payload.final_scores);
      this.roundSummaries.set(msg.payload.round_summaries);
    });
  }
}
