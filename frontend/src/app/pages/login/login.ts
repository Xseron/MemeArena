import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';

import { AuthService } from '../../core/auth.service';

@Component({
  selector: 'app-login',
  standalone: true,
  imports: [FormsModule],
  templateUrl: './login.html',
  styleUrl: './login.css',
})
export class LoginComponent {
  private auth = inject(AuthService);
  private router = inject(Router);

  mode = signal<'login' | 'register'>('login');
  username = '';
  password = '';
  error = signal<string | null>(null);
  busy = signal(false);

  setMode(m: 'login' | 'register') {
    this.mode.set(m);
    this.error.set(null);
  }

  async submit() {
    if (!this.username || !this.password) {
      this.error.set('Username and password are required');
      return;
    }
    this.busy.set(true);
    this.error.set(null);
    try {
      if (this.mode() === 'register') {
        await this.auth.register(this.username, this.password);
      } else {
        await this.auth.login(this.username, this.password);
      }
      this.router.navigate(['/game']);
    } catch (e: any) {
      const detail = e?.error?.detail ?? e?.error ?? e?.message ?? 'Request failed';
      this.error.set(typeof detail === 'string' ? detail : JSON.stringify(detail));
    } finally {
      this.busy.set(false);
    }
  }
}
