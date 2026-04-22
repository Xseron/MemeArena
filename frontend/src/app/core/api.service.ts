import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { environment } from '../../environments/environment';

@Injectable({ providedIn: 'root' })
export class ApiService {
  private http = inject(HttpClient);

  async submit(playerCardId: number): Promise<void> {
    try {
      await firstValueFrom(
        this.http.post(`${environment.apiUrl}/api/game/submit/`, {
          player_card_id: playerCardId,
        }),
      );
    } catch (e) {
      throw this.unwrap(e);
    }
  }

  async vote(submissionId: number): Promise<void> {
    try {
      await firstValueFrom(
        this.http.post(`${environment.apiUrl}/api/game/vote/`, {
          submission_id: submissionId,
        }),
      );
    } catch (e) {
      throw this.unwrap(e);
    }
  }

  async resetGame(): Promise<void> {
    try {
      await firstValueFrom(
        this.http.post(`${environment.apiUrl}/api/game/reset/`, {}),
      );
    } catch (e) {
      throw this.unwrap(e);
    }
  }

  async kickPlayer(userId: number): Promise<void> {
    try {
      await firstValueFrom(
        this.http.post(`${environment.apiUrl}/api/game/kick/`, { user_id: userId }),
      );
    } catch (e) {
      throw this.unwrap(e);
    }
  }

  private unwrap(e: unknown): Error {
    if (e instanceof HttpErrorResponse) {
      const code = (e.error && (e.error as { error?: string }).error) || `http_${e.status}`;
      return new Error(code);
    }
    return e instanceof Error ? e : new Error('unknown');
  }
}
