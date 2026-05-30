type Check = { name: string; fn: () => Promise<boolean> };

let draining = false;
const checks: Check[] = [{ name: 'drain', fn: async () => !draining }];

export function registerCheck(name: string, fn: () => Promise<boolean>) {
  checks.push({ name, fn });
}

export function setDraining(state: boolean) {
  draining = state;
}

export async function readinessSummary() {
  const details = await Promise.all(checks.map(async (check) => ({ name: check.name, ok: await check.fn() })));
  return { ok: details.every((detail) => detail.ok), details };
}
