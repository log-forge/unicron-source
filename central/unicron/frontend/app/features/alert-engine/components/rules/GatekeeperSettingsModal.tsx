import { useEffect, useMemo, useState } from "react";
import type { GatekeeperSettings, KeywordSettings } from "../../types";
import { apiService } from "../../services/api";
import Modal from "../ui/Modal";
import Button from "../ui/Button";
import TagInput from "../ui/TagInput";
import { KEYWORD_IGNORE_MAX, KEYWORD_IGNORE_MAX_LEN } from "../../constants";
import { HelpCircle, RotateCcw } from "lucide-react";

interface Props {
  isOpen: boolean;
  onClose: () => void;
  onSaved?: () => void;
}

const SUPPRESSIBLE_RULE_TYPES = ["container_event", "keyword", "rate", "threshold"] as const;
const SUPPRESSION_ACTION_TYPES = ["stop", "kill", "restart", "start", "run_script", "notify"] as const;

function toDisplayLabel(value: string): string {
  const normalized = String(value || "").trim().toLowerCase();
  const labels: Record<string, string> = {
    all: "All",
    container_event: "Container Event",
    run_script: "Run Script",
    keyword: "Keyword",
    rate: "Rate",
    threshold: "Threshold",
    stop: "Stop",
    kill: "Kill",
    restart: "Restart",
    start: "Start",
    notify: "Notify",
  };
  return labels[normalized] || normalized.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function normalizeSuppressionRuleTypes(raw: string[]): string[] {
  const selected = new Set(
    (raw || [])
      .map((value) => String(value || "").trim().toLowerCase())
      .filter(Boolean)
  );

  if (selected.size === 0) {
    return ["all", ...SUPPRESSIBLE_RULE_TYPES];
  }

  if (selected.has("all")) {
    return ["all", ...SUPPRESSIBLE_RULE_TYPES];
  }

  const filtered = SUPPRESSIBLE_RULE_TYPES.filter((value) => selected.has(value));
  if (filtered.length === 0) {
    return ["all", ...SUPPRESSIBLE_RULE_TYPES];
  }
  if (filtered.length === SUPPRESSIBLE_RULE_TYPES.length) {
    return ["all", ...SUPPRESSIBLE_RULE_TYPES];
  }
  return filtered;
}

const defaultSettings: GatekeeperSettings = {
  cooldown_minutes: { restart: 5, stop: 3, start: 3, kill: 5, run_script: 10 },
  backoff_delays: [2, 5, 15],
  max_backoff_minutes: 30,
  disable_after_failures: 3,
  disable_duration_minutes: 60,
  max_actions_per_rule_per_hour: 3,
  max_actions_per_container_per_hour: 10,
  verification_delay_seconds: 30,
  trigger_suppression_enabled: true,
  trigger_suppression_minutes: 10,
  trigger_suppression_actions: ["stop", "kill", "restart", "start", "notify"],
  trigger_suppression_rule_types: ["all", ...SUPPRESSIBLE_RULE_TYPES],
  dedup_enabled: true,
  dedup_window_seconds: 900,
};

const defaultKeywordSettings: KeywordSettings = {
  case_sensitive: true,
  multi_mode: 'any',
  ignore_patterns: [],
};

export default function GatekeeperSettingsModal({ isOpen, onClose, onSaved }: Props) {
  const [loadingGatekeeper, setLoadingGatekeeper] = useState(false);
  const [loadingKeywords, setLoadingKeywords] = useState(false);
  const [gatekeeperLoaded, setGatekeeperLoaded] = useState(false);
  const [keywordsLoaded, setKeywordsLoaded] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [settings, setSettings] = useState<GatekeeperSettings>(defaultSettings);
  const [activeTab, setActiveTab] = useState<"actions" | "Thresholds" | "keywords">("actions");
  const [keywordSettings, setKeywordSettings] = useState<KeywordSettings>({ case_sensitive: true, multi_mode: "any", ignore_patterns: [] });
  const selectedSuppressionRuleTypes = normalizeSuppressionRuleTypes(
    settings.trigger_suppression_rule_types || []
  );
  const allSuppressionRuleTypesChecked = selectedSuppressionRuleTypes.includes("all");
  const MAX_IGNORE = KEYWORD_IGNORE_MAX;
  const MAX_PATTERN_LEN = KEYWORD_IGNORE_MAX_LEN;
  const keywordErrors: string[] = [];
  if (keywordSettings.ignore_patterns.length > MAX_IGNORE) keywordErrors.push(`Too many patterns: ${keywordSettings.ignore_patterns.length}/${MAX_IGNORE}`);
  if (keywordSettings.ignore_patterns.some(p => p.length > MAX_PATTERN_LEN)) keywordErrors.push(`Each pattern must be <= ${MAX_PATTERN_LEN} characters`);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoadingGatekeeper(true);
      setError(null);
      try {
        const s = await apiService.getGatekeeperSettings();
        if (!cancelled) {
          setSettings({
            ...defaultSettings,
            ...s,
            dedup_enabled: s.dedup_enabled ?? defaultSettings.dedup_enabled,
            dedup_window_seconds: Math.max(
              1,
              Number(s.dedup_window_seconds ?? defaultSettings.dedup_window_seconds)
            ),
            trigger_suppression_rule_types: normalizeSuppressionRuleTypes(
              s.trigger_suppression_rule_types || []
            ),
          });
          setGatekeeperLoaded(true);
        }
      } catch (e: any) {
        if (!cancelled) setError(e?.message || "Failed to load settings");
      } finally {
        if (!cancelled) setLoadingGatekeeper(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!isOpen || activeTab !== "keywords" || keywordsLoaded) return;
    let cancelled = false;
    (async () => {
      setLoadingKeywords(true);
      setError(null);
      try {
        const ks = await apiService.getKeywordSettings();
        if (!cancelled) {
          setKeywordSettings(ks);
          setKeywordsLoaded(true);
        }
      } catch (e: any) {
        if (!cancelled) setError(e?.message || "Failed to load settings");
      } finally {
        if (!cancelled) setLoadingKeywords(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [isOpen, activeTab, keywordsLoaded]);

  const keywordSaveDisabled = loadingKeywords || saving || keywordErrors.length > 0;
  const keywordSaveDisabledReason = loadingKeywords
    ? "Keyword settings are still loading"
    : saving
      ? "Settings are being saved"
      : keywordErrors[0];
  const gatekeeperSaveDisabled = (loadingGatekeeper && !gatekeeperLoaded) || saving;
  const gatekeeperSaveDisabledReason = loadingGatekeeper && !gatekeeperLoaded
    ? "Gatekeeper settings are still loading"
    : saving
      ? "Settings are being saved"
      : undefined;

  const handleSaveActions = async () => {
    setSaving(true);
    setError(null);
    try {
      const MAX_UI = 99;
      for (const [k, v] of Object.entries(settings.cooldown_minutes)) {
        if ((v as number) > MAX_UI) {
          setError(`Value for "${k}" must be <= ${MAX_UI}.`);
          setSaving(false);
          return;
        }
      }
      for (const v of settings.backoff_delays) {
        if (v > MAX_UI) {
          setError(`Backoff delays must be <= ${MAX_UI} minutes.`);
          setSaving(false);
          return;
        }
      }
      const otherPairs: Array<[string, number]> = [
        ["Max Backoff Minutes", settings.max_backoff_minutes],
        ["Disable After Failures", settings.disable_after_failures],
        ["Disable Duration (minutes)", settings.disable_duration_minutes],
        ["Max Actions per Rule per Hour", settings.max_actions_per_rule_per_hour],
        ["Max Actions per Container per Hour", settings.max_actions_per_container_per_hour],
        ["Verification Delay (seconds)", settings.verification_delay_seconds],
        ["Trigger Suppression Minutes", settings.trigger_suppression_minutes],
      ];
      for (const [label, val] of otherPairs) {
        if (val > MAX_UI) {
          setError(`${label} must be <= ${MAX_UI}.`);
          setSaving(false);
          return;
        }
      }
      if (settings.dedup_window_seconds > 3600) {
        setError("Dedup Window (seconds) must be <= 3600.");
        setSaving(false);
        return;
      }
      if (settings.trigger_suppression_enabled) {
        if (settings.trigger_suppression_actions.length === 0) {
          setError("Select at least one action for trigger suppression.");
          setSaving(false);
          return;
        }
        if (settings.trigger_suppression_rule_types.length === 0) {
          setError("Select at least one rule type for trigger suppression.");
          setSaving(false);
          return;
        }
      }
      const payload: GatekeeperSettings = {
        ...settings,
        trigger_suppression_rule_types: normalizeSuppressionRuleTypes(
          settings.trigger_suppression_rule_types || []
        ),
      };
      const updated = await apiService.updateGatekeeperSettings(payload);
      setSettings({
        ...updated,
        trigger_suppression_rule_types: normalizeSuppressionRuleTypes(
          updated.trigger_suppression_rule_types || []
        ),
      });
      if (onSaved) onSaved();
      onClose();
    } catch (e: any) {
      setError(e?.message || "Failed to save settings");
    } finally {
      setSaving(false);
    }
  };

  const handleSaveKeywords = async () => {
    setSaving(true);
    setError(null);
    try {
      const updated = await apiService.updateKeywordSettings(keywordSettings);
      setKeywordSettings(updated);
      if (onSaved) onSaved();
      onClose();
    } catch (e: any) {
      setError(e?.message || "Failed to save settings");
    } finally {
      setSaving(false);
    }
  };

  // Precomputed help messages
  const help = useMemo(
    () => ({
      cooldown_minutes:
        "Minimum wait time after an action succeeds or fails before the same action can run again on the same container.",
      backoff_delays:
        "Extra delays applied after repeated failures (exponential backoff). Each failure level adds the corresponding delay before the next attempt.",
      max_backoff_minutes:
        "Upper bound for exponential backoff. Prevents backoff from growing beyond this value.",
      disable_after_failures:
        "Number of consecutive failures that will temporarily disable this rule for the container to protect the system.",
      disable_duration_minutes:
        "How long a rule stays disabled after hitting the failure threshold.",
      max_actions_per_rule_per_hour:
        "Global cap per rule across all containers in a rolling hour. Prevents noisy rules from spamming actions.",
      max_actions_per_container_per_hour:
        "Per-container cap in a rolling hour. Prevents a single container from being acted on too frequently.",
      verification_delay_seconds:
        "Delay before verifying that actions like restart/start/stop reached the desired state.",
      trigger_suppression_enabled:
        "After a configured remediation action succeeds, pause matching triggers for the same container for a short window.",
      trigger_suppression_minutes:
        "Suppression window length in minutes after successful remediation.",
      trigger_suppression_actions:
        "Only these successful actions activate suppression.",
      trigger_suppression_rule_types:
        "Only these rule trigger types are suppressed. Default is All.",
      dedup_enabled:
        "Suppress duplicate trigger side effects for the same alert fingerprint within the fixed dedup window.",
      dedup_window_seconds:
        "Deduplication window in seconds. Default is 900 seconds (15 minutes).",
    }),
    []
  );

  const restoreDefaults = () => {
    if (activeTab === 'keywords') {
      setKeywordSettings(defaultKeywordSettings);
    } else {
      setSettings({
        ...defaultSettings,
        cooldown_minutes: { ...defaultSettings.cooldown_minutes },
        backoff_delays: [...defaultSettings.backoff_delays],
        trigger_suppression_actions: [...defaultSettings.trigger_suppression_actions],
        trigger_suppression_rule_types: [...defaultSettings.trigger_suppression_rule_types],
      });
    }
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Advanced Settings">
      <div className="space-y-6">
        <div className="flex gap-3 border-b dark:border-divider">
          <button
            className={`cursor-pointer px-3 py-2 text-sm ${activeTab === 'actions' ? 'border-b-2 border-info text-info' : 'text-neutral-text dark:text-neutral-text'}`}
            onClick={() => setActiveTab('actions')}
          >
            Actions
          </button>
          <button
            className={`cursor-pointer px-3 py-2 text-sm ${activeTab === 'Thresholds' ? 'border-b-2 border-info text-info' : 'text-neutral-text dark:text-neutral-text'}`}
            onClick={() => setActiveTab('Thresholds')}
          >
            Thresholds
          </button>
          <button
            className={`cursor-pointer px-3 py-2 text-sm ${activeTab === 'keywords' ? 'border-b-2 border-info text-info' : 'text-neutral-text dark:text-neutral-text'}`}
            onClick={() => setActiveTab('keywords')}
          >
            Keywords
          </button>
        </div>
        {error && (
          <div className="rounded-md border border-error/30 bg-error/10 p-3 text-sm text-error">
            {error}
          </div>
        )}
        <>
            {activeTab === 'keywords' && (
              <div className="space-y-6">
                <Section
                  title="Keyword Matching"
                  hint="Matching uses simple substrings (not whole-word or regex)."
                >
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <div className="flex items-center gap-2">
                        <input
                          type="checkbox"
                          className="cursor-pointer"
                          checked={keywordSettings.case_sensitive}
                          onChange={(e) => setKeywordSettings(s => ({ ...s, case_sensitive: e.target.checked }))}
                        />
                        <label className="cursor-pointer text-sm text-text">Case-Sensitive Matching</label>
                      </div>
                      {/* No extra explanation for case-sensitive per request */}
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-text mb-1">Multi-keyword Mode</label>
                      <select
                        className="select-modern cursor-pointer text-sm"
                        value={keywordSettings.multi_mode}
                        onChange={(e) => setKeywordSettings(s => ({ ...s, multi_mode: e.target.value as 'any' | 'all' }))}
                      >
                        <option value="any">Any of the keywords</option>
                        <option value="all">All keywords (in the same line)</option>
                      </select>
                      <div className="text-xs text-neutral-text mt-1">
                        {keywordSettings.multi_mode === 'all'
                          ? 'All: a line must contain every keyword (order doesn\'t matter).'
                          : 'Any: a line matches if it contains at least one keyword.'}
                      </div>
                    </div>
                  </div>
                </Section>
                <Section
                  title="Ignore Patterns (one per pattern)"
                  hint="If a log line contains any of these substrings, it is skipped before keyword checks. Case sensitivity follows the toggle above."
                >
                  <TagInput
                    tags={keywordSettings.ignore_patterns || []}
                    onChange={(tags: string[]) => {
                      // normalize, dedupe, cap
                      const seen = new Set<string>();
                      const norms = [] as string[];
                      for (const t of tags) {
                        const s = (t || '').trim();
                        if (!s || s.length > MAX_PATTERN_LEN || seen.has(s)) continue;
                        seen.add(s);
                        norms.push(s);
                        if (norms.length >= MAX_IGNORE) break;
                      }
                      setKeywordSettings(s => ({ ...s, ignore_patterns: norms }));
                    }}
                    placeholder="Type a pattern and press Enter (e.g., healthcheck, readiness probe, retry in 1s)"
                    className="text-sm"
                    helpText={`Type and press Enter`}
                    helpRight={<span>{`${Math.min(keywordSettings.ignore_patterns.length, MAX_IGNORE)}/${MAX_IGNORE}`}</span>}
                  />
                  {keywordErrors.length > 0 && (
                    <div className="mt-1 text-xs text-error">{keywordErrors[0]}</div>
                  )}
                </Section>
              </div>
            )}

            {activeTab === 'Thresholds' && (
              <>
                <Section title="Backoff Delays (minutes)" hint={help.backoff_delays}>
                  <div className="flex flex-row flex-wrap items-center gap-3">
                    {settings.backoff_delays.map((v, i) => (
                      <div key={i} className="flex items-center gap-1">
                        <span className="text-xs text-neutral-text">Step {i + 1}</span>
                        <input
                          type="number"
                          className="w-20 rounded-md border border-divider dark:border-divider dark:bg-foreground dark:text-text px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary transition"
                          min={0}
                          max={99}
                          value={String(v)}
                          onChange={(e) => {
                            const raw = Number(e.target.value);
                            if (Number.isNaN(raw)) return;
                            const clamped = Math.max(0, Math.min(99, raw));
                            setSettings((s) => {
                              const arr = [...s.backoff_delays];
                              arr[i] = clamped;
                              return { ...s, backoff_delays: arr };
                            })
                          }}
                        />
                        <span className="text-xs text-neutral-text">min</span>
                      </div>
                    ))}
                  </div>
                </Section>

                <Section title="Limits & Thresholds">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <NumberInput
                      label="Max Backoff Minutes"
                      hint={help.max_backoff_minutes}
                      value={settings.max_backoff_minutes}
                      min={0}
                      onChange={(val) => setSettings((s) => ({ ...s, max_backoff_minutes: val }))}
                    />
                    <NumberInput
                      label="Disable After Failures"
                      hint={help.disable_after_failures}
                      value={settings.disable_after_failures}
                      min={0}
                      onChange={(val) => setSettings((s) => ({ ...s, disable_after_failures: val }))}
                    />
                    <NumberInput
                      label="Disable Duration (minutes)"
                      hint={help.disable_duration_minutes}
                      value={settings.disable_duration_minutes}
                      min={0}
                      onChange={(val) => setSettings((s) => ({ ...s, disable_duration_minutes: val }))}
                    />
                    <NumberInput
                      label="Max Actions per Rule per Hour"
                      hint={help.max_actions_per_rule_per_hour}
                      value={settings.max_actions_per_rule_per_hour}
                      min={0}
                      onChange={(val) => setSettings((s) => ({ ...s, max_actions_per_rule_per_hour: val }))}
                    />
                    <NumberInput
                      label="Max Actions per Container per Hour"
                      hint={help.max_actions_per_container_per_hour}
                      value={settings.max_actions_per_container_per_hour}
                      min={0}
                      onChange={(val) => setSettings((s) => ({ ...s, max_actions_per_container_per_hour: val }))}
                    />
                    <NumberInput
                      label="Verification Delay (seconds)"
                      hint={help.verification_delay_seconds}
                      value={settings.verification_delay_seconds}
                      min={0}
                      onChange={(val) => setSettings((s) => ({ ...s, verification_delay_seconds: val }))}
                    />
                  </div>
                </Section>
              </>
            )}

            {activeTab === 'actions' && (
              <>
              <Section title="Cooldown Minutes (by action)" hint={help.cooldown_minutes}>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {Object.entries(settings.cooldown_minutes).map(([k, v]) => (
                    <NumberInput
                      key={k}
                      label={toDisplayLabel(k)}
                      hint="Minutes between repeated actions"
                      value={v}
                      min={0}
                      onChange={(val) =>
                        setSettings((s) => ({
                          ...s,
                          cooldown_minutes: { ...s.cooldown_minutes, [k]: val },
                        }))
                      }
                    />
                  ))}
                </div>
              </Section>

              <Section title="Trigger Suppression" hint={help.trigger_suppression_enabled}>
                <div className="space-y-4">
                  <div className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      className="cursor-pointer"
                      checked={settings.trigger_suppression_enabled}
                      onChange={(e) =>
                        setSettings((s) => ({
                          ...s,
                          trigger_suppression_enabled: e.target.checked,
                        }))
                      }
                    />
                    <label className="cursor-pointer text-sm text-text">Enable post-remediation trigger suppression</label>
                  </div>

                  {settings.trigger_suppression_enabled && (
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <NumberInput
                        label="Suppression Window (minutes)"
                        hint={help.trigger_suppression_minutes}
                        value={settings.trigger_suppression_minutes}
                        min={0}
                        onChange={(val) =>
                          setSettings((s) => ({ ...s, trigger_suppression_minutes: val }))
                        }
                      />

                      <div className="w-full flex flex-col gap-2 text-sm text-text">
                        <label className="flex items-center gap-2">
                          <span className="font-medium text-text">Rule Types to Suppress</span>
                          <Tooltip content={help.trigger_suppression_rule_types} />
                        </label>
                        <div className="flex flex-wrap gap-2">
                          {["all", ...SUPPRESSIBLE_RULE_TYPES].map((ruleType) => {
                            const checked = ruleType === "all"
                              ? allSuppressionRuleTypesChecked
                              : allSuppressionRuleTypesChecked || selectedSuppressionRuleTypes.includes(ruleType);
                            return (
                              <label key={ruleType} className="inline-flex cursor-pointer items-center gap-2 rounded border border-divider px-2 py-1">
                                <input
                                  type="checkbox"
                                  className="cursor-pointer"
                                  checked={checked}
                                  onChange={(e) => {
                                    setSettings((s) => {
                                      if (ruleType === "all") {
                                        return {
                                          ...s,
                                          trigger_suppression_rule_types: e.target.checked
                                            ? ["all", ...SUPPRESSIBLE_RULE_TYPES]
                                            : [],
                                        };
                                      }

                                      const next = new Set(
                                        normalizeSuppressionRuleTypes(s.trigger_suppression_rule_types || [])
                                          .filter((value) => value !== "all")
                                      );
                                      if (e.target.checked) {
                                        next.add(ruleType);
                                      } else {
                                        next.delete(ruleType);
                                      }
                                      return {
                                        ...s,
                                        trigger_suppression_rule_types: normalizeSuppressionRuleTypes(
                                          Array.from(next)
                                        ),
                                      };
                                    });
                                  }}
                                />
                                <span className="text-xs">{toDisplayLabel(ruleType)}</span>
                              </label>
                            );
                          })}
                        </div>
                      </div>

                      <div className="w-full flex flex-col gap-2 text-sm text-text md:col-span-2">
                        <label className="flex items-center gap-2">
                          <span className="font-medium text-text">Actions That Activate Suppression</span>
                          <Tooltip content={help.trigger_suppression_actions} />
                        </label>
                        <div className="flex flex-wrap gap-2">
                          {SUPPRESSION_ACTION_TYPES.map((actionType) => {
                            const checked = settings.trigger_suppression_actions.includes(actionType);
                            return (
                              <label key={actionType} className="inline-flex cursor-pointer items-center gap-2 rounded border border-divider px-2 py-1">
                                <input
                                  type="checkbox"
                                  className="cursor-pointer"
                                  checked={checked}
                                  onChange={(e) => {
                                    setSettings((s) => {
                                      const next = new Set(s.trigger_suppression_actions);
                                      if (e.target.checked) next.add(actionType);
                                      else next.delete(actionType);
                                      return {
                                        ...s,
                                        trigger_suppression_actions: Array.from(next),
                                      };
                                    });
                                  }}
                                />
                                <span className="text-xs">{toDisplayLabel(actionType)}</span>
                              </label>
                            );
                          })}
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              </Section>

              <Section title="Alert Deduplication" hint={help.dedup_enabled}>
                <div className="space-y-4">
                  <div className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      className="cursor-pointer"
                      checked={settings.dedup_enabled}
                      onChange={(e) =>
                        setSettings((s) => ({
                          ...s,
                          dedup_enabled: e.target.checked,
                        }))
                      }
                    />
                    <label className="cursor-pointer text-sm text-text">Enable duplicate trigger suppression</label>
                  </div>

                  {settings.dedup_enabled && (
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <NumberInput
                        label="Dedup Window (seconds)"
                        hint={help.dedup_window_seconds}
                        value={settings.dedup_window_seconds}
                        min={1}
                        max={3600}
                        onChange={(val) =>
                          setSettings((s) => ({ ...s, dedup_window_seconds: val }))
                        }
                      />
                    </div>
                  )}
                </div>
              </Section>

              {/* Backoff moved to its own tab */}

              {/* Limits moved to Backoff tab */}
              </>
            )}
          </>
        <div className="flex items-center justify-between gap-3 border-t pt-4">
          <div>
            <Button
              variant="outline"
              size="sm"
              onClick={restoreDefaults}
              title="Restore all values to their default recommendations"
            >
              <RotateCcw className="w-4 h-4 mr-2" /> Restore to default
            </Button>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" onClick={onClose}>Cancel</Button>
            {activeTab === 'keywords' ? (
              <Button
                onClick={handleSaveKeywords}
                loading={saving}
                disabled={keywordSaveDisabled}
                title={keywordSaveDisabledReason}
              >
                Save Settings
              </Button>
            ) : (
              <Button
                onClick={handleSaveActions}
                loading={saving}
                disabled={gatekeeperSaveDisabled}
                title={gatekeeperSaveDisabledReason}
              >
                Save Settings
              </Button>
            )}
          </div>
        </div>
      </div>
    </Modal>
  );
}

function Section({ title, hint, children }: { title: string; hint?: string; children: React.ReactNode }) {
  return (
    <section>
      <div className="mb-2 flex items-center gap-2">
        <h4 className="text-sm font-semibold text-text">{title}</h4>
        {hint && (
          <Tooltip content={hint} />
        )}
      </div>
      {children}
    </section>
  );
}

function NumberInput({
  label,
  hint,
  value,
  min = 0,
  max = 99,
  onChange,
}: {
  label: string;
  hint?: string;
  value: number;
  min?: number;
  max?: number;
  onChange: (val: number) => void;
}) {
  return (
    <div className="w-full flex flex-col gap-1 text-sm text-text">
      <label className="flex items-center gap-2">
        <span className="font-medium text-text">{label}</span>
        {hint && <Tooltip content={hint} />}
      </label>
      <input
        type="number"
        className="w-full rounded-lg border border-divider dark:border-divider dark:bg-foreground dark:text-text px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary transition"
        min={min}
        max={max}
        value={String(value)}
        onChange={(e) => {
          const raw = Number(e.target.value);
          if (Number.isNaN(raw)) return;
          const clamped = Math.max(min, Math.min(max, raw));
          onChange(clamped);
        }}
      />
      <div className="text-xs text-neutral-text">Max {max}</div>
    </div>
  );
}

function Tooltip({ content }: { content: string }) {
  return (
    <span className="relative group inline-flex items-center">
      <HelpCircle className="w-4 h-4 text-neutral-text group-hover:text-neutral-text dark:group-hover:text-neutral-text" />
      <span className="pointer-events-none absolute z-10 mt-6 hidden w-72 group-hover:block rounded-lg border border-divider dark:border-divider bg-background dark:bg-foreground p-3 text-xs text-text dark:text-text shadow-lg">
        {content}
      </span>
    </span>
  );
}
