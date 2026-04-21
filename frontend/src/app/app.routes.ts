import { Routes } from '@angular/router';

import { authGuard } from './core/auth.guard';

export const routes: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'game' },
  {
    path: 'login',
    loadComponent: () =>
      import('./pages/login/login').then((m) => m.LoginComponent),
  },
  {
    path: 'game',
    canActivate: [authGuard],
    loadComponent: () =>
      import('./pages/game/game').then((m) => m.GameComponent),
  },
  { path: '**', redirectTo: 'login' },
];
