import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { Check, Copy, X } from "lucide-react";

interface PushTelemetryGuideProps {
  hostId?: string;
  buttonLabel?: string;
  fluentAddress?: string;
  className?: string;
  disabled?: boolean;
}

type SnippetKey = "defaults" | "service" | "single";

function buildDefaultsSnippet(fluentAddress: string): string {
  return [
    "x-push-logging: &push_logging",
    "  driver: fluentd",
    "  options:",
    `    fluentd-address: "${fluentAddress}"`,
    '    fluentd-async: "true"',
    '    fluentd-async-reconnect-interval: "2s"',
    '    fluentd-sub-second-precision: "true"',
    '    tag: "app.{{.Name}}"',
    "",
    "x-push-defaults: &push_defaults",
    "  labels:",
    '    unicron.telemetry.mode: "push"',
    "  logging: *push_logging",
  ].join("\n");
}

const SERVICE_SNIPPET = [
  "<<: *push_defaults",
  "",
  "For example:",
  "",
  "services:",
  "  my-service:",
  "    <<: *push_defaults",
  "    image: your-image:latest",
].join("\n");

const SINGLE_SERVICE_SNIPPET = [
  "services:",
  "  my-service:",
  "    image: your-image:latest",
  "    labels:",
  '      unicron.telemetry.mode: "push"',
  "    logging:",
  "      driver: fluentd",
  "      options:",
  '        fluentd-address: "${AGENT_FLUENTD_ADDRESS}"',
  '        fluentd-async: "true"',
  '        fluentd-async-reconnect-interval: "2s"',
  '        fluentd-sub-second-precision: "true"',
  '        tag: "app.{{.Name}}"',
].join("\n");

export default function PushTelemetryGuide({
  hostId,
  buttonLabel = "Setup Push Telemetry",
  fluentAddress = "127.0.0.1:24224",
  className,
  disabled = false,
}: PushTelemetryGuideProps) {
  const [copied, setCopied] = useState<SnippetKey | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);

  const defaultsSnippet = useMemo(
    () => buildDefaultsSnippet(fluentAddress),
    [fluentAddress]
  );

  useEffect(() => {
    if (!copied) return;
    const timer = window.setTimeout(() => setCopied(null), 1800);
    return () => window.clearTimeout(timer);
  }, [copied]);

  useEffect(() => {
    if (!isModalOpen) return;

    const original = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setIsModalOpen(false);
    };
    window.addEventListener("keydown", onKeyDown);

    return () => {
      document.body.style.overflow = original || "";
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [isModalOpen]);

  const copySnippet = async (key: SnippetKey, text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(key);
    } catch {
      setCopied(null);
    }
  };

  return (
    <>
      <button
        type="button"
        disabled={disabled}
        onClick={() => setIsModalOpen(true)}
        className={
          className ||
          "inline-flex cursor-pointer items-center justify-center rounded-md border border-primary/40 bg-primary/10 px-3 py-1.5 text-xs font-medium text-primary transition hover:bg-primary/20 disabled:cursor-not-allowed disabled:opacity-50"
        }
      >
        {buttonLabel}
      </button>

      {isModalOpen && typeof document !== "undefined"
        ? createPortal(
            <div className="fixed inset-0 z-[120] animate-fade-in">
              <div
                className="fixed inset-0 bg-black/50 backdrop-blur-sm transition-opacity"
                onClick={() => setIsModalOpen(false)}
              />
              <div className="fixed inset-0 flex items-center justify-center p-4 pointer-events-none">
                <div
                  className="pointer-events-auto relative flex max-h-[90vh] w-[min(94vw,64rem)] flex-col rounded-xl border border-neutral/20 bg-background shadow-2xl"
                  onClick={(event) => event.stopPropagation()}
                >
                  <div className="flex flex-shrink-0 items-center justify-between border-b border-neutral/20 px-4 py-3">
                    <h3 className="text-base font-semibold text-text">
                      Push Telemetry Setup
                    </h3>
                    <button
                      type="button"
                      onClick={() => setIsModalOpen(false)}
                      className="flex h-7 w-7 cursor-pointer items-center justify-center rounded-full transition-colors hover:bg-neutral/10"
                      aria-label="Close setup guide"
                    >
                      <X className="h-4 w-4 text-neutral" />
                    </button>
                  </div>

                  <div className="flex-1 overflow-y-auto px-4 py-3">
                    <div className="flex flex-col gap-sm">
                      <p className="text-sm text-neutral">
                        Copy paste this at the top of your compose file. This
                        enables push-mode logs using Fluentd and adds the
                        required label for push telemetry.
                      </p>

                      <div className="flex flex-wrap gap-xs text-xs text-neutral">
                        <span className="rounded-full border border-neutral/20 bg-background px-2 py-1 font-mono text-text">
                          Fluent Forward 24224
                        </span>
                        <span className="rounded-full border border-neutral/20 bg-background px-2 py-1 font-mono text-text">
                          Fluent HTTP 9880
                        </span>
                        <span className="rounded-full border border-neutral/20 bg-background px-2 py-1 font-mono text-text">
                          OTLP Metrics 4318
                        </span>
                        <span className="rounded-full border border-neutral/20 bg-background px-2 py-1 font-mono text-text">
                          host {hostId ?? "agent"}
                        </span>
                      </div>

                      <div className="rounded-lg border border-neutral/20 bg-background/80">
                        <div className="flex items-center justify-between border-b border-neutral/20 px-sm py-xs">
                          <span className="text-xs font-medium text-text">
                            Compose top block
                          </span>
                          <button
                            type="button"
                            onClick={() => copySnippet("defaults", defaultsSnippet)}
                            className="inline-flex cursor-pointer items-center gap-1 rounded px-2 py-1 text-xs text-neutral transition hover:bg-neutral/10 hover:text-text"
                          >
                            {copied === "defaults" ? (
                              <Check className="h-3.5 w-3.5" />
                            ) : (
                              <Copy className="h-3.5 w-3.5" />
                            )}
                            {copied === "defaults" ? "Copied" : "Copy"}
                          </button>
                        </div>
                        <pre className="max-h-64 overflow-auto px-sm py-xs text-xs text-text">
                          <code>{defaultsSnippet}</code>
                        </pre>
                      </div>

                      <p className="text-sm text-neutral">
                        Then add the following for your service in that same
                        compose file.
                      </p>

                      <div className="rounded-lg border border-neutral/20 bg-background/80">
                        <div className="flex items-center justify-between border-b border-neutral/20 px-sm py-xs">
                          <span className="text-xs font-medium text-text">
                            Service usage
                          </span>
                          <button
                            type="button"
                            onClick={() => copySnippet("service", SERVICE_SNIPPET)}
                            className="inline-flex cursor-pointer items-center gap-1 rounded px-2 py-1 text-xs text-neutral transition hover:bg-neutral/10 hover:text-text"
                          >
                            {copied === "service" ? (
                              <Check className="h-3.5 w-3.5" />
                            ) : (
                              <Copy className="h-3.5 w-3.5" />
                            )}
                            {copied === "service" ? "Copied" : "Copy"}
                          </button>
                        </div>
                        <pre className="overflow-auto px-sm py-xs text-xs text-text">
                          <code>{SERVICE_SNIPPET}</code>
                        </pre>
                      </div>

                      <p className="text-sm text-neutral">
                        Single service usage example (without anchors).
                      </p>

                      <div className="rounded-lg border border-neutral/20 bg-background/80">
                        <div className="flex items-center justify-between border-b border-neutral/20 px-sm py-xs">
                          <span className="text-xs font-medium text-text">
                            Single service example
                          </span>
                          <button
                            type="button"
                            onClick={() =>
                              copySnippet("single", SINGLE_SERVICE_SNIPPET)
                            }
                            className="inline-flex cursor-pointer items-center gap-1 rounded px-2 py-1 text-xs text-neutral transition hover:bg-neutral/10 hover:text-text"
                          >
                            {copied === "single" ? (
                              <Check className="h-3.5 w-3.5" />
                            ) : (
                              <Copy className="h-3.5 w-3.5" />
                            )}
                            {copied === "single" ? "Copied" : "Copy"}
                          </button>
                        </div>
                        <pre className="overflow-auto px-sm py-xs text-xs text-text">
                          <code>{SINGLE_SERVICE_SNIPPET}</code>
                        </pre>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>,
            document.body
          )
        : null}
    </>
  );
}
