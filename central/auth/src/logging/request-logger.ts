import crypto from 'node:crypto';
import type { IncomingMessage, ServerResponse } from 'node:http';
import type { RequestHandler } from 'express';
import pinoHttp, { type Options as PinoHttpOptions } from 'pino-http';
import { logger } from './logger';

type RequestWithExtras = IncomingMessage & {
  id?: string;
  ip?: string;
  socket?: { remoteAddress?: string };
  headers: IncomingMessage['headers'] & { 'user-agent'?: string };
};

const SENSITIVE_QUERY_KEY = /(?:password|passwd|pwd|token|secret|credential|authorization|api[-_]?key|session|code)/iu;

function sanitizeUrlForLog(rawUrl?: string | null): string {
  if (!rawUrl) return '';

  try {
    const parsed = new URL(rawUrl, 'http://local.invalid');
    for (const key of Array.from(parsed.searchParams.keys())) {
      if (SENSITIVE_QUERY_KEY.test(key)) parsed.searchParams.set(key, '[REDACTED]');
    }

    return `${parsed.pathname}${parsed.search}${parsed.hash}`;
  } catch (_err) {
    return rawUrl.replace(/([?&][^=&]*(?:password|passwd|pwd|token|secret|credential|authorization|api[-_]?key|session|code)[^=]*=)[^&]*/giu, '$1[REDACTED]');
  }
}

const pinoHttpOptions: PinoHttpOptions = {
  logger,
  genReqId: (req: IncomingMessage) => (req.headers['x-request-id'] as string) || crypto.randomUUID(),
  serializers: {
    req(req: IncomingMessage) {
      const r = req as RequestWithExtras;
      return {
        id: r.id,
        method: r.method,
        url: sanitizeUrlForLog(r.url),
        remoteAddress: r.ip || r.socket?.remoteAddress || undefined,
        userAgent: r.headers?.['user-agent'],
      };
    },
    res(res: ServerResponse) {
      return { statusCode: res.statusCode };
    },
  },
  customLogLevel: (_req: IncomingMessage, res: ServerResponse, err: unknown) => (err || res.statusCode >= 500 ? 'error' : res.statusCode >= 400 ? 'warn' : 'info'),
  autoLogging: { ignore: (req: IncomingMessage) => Boolean(req.url && (req.url.startsWith('/healthz') || req.url.startsWith('/readyz'))) },
};

export const requestLogger = pinoHttp(pinoHttpOptions);

export const requestIdHeader: RequestHandler = (req, res, next) => {
  const r = req as RequestWithExtras;
  if (r.id) res.setHeader('x-request-id', r.id);
  if ((req as any).log && r.id) {
    (req as any).log = (req as any).log.child({ request_id: r.id });
  }
  next();
};
