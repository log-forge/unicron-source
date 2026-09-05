import { randomUUID } from 'node:crypto';
import type { Pool, PoolClient } from 'pg';
import { getPostgresPool } from './postgres';

export interface AuthUser {
  id: string;
  email: string;
  emailVerified: boolean;
  name?: string | null;
  username?: string | null;
  displayUsername?: string | null;
  image?: string | null;
  requiresPasswordChange?: boolean | null;
  createdAt: Date;
  updatedAt: Date;
}

export interface ImportedCredential {
  id?: string;
  accountId?: string;
  password?: string | null;
  createdAt?: Date;
  updatedAt?: Date;
}

type UserUpdates = Partial<Pick<AuthUser, 'email' | 'emailVerified' | 'name' | 'username' | 'displayUsername' | 'requiresPasswordChange'>>;

const userColumns: Record<keyof UserUpdates, string> = {
  email: 'email',
  emailVerified: 'emailVerified',
  name: 'name',
  username: 'username',
  displayUsername: 'displayUsername',
  requiresPasswordChange: 'requiresPasswordChange',
};

export class AuthStore {
  constructor(private readonly pool: Pool = getPostgresPool()) {}

  async listUsers(): Promise<AuthUser[]> {
    const result = await this.pool.query<AuthUser>(
      `SELECT id, email, "emailVerified", name, username, "displayUsername", image,
              "requiresPasswordChange", "createdAt", "updatedAt"
         FROM "user"
        ORDER BY "createdAt", id`,
    );
    return result.rows;
  }

  async createAdmin(user: Omit<AuthUser, 'id' | 'createdAt' | 'updatedAt'> & Partial<Pick<AuthUser, 'id' | 'createdAt' | 'updatedAt'>>, passwordHash: string): Promise<AuthUser> {
    const now = new Date();
    const id = user.id ?? randomUUID();
    const createdAt = user.createdAt ?? now;
    const updatedAt = user.updatedAt ?? now;
    const client = await this.pool.connect();
    try {
      await client.query('BEGIN');
      const created = await this.insertUser(client, { ...user, id, createdAt, updatedAt });
      await this.upsertCredentialWithClient(client, id, passwordHash);
      await client.query('COMMIT');
      return created;
    } catch (err) {
      await client.query('ROLLBACK');
      throw err;
    } finally {
      client.release();
    }
  }

  async importLegacyAdmin(user: AuthUser, credential?: ImportedCredential): Promise<void> {
    const client = await this.pool.connect();
    try {
      await client.query('BEGIN');
      await this.insertUser(client, user);
      if (credential?.password) {
        await this.upsertCredentialWithClient(client, user.id, credential.password, credential);
      }
      await client.query('COMMIT');
    } catch (err) {
      await client.query('ROLLBACK');
      throw err;
    } finally {
      client.release();
    }
  }

  async updateUser(userId: string, updates: UserUpdates): Promise<void> {
    const entries = Object.entries(updates) as Array<[keyof UserUpdates, UserUpdates[keyof UserUpdates]]>;
    if (entries.length === 0) return;

    const assignments = entries.map(([key], index) => `"${userColumns[key]}" = $${index + 2}`);
    const values = entries.map(([, value]) => value);
    await this.pool.query(`UPDATE "user" SET ${assignments.join(', ')}, "updatedAt" = NOW() WHERE id = $1`, [userId, ...values]);
  }

  async credentialExists(userId: string): Promise<boolean> {
    const result = await this.pool.query('SELECT 1 FROM account WHERE "userId" = $1 AND "providerId" = $2 LIMIT 1', [userId, 'credential']);
    return result.rowCount === 1;
  }

  async readCredentialPassword(userId: string): Promise<string | null> {
    const result = await this.pool.query<{ password: string | null }>('SELECT password FROM account WHERE "userId" = $1 AND "providerId" = $2 LIMIT 1', [userId, 'credential']);
    return result.rows[0]?.password ?? null;
  }

  async writeCredential(userId: string, passwordHash: string): Promise<void> {
    const client = await this.pool.connect();
    try {
      await client.query('BEGIN');
      await this.upsertCredentialWithClient(client, userId, passwordHash);
      await client.query('COMMIT');
    } catch (err) {
      await client.query('ROLLBACK');
      throw err;
    } finally {
      client.release();
    }
  }

  async deleteSessions(userId: string): Promise<void> {
    await this.pool.query('DELETE FROM session WHERE "userId" = $1', [userId]);
  }

  async clearPasswordChangeRequirement(userId: string): Promise<void> {
    await this.updateUser(userId, { requiresPasswordChange: false });
  }

  private async insertUser(client: PoolClient, user: AuthUser): Promise<AuthUser> {
    const result = await client.query<AuthUser>(
      `INSERT INTO "user" (
         id, email, "emailVerified", name, username, "displayUsername", image,
         "requiresPasswordChange", "createdAt", "updatedAt"
       ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
       RETURNING id, email, "emailVerified", name, username, "displayUsername", image,
                 "requiresPasswordChange", "createdAt", "updatedAt"`,
      [
        user.id,
        user.email,
        user.emailVerified,
        user.name ?? null,
        user.username ?? null,
        user.displayUsername ?? null,
        user.image ?? null,
        user.requiresPasswordChange ?? false,
        user.createdAt,
        user.updatedAt,
      ],
    );
    return result.rows[0];
  }

  private async upsertCredentialWithClient(client: PoolClient, userId: string, passwordHash: string, imported: ImportedCredential = {}): Promise<void> {
    const updated = await client.query(
      `UPDATE account
          SET password = $3, "updatedAt" = $4
        WHERE "userId" = $1 AND "providerId" = $2`,
      [userId, 'credential', passwordHash, imported.updatedAt ?? new Date()],
    );
    if (updated.rowCount && updated.rowCount > 0) return;

    await client.query(
      `INSERT INTO account (id, "accountId", "providerId", "userId", password, "createdAt", "updatedAt")
       VALUES ($1, $2, $3, $4, $5, $6, $7)`,
      [imported.id ?? randomUUID(), imported.accountId ?? userId, 'credential', userId, passwordHash, imported.createdAt ?? new Date(), imported.updatedAt ?? new Date()],
    );
  }
}

export function getAuthStore(): AuthStore {
  return new AuthStore();
}
