import { z } from "zod";

// Match the server-side password strength rules used in auth.ts
export const PASSWORD_MIN = 8;
export const PASSWORD_MAX = 128;

export const PasswordSchema = z
  .string()
  .min(PASSWORD_MIN, `Password must be at least ${PASSWORD_MIN} characters long`)
  .max(PASSWORD_MAX, `Password cannot exceed ${PASSWORD_MAX} characters`)
  .regex(/[A-Z]/, "Password must include an uppercase letter")
  .regex(/[a-z]/, "Password must include a lowercase letter")
  .regex(/[0-9]/, "Password must include a number")
  .regex(/[^A-Za-z0-9]/, "Password must include a special character");

export const SignInPasswordSchema = z.string().min(1, "Enter your password").max(PASSWORD_MAX, `Password cannot exceed ${PASSWORD_MAX} characters`);

export const sanitizeUsername = (raw: string) =>
  raw
    .toLowerCase()
    .replace(/[^a-z0-9._-]/g, "")
    .slice(0, 30);

export const UsernameSchema = z.preprocess(
  (value) => sanitizeUsername(String(value ?? "")),
  z
    .string()
    .min(3, "Username must be at least 3 characters")
    .max(30, "Username cannot exceed 30 characters")
    .regex(/^[a-z0-9._-]+$/, "Use lowercase letters, numbers, dots, underscores, and hyphens only"),
);

export const EmailSchema = z.email("Enter a valid email address").trim().toLowerCase();

export const FullNameSchema = z.string().trim().min(3, "Full name must be at least 3 characters").max(100, "Full name cannot exceed 100 characters");

export const CountrySchema = z.string().trim().min(2, "Select a country").max(60, "Country name cannot exceed 60 characters");

export const SignUpSchema = z.object({
  name: UsernameSchema,
  email: EmailSchema,
  fullName: FullNameSchema,
  country: CountrySchema,
  password: PasswordSchema,
});

export type SignUpInput = z.infer<typeof SignUpSchema>;

export const SignInSchema = z.object({
  username: UsernameSchema,
  password: SignInPasswordSchema,
});

export type SignInInput = z.infer<typeof SignInSchema>;
