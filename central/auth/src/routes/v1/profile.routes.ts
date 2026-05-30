import { Router } from 'express';
import { getProfile } from './profile.controller';

const router = Router();

router.get('/profile', getProfile);

export default router;
