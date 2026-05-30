import type { NextFunction, Request, Response } from 'express';
import { ZodError } from 'zod';
import { HttpError } from '../utils/http-errors';
import { normalizeZodError } from '../utils/validation';

type ErrorPayload = {
  code: string;
  message: string;
  issues?: unknown;
  details?: unknown;
};

function sendError(res: Response, status: number, payload: ErrorPayload) {
  return res.status(status).json(payload);
}

export function notFoundHandler(_req: Request, _res: Response, next: NextFunction) {
  next(new HttpError(404, 'Not Found', 'NOT_FOUND'));
}

export function errorHandler(err: any, req: Request, res: Response, _next: NextFunction) {
  if (err instanceof ZodError) {
    const normalized = normalizeZodError(err);
    const payload: ErrorPayload = {
      code: 'BAD_REQUEST',
      message: normalized.message,
      issues: normalized.issues,
      details: normalized.details,
    };
    req.log.warn({ err, path: req.path, response: payload }, 'Zod validation error');
    return sendError(res, 400, payload);
  }

  const isHttpError = err instanceof HttpError;
  const status = isHttpError ? err.status : 500;
  const payload: ErrorPayload = {
    code: isHttpError ? err.code : 'INTERNAL_ERROR',
    message: isHttpError ? err.message : 'Unexpected error',
    details: isHttpError ? err.details : undefined,
  };

  if (status >= 500) {
    req.log.error({ err, path: req.path, response: payload }, 'Unhandled error');
  } else {
    req.log.warn({ err, path: req.path, response: payload }, 'Handled error');
  }

  return sendError(res, status, payload);
}
