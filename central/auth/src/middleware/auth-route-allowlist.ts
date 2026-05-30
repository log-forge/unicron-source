import type { RequestHandler } from 'express';

const ALLOWED_AUTH_ROUTES = new Set([
  'GET /api/auth/ok',
  'GET /api/auth/get-session',
  'POST /api/auth/sign-in/username',
  'POST /api/auth/sign-out',
  'POST /api/auth/change-password',
]);

export const authRouteAllowlist: RequestHandler = (req, res, next) => {
  const path = new URL(req.originalUrl, 'http://central-auth.local').pathname;
  const key = `${req.method.toUpperCase()} ${path}`;
  if (ALLOWED_AUTH_ROUTES.has(key)) return next();

  return res.status(404).json({
    code: 'NOT_FOUND',
    message: 'Not Found',
  });
};
