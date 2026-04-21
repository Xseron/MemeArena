import { HttpClient } from '@angular/common/http';
import { Injectable, computed, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { firstValueFrom } from 'rxjs';

import { environment } from '../../environments/environment';
import { AuthTokens, User } from './models';

const ACCESS_KEY = 'access';
const REFRESH_KEY = 'refresh';
const USERNAME_KEY = 'username';

@Injectable({ providedIn: 'root' })
export class AuthService {
  private http = inject(HttpClient);
  private router = inject(Router);

  private accessSig = signal<string | null>(localStorage.getItem(ACCESS_KEY));
  private refreshSig = signal<string | null>(localStorage.getItem(REFRESH_KEY));
  private userSig = signal<User | null>(this.hydrateUser());

  token = computed(() => this.accessSig());
  currentUser = computed(() => this.userSig());

  private hydrateUser(): User | null {
    const name = localStorage.getItem(USERNAME_KEY);
    return name ? { id: 0, username: name } : null;
  }

  async register(username: string, password: string): Promise<void> {
    await firstValueFrom(
      this.http.post(`${environment.apiUrl}/api/auth/register/`, { username, password }),
    );
    await this.login(username, password);
  }

  async login(username: string, password: string): Promise<void> {
    const tokens = await firstValueFrom(
      this.http.post<AuthTokens>(`${environment.apiUrl}/api/auth/login/`, {
        username,
        password,
      }),
    );
    localStorage.setItem(ACCESS_KEY, tokens.access);
    localStorage.setItem(REFRESH_KEY, tokens.refresh);
    localStorage.setItem(USERNAME_KEY, tokens.username);
    this.accessSig.set(tokens.access);
    this.refreshSig.set(tokens.refresh);
    this.userSig.set({ id: 0, username: tokens.username });
  }

  logout(): void {
    const refresh = this.refreshSig() ?? localStorage.getItem(REFRESH_KEY);
    if (refresh) {
      this.http
        .post(`${environment.apiUrl}/api/auth/logout/`, { refresh })
        .subscribe({ error: () => {} });
    }
    localStorage.removeItem(ACCESS_KEY);
    localStorage.removeItem(REFRESH_KEY);
    localStorage.removeItem(USERNAME_KEY);
    this.accessSig.set(null);
    this.refreshSig.set(null);
    this.userSig.set(null);
    this.router.navigate(['/login']);
  }
}
