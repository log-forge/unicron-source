import { randomBytes } from 'node:crypto';
import { hashPassword } from 'better-auth/crypto';
import { DEFAULT_CENTRAL_ADMIN_PASSWORD, LOCAL_EMAIL_DOMAIN } from '../constants';
import { env } from '../config/env';
import { logger } from '../logging/logger';
import { AccountModel } from '../models/account.model';
import { SessionModel } from '../models/session.model';
import { UserModel, type IUser } from '../models/user.model';
import { PasswordSchema } from '../schemas/password.schemas';
import { UsernameSchema } from '../schemas/username.schemas';

export function configuredAdminUsername(): string {
  return UsernameSchema.parse(env.CENTRAL_ADMIN_USERNAME);
}

export function syntheticEmailForUsername(username: string): string {
  return `${username}@${LOCAL_EMAIL_DOMAIN}`;
}

function isDefaultAdminBootstrapPassword(password?: string | null): boolean {
  return String(password ?? '') === DEFAULT_CENTRAL_ADMIN_PASSWORD;
}

function configuredAdminPassword(): string | null {
  const password = env.CENTRAL_ADMIN_PASSWORD;
  return typeof password === 'string' && password.length > 0 ? password : null;
}

function generateFirstBootPassword(): string {
  return `Unicron-${randomBytes(18).toString('base64url')}-A1!`;
}

function passwordPolicyError(password: string): string | null {
  const parsed = PasswordSchema.safeParse(password);
  if (parsed.success) return null;
  return parsed.error.issues.map((issue) => issue.message).join('; ');
}

function usernameForUser(user: Pick<IUser, 'username' | 'name' | 'email'>): string {
  if (user.username) return String(user.username).trim().toLowerCase();
  if (user.name) return String(user.name).trim().toLowerCase();
  const email = String(user.email ?? '').trim().toLowerCase();
  return email.endsWith(`@${LOCAL_EMAIL_DOMAIN}`) ? email.slice(0, -1 * (`@${LOCAL_EMAIL_DOMAIN}`).length) : email;
}

async function writeCredential(user: IUser, password: string) {
  const passwordHash = await hashPassword(password);

  await AccountModel.updateOne(
    { userId: user._id, providerId: 'credential' },
    {
      $set: {
        userId: user._id,
        accountId: user._id.toString(),
        providerId: 'credential',
        password: passwordHash,
      },
    },
    { upsert: true },
  );
}

async function ensureCredentialIfMissing(user: IUser, password: string) {
  const existingAccount = await AccountModel.findOne({ userId: user._id, providerId: 'credential' });
  if (existingAccount) return;
  await writeCredential(user, password);
}

async function createAdminUser(username: string, password: string, requiresPasswordChange: boolean) {
  const admin = await UserModel.create({
    email: syntheticEmailForUsername(username),
    emailVerified: true,
    username,
    displayUsername: username,
    name: username,
    requiresPasswordChange,
  });

  await writeCredential(admin, password);
  return admin;
}

async function alignAdminIdentity(user: IUser, username: string, requiresPasswordChange?: boolean) {
  const update: Record<string, unknown> = {
    email: syntheticEmailForUsername(username),
    emailVerified: true,
    username,
    displayUsername: username,
    name: username,
  };

  if (typeof requiresPasswordChange === 'boolean') {
    update.requiresPasswordChange = requiresPasswordChange;
  }

  await UserModel.updateOne({ _id: user._id }, { $set: update });
  Object.assign(user, update);
}

export async function bootstrapLocalAdmin(): Promise<void> {
  const username = configuredAdminUsername();
  const configuredPassword = configuredAdminPassword();

  const users = await UserModel.find().sort({ createdAt: 1 });

  if (users.length > 1) {
    throw new Error(`central/auth bootstrap found ${users.length} existing users. Local appliance auth supports exactly one administrator account.`);
  }

  if (users.length === 0) {
    const generated = !configuredPassword;
    const password = configuredPassword ?? generateFirstBootPassword();
    const passwordError = passwordPolicyError(password);

    if (passwordError) {
      throw new Error(`CENTRAL_ADMIN_PASSWORD does not meet the password policy: ${passwordError}`);
    }

    const requiresPasswordChange = generated || isDefaultAdminBootstrapPassword(password);
    const admin = await createAdminUser(username, password, requiresPasswordChange);

    if (generated) {
      logger.warn(
        { userId: admin._id.toString(), username, generatedPassword: password, requiresPasswordChange },
        'Local admin first-boot generated administrator credential',
      );
    } else {
      logger.info(
        { userId: admin._id.toString(), username, recoveryOverride: env.CENTRAL_ADMIN_RECOVERY_OVERRIDE, requiresPasswordChange },
        'Local admin bootstrap created administrator',
      );
    }
    return;
  }

  const [existing] = users;

  if (env.CENTRAL_ADMIN_RECOVERY_OVERRIDE) {
    if (!configuredPassword) {
      throw new Error('CENTRAL_ADMIN_RECOVERY_OVERRIDE requires CENTRAL_ADMIN_PASSWORD to be set.');
    }

    const passwordError = passwordPolicyError(configuredPassword);
    if (passwordError) {
      throw new Error(`CENTRAL_ADMIN_PASSWORD does not meet the password policy: ${passwordError}`);
    }

    await alignAdminIdentity(existing, username, true);
    await writeCredential(existing, configuredPassword);
    await SessionModel.deleteMany({ userId: existing._id });
    logger.warn({ userId: existing._id.toString(), username }, 'Local admin recovery rotated administrator credential and revoked sessions');
    return;
  }

  const existingUsername = usernameForUser(existing);
  if (existingUsername !== username) {
    throw new Error(
      `central/auth bootstrap found existing admin username "${existingUsername}" but CENTRAL_ADMIN_USERNAME is "${username}". ` +
        'Set CENTRAL_ADMIN_RECOVERY_OVERRIDE=true only for an operator recovery flow.',
    );
  }

  const identityUpdates: Record<string, unknown> = {};
  if (existing.email !== syntheticEmailForUsername(username)) identityUpdates.email = syntheticEmailForUsername(username);
  if (!existing.emailVerified) identityUpdates.emailVerified = true;
  if (!existing.username) identityUpdates.username = username;
  if (!existing.displayUsername) identityUpdates.displayUsername = username;
  if (!existing.name) identityUpdates.name = username;

  if (Object.keys(identityUpdates).length > 0) {
    await UserModel.updateOne({ _id: existing._id }, { $set: identityUpdates });
  }

  const existingAccount = await AccountModel.findOne({ userId: existing._id, providerId: 'credential' });
  if (!existingAccount) {
    if (!configuredPassword) {
      throw new Error('central/auth bootstrap found an existing administrator without a credential. Set CENTRAL_ADMIN_PASSWORD once to repair it.');
    }

    const passwordError = passwordPolicyError(configuredPassword);
    if (passwordError) {
      throw new Error(`CENTRAL_ADMIN_PASSWORD does not meet the password policy: ${passwordError}`);
    }

    await ensureCredentialIfMissing(existing, configuredPassword);
  } else if (configuredPassword) {
    logger.warn(
      { userId: existing._id.toString(), username, recoveryOverride: false, sessionsRevoked: false },
      'Configured CENTRAL_ADMIN_PASSWORD is intentionally ignored on normal restart; use CENTRAL_ADMIN_RECOVERY_OVERRIDE=true for credential recovery.',
    );
  }
  logger.info({ userId: existing._id.toString(), username, recoveryOverride: false }, 'Local admin bootstrap reused existing administrator');
}
