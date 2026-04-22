import { AfterViewInit, Component, DestroyRef, Input, OnInit, computed, inject, signal } from '@angular/core';
import confetti from 'canvas-confetti';

import { FinalScore, Player, RoundSummary } from '../../../core/models';

interface PodiumSlot {
  place: 1 | 2 | 3;
  username: string;
  score: number;
  medal: string;
  label: string;
}

@Component({
  selector: 'app-final-screen',
  standalone: true,
  templateUrl: './final-screen.html',
  styleUrl: './final-screen.css',
})
export class FinalScreenComponent implements OnInit, AfterViewInit {
  @Input({ required: true }) scores: FinalScore[] = [];
  @Input({ required: true }) players: Player[] = [];
  @Input() roundSummaries: RoundSummary[] = [];

  private destroyRef = inject(DestroyRef);
  private timers: ReturnType<typeof setTimeout>[] = [];

  readonly revealed = signal(false);

  readonly champion = computed(() => {
    const top = this.scores[0];
    if (!top) return null;
    return {
      username: this.usernameOf(top.player_id),
      score: top.score,
    };
  });

  readonly podium = computed<PodiumSlot[]>(() => {
    const slots: PodiumSlot[] = [];
    const medals: Record<number, { medal: string; label: string }> = {
      1: { medal: '🥇', label: 'CHAMPION' },
      2: { medal: '🥈', label: 'RUNNER-UP' },
      3: { medal: '🥉', label: 'THIRD' },
    };
    this.scores.slice(0, 3).forEach((s, i) => {
      const place = (i + 1) as 1 | 2 | 3;
      slots.push({
        place,
        username: this.usernameOf(s.player_id),
        score: s.score,
        medal: medals[place].medal,
        label: medals[place].label,
      });
    });
    return slots;
  });

  readonly remaining = computed(() =>
    this.scores.slice(3).map((s, i) => ({
      place: i + 4,
      username: this.usernameOf(s.player_id),
      score: s.score,
    })),
  );

  readonly wallCards = computed(() =>
    (this.roundSummaries ?? []).filter((r) => r.winner !== null),
  );

  ngOnInit(): void {
    this.destroyRef.onDestroy(() => {
      this.timers.forEach(clearTimeout);
      this.timers = [];
    });
  }

  ngAfterViewInit(): void {
    this.schedule(100, () => this.burstCorners());
    this.schedule(800, () => this.burstCenter());
    this.schedule(1800, () => this.burstCorners());
    this.schedule(3000, () => this.revealed.set(true));
  }

  usernameOf(playerId: number): string {
    const p = this.players.find((x) => x.id === playerId);
    return p ? p.username : `#${playerId}`;
  }

  trackCard = (_: number, r: RoundSummary) => r.round_number;
  trackRank = (_: number, r: { place: number }) => r.place;

  tiltFor(index: number): number {
    const seq = [-3.2, 2.4, -1.8, 3.1, -2.6, 1.7, -3.5, 2.2];
    return seq[index % seq.length];
  }

  private schedule(delay: number, fn: () => void): void {
    this.timers.push(setTimeout(fn, delay));
  }

  private burstCorners(): void {
    const palette = ['#ffd447', '#f72585', '#ff6ec7', '#7af7ff', '#ffffff'];
    confetti({
      particleCount: 90,
      angle: 60,
      spread: 70,
      startVelocity: 55,
      origin: { x: 0, y: 0.85 },
      colors: palette,
      ticks: 260,
    });
    confetti({
      particleCount: 90,
      angle: 120,
      spread: 70,
      startVelocity: 55,
      origin: { x: 1, y: 0.85 },
      colors: palette,
      ticks: 260,
    });
  }

  private burstCenter(): void {
    confetti({
      particleCount: 140,
      spread: 160,
      startVelocity: 35,
      gravity: 0.8,
      scalar: 1.1,
      origin: { x: 0.5, y: 0.35 },
      colors: ['#ffd447', '#ffb800', '#ffffff', '#f72585'],
      shapes: ['star', 'circle'],
      ticks: 320,
    });
  }
}
