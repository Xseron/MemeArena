import {
  Component,
  ElementRef,
  EventEmitter,
  Input,
  OnChanges,
  Output,
  QueryList,
  SimpleChanges,
  ViewChild,
  ViewChildren,
  signal,
} from '@angular/core';
import { animate, utils } from 'animejs';

import { HAND_SIZE, HandCard, Phase, Player, SubmissionDto } from '../../core/models';
import { TimerComponent } from '../timer/timer';

interface FlyingCard {
  id: number;
  card: HandCard;
  fromX: number;
  fromY: number;
}

@Component({
  selector: 'app-card-hand',
  standalone: true,
  imports: [TimerComponent],
  templateUrl: './card-hand.html',
  styleUrl: './card-hand.css',
})
export class CardHandComponent implements OnChanges {
  @ViewChild('stage') private stageRef?: ElementRef<HTMLElement>;
  @ViewChildren('flyEl') private flyEls?: QueryList<ElementRef<HTMLElement>>;

  @Input() phase: Phase = 'submitting';
  @Input() roundNumber = 1;
  @Input() totalRounds = 8;
  @Input() situation = '';
  @Input() phaseDeadline: string | null = null;
  @Input() yourHand: HandCard[] = [];
  @Input() yourUsername = '';
  @Input() otherPlayers: Player[] = [];
  @Input() players: Player[] = [];
  @Input() submissions: SubmissionDto[] = [];
  @Input() youSubmitted = false;
  @Input() youVoted = false;
  @Input() winnerSubmissionId: number | null = null;
  @Input() voteCounts: Record<number, number> = {};

  @Output() pickCard = new EventEmitter<number>();
  @Output() voteSubmission = new EventEmitter<number>();

  readonly flying = signal<FlyingCard[]>([]);

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['yourHand'] && !changes['yourHand'].firstChange) {
      const prev: HandCard[] = changes['yourHand'].previousValue ?? [];
      const cur: HandCard[] = changes['yourHand'].currentValue ?? [];
      const curIds = new Set(cur.map((c) => c.id));
      const gone = prev.filter((c) => !curIds.has(c.id));
      if (gone.length) this.cleanupFlying();
    }
  }

  onPickYou(handCardId: number, btn: HTMLButtonElement): void {
    if (this.phase !== 'submitting' || this.youSubmitted) return;
    this.startFlight(handCardId, btn);
    this.pickCard.emit(handCardId);
  }

  onVote(submissionId: number): void {
    if (this.phase !== 'voting' || this.youVoted) return;
    this.voteSubmission.emit(submissionId);
  }

  isWinner(submissionId: number): boolean {
    return this.winnerSubmissionId === submissionId;
  }

  voteCount(submissionId: number): number {
    return this.voteCounts[submissionId] ?? 0;
  }

  usernameOf(playerId: number | null | undefined): string {
    if (playerId == null) return '';
    const p = this.players.find((x) => x.id === playerId);
    return p ? p.username : '';
  }

  otherHandBacks(): number[] {
    return Array.from({ length: HAND_SIZE }, (_, i) => i + 1);
  }

  trackCard = (_: number, c: HandCard) => c.id;
  trackSub = (_: number, s: SubmissionDto) => s.id;
  trackPlayer = (_: number, p: Player) => p.id;

  private startFlight(handCardId: number, btn: HTMLButtonElement): void {
    const stage = this.stageRef?.nativeElement;
    if (!stage) return;
    const card = this.yourHand.find((c) => c.id === handCardId);
    if (!card) return;

    const sRect = stage.getBoundingClientRect();
    const hRect = btn.getBoundingClientRect();
    const fromX = hRect.left + hRect.width / 2 - (sRect.left + sRect.width / 2);
    const fromY = hRect.top + hRect.height / 2 - (sRect.top + sRect.height / 2);

    this.flying.update((arr) => [...arr, { id: handCardId, card, fromX, fromY }]);

    requestAnimationFrame(() => {
      const flyEl = this.flyEls?.find(
        (r) => r.nativeElement.dataset['id'] === String(handCardId),
      )?.nativeElement;
      if (!flyEl) return;

      const spin = Math.random() > 0.5 ? 540 : -540;
      utils.set(flyEl, { x: fromX, y: fromY, rotate: 0, scale: 1 });

      animate(flyEl, {
        keyframes: [
          { x: fromX * 0.4, y: fromY * 0.4 - 50, rotate: spin * 0.4, scale: 1.18, duration: 380, ease: 'out(3)' },
          { x: 0, y: 0, rotate: spin, scale: 1, duration: 520, ease: 'out(5)' },
        ],
        onComplete: () => {
          setTimeout(() => {
            this.flying.update((arr) => arr.filter((f) => f.id !== handCardId));
          }, 200);
        },
      });
    });
  }

  private cleanupFlying(): void {
    this.flying.set([]);
  }
}
