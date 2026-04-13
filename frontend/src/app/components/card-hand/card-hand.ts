import {
  AfterViewInit,
  Component,
  DestroyRef,
  ElementRef,
  OnDestroy,
  QueryList,
  ViewChild,
  ViewChildren,
  inject,
  signal,
} from '@angular/core';
import { animate, createTimer, utils } from 'animejs';

type PlayerId = 'you' | 'top' | 'left' | 'right';

interface Meme {
  img: string;
  title: string;
  hue: number;
}

interface Card {
  id: number;
  meme: Meme;
  owner: PlayerId;
  slot: number;
  state: 'hand' | 'flying' | 'table';
  from?: { x: number; y: number };
  tableIdx?: number;
}

const MEMES: Meme[] = [
  { img: 'memes/dead_inside.png', title: 'DEAD INSIDE', hue: 280 },
  { img: 'memes/giga.png',        title: 'GIGACHAD',    hue: 42  },
  { img: 'memes/megamozg.png',    title: 'BIG BRAIN',   hue: 200 },
];

const PLAYERS: PlayerId[] = ['you', 'top', 'left', 'right'];
const HAND_SIZE = 5;
const TURN_MS = 10_000;

let UID = 1;
const pickMeme = () => MEMES[Math.floor(Math.random() * MEMES.length)];

@Component({
  selector: 'app-card-hand',
  standalone: true,
  templateUrl: './card-hand.html',
  styleUrl: './card-hand.css',
})
export class CardHandComponent implements AfterViewInit, OnDestroy {
  @ViewChild('stage') private stageRef?: ElementRef<HTMLElement>;
  @ViewChildren('handEl') private handEls?: QueryList<ElementRef<HTMLElement>>;
  @ViewChildren('flyEl') private flyEls?: QueryList<ElementRef<HTMLElement>>;

  private destroyRef = inject(DestroyRef);

  readonly cards = signal<Card[]>([]);
  readonly selectedId = signal<number | null>(null);
  readonly tick = signal<number>(TURN_MS);

  private startTs = performance.now();
  private turnTimer?: ReturnType<typeof createTimer>;
  private tickTimer?: ReturnType<typeof createTimer>;

  ngAfterViewInit(): void {
    this.deal();

    this.tickTimer = createTimer({
      duration: 1e9,
      onUpdate: () => {
        const elapsed = (performance.now() - this.startTs) % TURN_MS;
        this.tick.set(Math.max(0, TURN_MS - elapsed));
      },
    });

    this.turnTimer = createTimer({
      duration: TURN_MS,
      loop: true,
      onLoop: () => this.throwRound(),
    });

    this.destroyRef.onDestroy(() => {
      this.tickTimer?.pause();
      this.turnTimer?.pause();
    });
  }

  ngOnDestroy(): void {
    this.tickTimer?.pause();
    this.turnTimer?.pause();
  }

  private deal(): void {
    const deck: Card[] = [];
    for (const p of PLAYERS) {
      for (let s = 0; s < HAND_SIZE; s++) {
        deck.push({ id: UID++, meme: pickMeme(), owner: p, slot: s, state: 'hand' });
      }
    }
    this.cards.set(deck);
  }

  select(id: number, owner: PlayerId): void {
    if (owner !== 'you') return;
    this.selectedId.update((cur) => (cur === id ? null : id));
  }

  private throwRound(): void {
    this.startTs = performance.now();
    // clear previous round's table
    this.cards.update((all) => all.filter((c) => c.state !== 'table'));
    PLAYERS.forEach((p, idx) => {
      setTimeout(() => this.throwFor(p), idx * 120);
    });
  }

  private throwFor(owner: PlayerId): void {
    const list = this.cards();
    const hand = list.filter((c) => c.owner === owner && c.state === 'hand');
    if (!hand.length) return;

    let card: Card | undefined;
    if (owner === 'you') {
      const sel = this.selectedId();
      card = sel != null ? hand.find((c) => c.id === sel) : hand[0];
    } else {
      card = hand[Math.floor(Math.random() * hand.length)];
    }
    if (!card) return;

    // measure the hand card on screen, compute offset from stage center
    const stage = this.stageRef?.nativeElement;
    if (!stage) return;
    const sRect = stage.getBoundingClientRect();
    const handEl = this.handEls?.find(
      (r) => r.nativeElement.dataset['id'] === String(card!.id),
    )?.nativeElement;
    if (!handEl) return;

    const hRect = handEl.getBoundingClientRect();
    const fromX = hRect.left + hRect.width / 2 - (sRect.left + sRect.width / 2);
    const fromY = hRect.top + hRect.height / 2 - (sRect.top + sRect.height / 2);

    const tableIdx = this.cards().filter(
      (c) => c.state === 'table' || c.state === 'flying',
    ).length;

    const cardId = card.id;

    this.cards.update((all) =>
      all.map((c) =>
        c.id === cardId
          ? { ...c, state: 'flying', from: { x: fromX, y: fromY }, tableIdx }
          : c,
      ),
    );
    if (this.selectedId() === cardId) this.selectedId.set(null);

    requestAnimationFrame(() => {
      const flyEl = this.flyEls?.find(
        (r) => r.nativeElement.dataset['id'] === String(cardId),
      )?.nativeElement;
      if (!flyEl) {
        this.markOnTable(cardId);
        return;
      }

      const spin = Math.random() > 0.5 ? 540 : -540;

      utils.set(flyEl, { x: fromX, y: fromY, rotate: 0, scale: 1 });

      const target = this.tableCoord(tableIdx);

      animate(flyEl, {
        keyframes: [
          { x: fromX * 0.4, y: fromY * 0.4 - 50, rotate: spin * 0.4, scale: 1.18, duration: 380, ease: 'out(3)' },
          { x: target.x,    y: target.y,         rotate: spin,        scale: 1,    duration: 520, ease: 'out(5)' },
        ],
        onComplete: () => {
          this.markOnTable(cardId);
          this.refill(owner, card!.slot);
        },
      });
    });
  }

  private markOnTable(id: number): void {
    this.cards.update((all) => all.map((c) => (c.id === id ? { ...c, state: 'table' } : c)));
  }

  private refill(owner: PlayerId, slot: number): void {
    this.cards.update((all) => [
      ...all,
      { id: UID++, meme: pickMeme(), owner, slot, state: 'hand' as const },
    ]);
  }

  track = (_: number, c: Card) => c.id;

  handOf(p: PlayerId): Card[] {
    return this.cards()
      .filter((c) => c.owner === p && c.state === 'hand')
      .sort((a, b) => a.slot - b.slot);
  }

  flying(): Card[] {
    return this.cards().filter((c) => c.state === 'flying');
  }

  onTable(): Card[] {
    return this.cards().filter((c) => c.state === 'table');
  }

  tableCoord(idx: number): { x: number; y: number } {
    const spacing = 100;
    const total = this.cards().filter(
      (c) => c.state === 'table' || c.state === 'flying',
    ).length;
    const x = (idx - (total - 1) / 2) * spacing;
    return { x, y: 0 };
  }

  tableTransform(c: Card): string {
    const { x, y } = this.tableCoord(c.tableIdx ?? 0);
    return `translate(-50%, -50%) translate(${x}px, ${y}px)`;
  }

  tickSeconds(): string {
    return (this.tick() / 1000).toFixed(1);
  }
}
