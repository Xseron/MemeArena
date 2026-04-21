import { HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';

import { AuthService } from './auth.service';

const PUBLIC_PATHS = ['/api/auth/login/', '/api/auth/register/', '/api/auth/refresh/'];

export const authInterceptor: HttpInterceptorFn = (req, next) => {
  if (PUBLIC_PATHS.some((p) => req.url.endsWith(p))) {
    return next(req);
  }
  const token = inject(AuthService).token();
  if (!token) return next(req);
  return next(
    req.clone({ setHeaders: { Authorization: `Bearer ${token}` } }),
  );
};
