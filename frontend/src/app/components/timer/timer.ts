import { Component, DestroyRef, Input, OnChanges, SimpleChanges, inject, signal } from '@angular/core';

@Component({
  selector: 'app-timer',
  standalone: true,
  templateUrl: './timer.html',
  styleUrl: './timer.css',
})
export class TimerComponent implements OnChanges {
  @Input() deadline: string | null = null;

  private destroyRef = inject(DestroyRef);
  private handle: ReturnType<typeof setInterval> | null = null;

  readonly remaining = signal('—');

  ngOnChanges(changes: SimpleChanges): void {
    this.stop();
    if (!this.deadline) {
      this.remaining.set('—');
      return;
    }
    this.tick();
    this.handle = setInterval(() => this.tick(), 100);
    this.destroyRef.onDestroy(() => this.stop());
  }

  private stop(): void {
    if (this.handle) {
      clearInterval(this.handle);
      this.handle = null;
    }
  }

  private tick(): void {
    if (!this.deadline) return;
    const ms = Math.max(0, new Date(this.deadline).getTime() - Date.now());
    this.remaining.set((ms / 1000).toFixed(1) + 's');
    if (ms === 0) this.stop();
  }
}
