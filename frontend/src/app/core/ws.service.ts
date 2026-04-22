import { Injectable } from '@angular/core';
import { Subject } from 'rxjs';

import { environment } from '../../environments/environment';
import { ServerMessage } from './models';

const MAX_RECONNECT = 5;
const RECONNECT_DELAY_MS = 1000;

@Injectable({ providedIn: 'root' })
export class WsService {
  readonly message$ = new Subject<ServerMessage>();

  private socket: WebSocket | null = null;
  private token: string | null = null;
  private reconnectAttempts = 0;
  private shouldReconnect = false;

  connect(token: string): void {
    this.token = token;
    this.shouldReconnect = true;
    this.reconnectAttempts = 0;
    this.open();
  }

  disconnect(): void {
    this.shouldReconnect = false;
    this.socket?.close(1000, 'client disconnect');
    this.socket = null;
  }

  private open(): void {
    const url = `${environment.wsUrl}/ws/game/?token=${encodeURIComponent(this.token ?? '')}`;
    const sock = new WebSocket(url);
    this.socket = sock;
    sock.onmessage = (ev) => {
      try {
        const parsed = JSON.parse(ev.data) as ServerMessage;
        if (parsed?.type !== 'state' && parsed?.type !== 'error') return;
        this.message$.next(parsed);
      } catch {
        return;
      }
    };
    sock.onclose = (ev) => {
      this.socket = null;
      if (ev.code === 4401) {
        this.message$.error(new Error('unauthorized'));
        return;
      }
      if (!this.shouldReconnect) return;
      if (this.reconnectAttempts >= MAX_RECONNECT) return;
      this.reconnectAttempts += 1;
      setTimeout(() => this.open(), RECONNECT_DELAY_MS);
    };
  }
}
