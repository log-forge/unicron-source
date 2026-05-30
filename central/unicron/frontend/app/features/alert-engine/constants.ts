// Shared frontend constants for Alert Engine UI
// Read from Vite env so docker-compose can control via a single env var.

const toNumber = (v: any, fallback: number) => {
  const n = Number(v);
  return Number.isFinite(n) && n > 0 ? n : fallback;
};

export const KEYWORD_IGNORE_MAX = toNumber(import.meta.env.VITE_KEYWORD_IGNORE_MAX, 10);
export const KEYWORD_IGNORE_MAX_LEN = toNumber(import.meta.env.VITE_KEYWORD_IGNORE_MAX_LEN, 100);

export const FRONTEND_LOG_LEVEL = String(import.meta.env.VITE_FRONTEND_LOG_LEVEL || 'info').toLowerCase();
export const feDebug = () => FRONTEND_LOG_LEVEL === 'debug';
