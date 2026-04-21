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
