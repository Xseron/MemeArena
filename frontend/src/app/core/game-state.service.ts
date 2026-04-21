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
