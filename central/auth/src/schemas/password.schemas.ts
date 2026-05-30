import { z } from 'zod';
import { PASSWORD_MAX, PASSWORD_MIN } from '../constants';

export const PasswordSchema = z
  .string()
  .min(PASSWORD_MIN, `Password must be at least ${PASSWORD_MIN} characters long`)
  .max(PASSWORD_MAX, `Password cannot exceed ${PASSWORD_MAX} characters`)
  .regex(/[A-Z]/, 'Password must include an uppercase letter')
  .regex(/[a-z]/, 'Password must include a lowercase letter')
  .regex(/[0-9]/, 'Password must include a number')
  .regex(/[^A-Za-z0-9]/, 'Password must include a special character');

export const NewPasswordInput = z.object({ newPassword: PasswordSchema });
