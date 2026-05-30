import { z } from 'zod';
import { USERNAME_MAX, USERNAME_MIN, USERNAME_REGEX } from '../constants';

export function normalizeUsername(username: string): string {
  return username.trim().toLowerCase();
}

export const UsernameSchema = z
  .string()
  .trim()
  .min(USERNAME_MIN, `Username must be at least ${USERNAME_MIN} characters long`)
  .max(USERNAME_MAX, `Username cannot exceed ${USERNAME_MAX} characters`)
  .transform((value) => value.toLowerCase())
  .refine((value) => USERNAME_REGEX.test(value), 'Username may only contain lowercase letters, numbers, dots, underscores, and hyphens');

export const UsernameInput = z.object({ username: UsernameSchema });
