import { Component, EventEmitter, Input, Output } from '@angular/core';

import { Player } from '../../../core/models';

@Component({
  selector: 'app-waiting-room',
  standalone: true,
  templateUrl: './waiting-room.html',
  styleUrl: './waiting-room.css',
})
export class WaitingRoomComponent {
  @Input({ required: true }) players: Player[] = [];
  @Input() youId: number | null = null;
  @Output() kick = new EventEmitter<number>();

  get slots(): (Player | null)[] {
    const out: (Player | null)[] = [...this.players];
    while (out.length < 4) out.push(null);
    return out.slice(0, 4);
  }
}
