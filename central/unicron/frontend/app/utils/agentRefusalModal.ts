import type { AgentFailure } from "./agentFailure";

type AgentRefusalStorage = Pick<Storage, "getItem" | "setItem"> &
  Partial<Pick<Storage, "key" | "length" | "removeItem">>;

const fallbackShownKeys = new Set<string>();

export type AgentRefusalModalData = {
  herald_id: string;
  herald_name: string;
  reason?: string | null;
  failure: AgentFailure;
};

export type AgentRefusalSource = {
  herald_id?: string | null;
  herald_name?: string | null;
  agent_id?: string | null;
  agent_name?: string | null;
  status?: string | null;
  reason?: string | null;
  failure?: AgentFailure | null;
};

function getSessionStorage(): AgentRefusalStorage | null {
  if (typeof window === "undefined") return null;
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

function storageHas(storage: AgentRefusalStorage | null | undefined, key: string): boolean {
  if (storage) {
    try {
      return storage.getItem(key) === "1";
    } catch {
      return fallbackShownKeys.has(key);
    }
  }
  return fallbackShownKeys.has(key);
}

function storageSet(storage: AgentRefusalStorage | null | undefined, key: string): void {
  if (storage) {
    try {
      storage.setItem(key, "1");
      return;
    } catch {
      fallbackShownKeys.add(key);
      return;
    }
  }
  fallbackShownKeys.add(key);
}

function buildAgentRefusalModalKeyPrefix(agentName: string): string | null {
  const normalizedAgentName = String(agentName || "").trim();
  if (!normalizedAgentName) return null;
  return `agent-refused:${normalizedAgentName}:`;
}

function clearMatchingStorageKeys(storage: AgentRefusalStorage | null | undefined, prefix: string): number {
  if (!storage || typeof storage.key !== "function" || typeof storage.removeItem !== "function") {
    return 0;
  }

  const keys: string[] = [];
  try {
    const length = typeof storage.length === "number" ? storage.length : 0;
    for (let idx = 0; idx < length; idx += 1) {
      const key = storage.key(idx);
      if (key?.startsWith(prefix)) keys.push(key);
    }
  } catch {
    return 0;
  }

  let cleared = 0;
  for (const key of keys) {
    try {
      storage.removeItem(key);
      cleared += 1;
    } catch {
      // Ignore storage failures; fallback keys are cleared separately.
    }
  }
  return cleared;
}

export function clearAgentRefusalModalClaims(agentName: string, storage?: AgentRefusalStorage | null): number {
  const prefix = buildAgentRefusalModalKeyPrefix(agentName);
  if (!prefix) return 0;

  let cleared = 0;
  for (const key of Array.from(fallbackShownKeys)) {
    if (key.startsWith(prefix)) {
      fallbackShownKeys.delete(key);
      cleared += 1;
    }
  }

  const targetStorage = storage === undefined ? getSessionStorage() : storage;
  return cleared + clearMatchingStorageKeys(targetStorage, prefix);
}

export function isAgentRefusalFailure(failure?: AgentFailure | null): failure is AgentFailure {
  return Boolean(failure?.code);
}

export function normalizeAgentRefusal(source: AgentRefusalSource): AgentRefusalModalData | null {
  if (!isAgentRefusalFailure(source.failure)) return null;

  const heraldName = String(source.herald_name || source.agent_name || source.herald_id || source.agent_id || "").trim();
  if (!heraldName) return null;

  const heraldId = String(source.herald_id || source.agent_id || heraldName).trim() || heraldName;

  return {
    herald_id: heraldId,
    herald_name: heraldName,
    reason: source.reason,
    failure: source.failure,
  };
}

export function buildAgentRefusalModalKey(source: AgentRefusalSource): string | null {
  const refusal = normalizeAgentRefusal(source);
  if (!refusal) return null;

  return `agent-refused:${refusal.herald_name}:${refusal.failure.code}`;
}

export function claimAgentRefusalModal(source: AgentRefusalSource, storage?: AgentRefusalStorage | null): AgentRefusalModalData | null {
  const refusal = normalizeAgentRefusal(source);
  if (!refusal) return null;

  const key = buildAgentRefusalModalKey(refusal);
  if (!key) return null;

  const targetStorage = storage === undefined ? getSessionStorage() : storage;
  if (storageHas(targetStorage, key)) return null;

  storageSet(targetStorage, key);
  return refusal;
}

export function openAgentRefusalModalOnce(
  source: AgentRefusalSource,
  openModal: (refusal: AgentRefusalModalData) => void,
  storage?: AgentRefusalStorage | null,
): boolean {
  const refusal = claimAgentRefusalModal(source, storage);
  if (!refusal) return false;

  openModal(refusal);
  return true;
}

export function findFirstBlockedAgentRefusal(agents: AgentRefusalSource[]): AgentRefusalModalData | null {
  for (const agent of agents) {
    if (agent.status !== "blocked") continue;
    const refusal = normalizeAgentRefusal(agent);
    if (refusal) return refusal;
  }
  return null;
}

export function openFirstBlockedAgentRefusalOnce(
  agents: AgentRefusalSource[],
  openModal: (refusal: AgentRefusalModalData) => void,
  storage?: AgentRefusalStorage | null,
): boolean {
  const refusal = findFirstBlockedAgentRefusal(agents);
  if (!refusal) return false;

  return openAgentRefusalModalOnce(refusal, openModal, storage);
}
