import { fromNodeHeaders } from 'better-auth/node';
import { DEPLOYMENT_ID } from '../../constants';
import { getAuth } from '../../lib/auth';
import { controller } from '../../middleware/validate';
import { HttpError } from '../../utils/http-errors';

function serializeDate(value: unknown): string | undefined {
  if (!value) return undefined;
  if (value instanceof Date) return value.toISOString();
  const date = new Date(String(value));
  return Number.isNaN(date.valueOf()) ? undefined : date.toISOString();
}

function serializeUser(user: any) {
  const username = typeof user.username === 'string' ? user.username : typeof user.name === 'string' ? user.name : undefined;

  return {
    id: user.id,
    username,
    displayUsername: typeof user.displayUsername === 'string' ? user.displayUsername : username,
    name: typeof user.name === 'string' ? user.name : username,
    image: user.image ?? null,
    createdAt: serializeDate(user.createdAt),
    updatedAt: serializeDate(user.updatedAt),
  };
}

function serializeSession(session: any) {
  return {
    id: session.id,
    userId: session.userId,
    expiresAt: serializeDate(session.expiresAt),
    createdAt: serializeDate(session.createdAt),
    updatedAt: serializeDate(session.updatedAt),
  };
}

export const getProfile = controller(async (req, res) => {
  const auth = getAuth();
  const session = await auth.api.getSession({ headers: fromNodeHeaders(req.headers) });

  if (!session?.user || !session?.session) {
    throw new HttpError(401, 'Unauthorized', 'UNAUTHORIZED');
  }

  const requiresPasswordChange = Boolean((session.user as any).requiresPasswordChange);

  return res.json({
    status: 'ok',
    data: {
      user: serializeUser(session.user),
      session: serializeSession(session.session),
      isAdmin: true,
      deploymentId: DEPLOYMENT_ID,
      requiresPasswordChange,
    },
  });
});
