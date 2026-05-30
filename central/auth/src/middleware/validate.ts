import type { NextFunction, Request, RequestHandler, Response } from 'express';

type VHandler = (req: Request, res: Response, next: NextFunction) => unknown | Promise<unknown>;

export function controller(handler: VHandler): RequestHandler {
  return async (req, res, next) => {
    try {
      await handler(req, res, next);
    } catch (err) {
      next(err);
    }
  };
}
