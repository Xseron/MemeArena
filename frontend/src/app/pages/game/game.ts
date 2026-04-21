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
