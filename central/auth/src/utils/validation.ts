import { APIError } from 'better-auth/api';
import { z, ZodError, type ZodType } from 'zod';
import { HttpError } from './http-errors';

export type Issue = { path: Array<string | number>; message: string };

function toIssues(err: ZodError): Issue[] {
  return err.issues.map((issue) => ({
    path: issue.path.map((segment) => (typeof segment === 'symbol' ? segment.toString() : segment)) as Array<string | number>,
    message: issue.message,
  }));
}

export function normalizeZodError(err: ZodError) {
  return {
    issues: toIssues(err),
    details: z.flattenError(err),
    message: 'Validation failed',
  } as const;
}

function buildHttpValidationError(err: ZodError, message = 'Validation failed', code = 'BAD_REQUEST', status = 400): HttpError {
  const { issues, details } = normalizeZodError(err);
  const httpErr = new HttpError(status, message, code, details);
  (httpErr as any).issues = issues;
  return httpErr;
}

function buildApiValidationError(err: ZodError, message = 'Validation failed', code: any = 'BAD_REQUEST'): APIError {
  const { issues, details } = normalizeZodError(err);
  return new APIError('BAD_REQUEST', { code, message, details, issues });
}

export function parseOrThrow<S extends ZodType>(schema: S, input: unknown, opts?: { message?: string; code?: string; status?: number }): z.infer<S> {
  const parsed = schema.safeParse(input);
  if (!parsed.success) throw buildHttpValidationError(parsed.error, opts?.message, opts?.code, opts?.status);
  return parsed.data as z.infer<S>;
}

export function parseOrApiError<S extends ZodType>(schema: S, input: unknown, opts?: { message?: string; code?: any }): z.infer<S> {
  const parsed = schema.safeParse(input);
  if (!parsed.success) throw buildApiValidationError(parsed.error, opts?.message, opts?.code);
  return parsed.data as z.infer<S>;
}
