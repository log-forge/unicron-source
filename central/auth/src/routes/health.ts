import { Router } from 'express';
import { readinessSummary } from '../utils/readiness';

const health = Router();

health.get('/', (_req, res) => res.status(200).json({ status: 'ok' }));

export const readinessRouter = Router();

readinessRouter.get('/', async (_req, res) => {
  const summary = await readinessSummary();
  res.status(summary.ok ? 200 : 503).json(summary);
});

export default health;
