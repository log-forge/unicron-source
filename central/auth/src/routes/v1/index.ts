import { Router } from 'express';
import profileRoutes from './profile.routes';

const router = Router();

router.use(profileRoutes);

export default router;
