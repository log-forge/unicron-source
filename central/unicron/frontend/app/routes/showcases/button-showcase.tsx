import type { Route } from "../../../.react-router/types/app/routes/showcases/+types/button-showcase";
import { useMemo, useState, type ReactNode } from "react";
import clsx from "clsx";
import { Button } from "../../components/library/buttons/Button";
import type { ButtonTone, ButtonVariant, ButtonWidth } from "../../components/library/buttons/button.styles";
import Checkbox from "../../components/library/forms/Checkbox";
import type { PaddingFormat } from "../../components/library/components.styles";

export function meta({}: Route.MetaArgs) {
  return [{ title: "Button Showcase | Unicron" }];
}

const TONE_OPTIONS: ButtonTone[] = ["default", "primary", "secondary", "success", "warning", "error", "neutral"];
const VARIANT_OPTIONS: ButtonVariant[] = ["solid", "pill", "ripple", "cartoon", "outline", "ghost", "subtle", "text", "glass"];
const WIDTH_OPTIONS: ButtonWidth[] = ["content", "full", "grow", "icon"];
const RADIUS_OPTIONS: Radius[] = ["none", "sm", "md", "lg", "full"];
const PADDING_OPTIONS: Spacing[] = ["0", "4xs", "3xs", "2xs", "xs", "sm", "md", "lg"];

const inputClass =
  "w-full rounded-md border border-divider bg-background px-sm py-2xs text-sm text-text shadow-sm focus-visible:border-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500";

type PlaygroundMode = "button" | "toggle";

export default function ButtonShowcase() {
  const [label, setLabel] = useState("Primary action");
  const [customClassName, setCustomClassName] = useState("");
  const [mode, setMode] = useState<PlaygroundMode>("button");
  const [variant, setVariant] = useState<ButtonVariant>("solid");
  const [tone, setTone] = useState<ButtonTone>("primary");
  const [width, setWidth] = useState<ButtonWidth>("content");
  const [radius, setRadius] = useState<Radius>("md");
  const [paddingTop, setPaddingTop] = useState<Spacing>("xs");
  const [paddingRight, setPaddingRight] = useState<Spacing>("xs");
  const [paddingBottom, setPaddingBottom] = useState<Spacing>("xs");
  const [paddingLeft, setPaddingLeft] = useState<Spacing>("xs");
  const [iconOnly, setIconOnly] = useState(false);
  const [startIcon, setStartIcon] = useState(false);
  const [endIcon, setEndIcon] = useState(false);
  const [isDisabled, setIsDisabled] = useState(false);
  const [isPending, setIsPending] = useState(false);
  const [pressCount, setPressCount] = useState(0);
  const [statusText, setStatusText] = useState("Try pressing the button to see feedback here.");
  const [isToggleSelected, setIsToggleSelected] = useState(false);
  const [toneToggleState, setToneToggleState] = useState<Record<ButtonTone, boolean>>(
    () => Object.fromEntries(TONE_OPTIONS.map((toneOption) => [toneOption, toneOption === "primary"])) as Record<ButtonTone, boolean>,
  );

  const handlePress = () => {
    setPressCount((count) => count + 1);
    const timestamp = new Date().toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    setStatusText(`Pressed at ${timestamp}`);
  };

  const handleToggleChange = (selected: boolean) => {
    setIsToggleSelected(selected);
    setStatusText(selected ? "Toggle is selected" : "Toggle is not selected");
  };

  const previewLabel = label.trim().length === 0 ? "Playground button" : label;

  const previewContent = (
    <span className="inline-flex items-center justify-center gap-2xs">
      {(startIcon || iconOnly) && <DemoIcon className="h-4 w-4 text-current" />}
      {!iconOnly && <span className="font-medium">{previewLabel}</span>}
      {!iconOnly && endIcon && <DemoIcon className="h-4 w-4 rotate-180 text-current" />}
    </span>
  );

  const previewRowClass = clsx("w-full", width === "grow" ? "flex items-center gap-2xs" : "flex justify-center");
  const previewSurfaceClass = clsx(
    "rounded-lg border border-dashed border-divider/60 bg-alt-background/60 p-lg",
    variant === "glass" && "bg-gradient-to-br from-primary-950 via-background to-secondary-900",
  );
  const resolvedPadding: PaddingFormat = resolvePaddingFormat(paddingTop, paddingRight, paddingBottom, paddingLeft);

  const buttonModeProps = mode === "toggle" ? { mode: "toggle" as const, isSelected: isToggleSelected, onChange: handleToggleChange } : { mode: "button" as const };

  const variantGroups = useMemo(
    () => [
      {
        title: "Filled",
        variants: ["solid", "pill", "ripple", "cartoon"] as ButtonVariant[],
      },
      {
        title: "Minimal",
        variants: ["outline", "ghost", "subtle", "text", "glass"] as ButtonVariant[],
      },
    ],
    [],
  );

  const showIconToggles = !iconOnly;

  return (
    <div className="flex w-full flex-col gap-lg pb-4xl">
      <header className="space-y-3 text-center">
        <h1 className="text-gradient bg-gradient-to-r from-primary-500 to-secondary-500 bg-clip-text text-5xl font-bold text-transparent">Button Showcase</h1>
        <p className="text-base text-neutral-text">Inspect every tone, variant, and toggle state for the shared Button component and experiment in the playground.</p>
      </header>

      <section className="grid gap-md rounded-lg border border-divider bg-alt-background/40 p-lg lg:grid-cols-[minmax(0,0.75fr)_minmax(0,1fr)]">
        <div className="space-y-md">
          <h2 className="text-h4 font-semibold text-text">Playground Controls</h2>
          <div className="grid gap-sm">
            <ControlGroup label="Mode">
              <div className="grid grid-cols-2 gap-2xs">
                {(["button", "toggle"] satisfies PlaygroundMode[]).map((option) => (
                  <button
                    key={option}
                    type="button"
                    className={clsx(
                      "rounded-md border px-sm py-2xs text-sm font-medium capitalize shadow-sm transition",
                      option === mode ? "border-primary bg-primary text-background" : "border-divider bg-background text-text hover:border-primary/60",
                    )}
                    onClick={() => setMode(option)}
                  >
                    {option}
                  </button>
                ))}
              </div>
            </ControlGroup>

            <ControlGroup label="Variant">
              <select className={inputClass} value={variant} onChange={(event) => setVariant(event.target.value as ButtonVariant)}>
                {VARIANT_OPTIONS.map((option) => (
                  <option key={option} value={option}>
                    {humanize(option)}
                  </option>
                ))}
              </select>
            </ControlGroup>

            <ControlGroup label="Tone">
              <select className={inputClass} value={tone} onChange={(event) => setTone(event.target.value as ButtonTone)}>
                {TONE_OPTIONS.map((option) => (
                  <option key={option} value={option}>
                    {humanize(option)}
                  </option>
                ))}
              </select>
            </ControlGroup>

            <div className="grid gap-sm sm:grid-cols-2">
              <ControlGroup label="Width">
                <select className={inputClass} value={width} onChange={(event) => setWidth(event.target.value as ButtonWidth)} disabled={iconOnly}>
                  {WIDTH_OPTIONS.map((option) => (
                    <option key={option} value={option}>
                      {humanize(option)}
                    </option>
                  ))}
                </select>
              </ControlGroup>
              <ControlGroup label="Radius">
                <select className={inputClass} value={radius} onChange={(event) => setRadius(event.target.value as Radius)}>
                  {RADIUS_OPTIONS.map((option) => (
                    <option key={option} value={option}>
                      {humanize(option)}
                    </option>
                  ))}
                </select>
              </ControlGroup>
            </div>

            <div className="grid gap-sm sm:grid-cols-2">
              <ControlGroup label="Padding top">
                <select className={inputClass} value={paddingTop} onChange={(event) => setPaddingTop(event.target.value as Spacing)}>
                  {PADDING_OPTIONS.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </select>
              </ControlGroup>
              <ControlGroup label="Padding right">
                <select className={inputClass} value={paddingRight} onChange={(event) => setPaddingRight(event.target.value as Spacing)}>
                  {PADDING_OPTIONS.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </select>
              </ControlGroup>
            </div>

            <div className="grid gap-sm sm:grid-cols-2">
              <ControlGroup label="Padding bottom">
                <select className={inputClass} value={paddingBottom} onChange={(event) => setPaddingBottom(event.target.value as Spacing)}>
                  {PADDING_OPTIONS.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </select>
              </ControlGroup>
              <ControlGroup label="Padding left">
                <select className={inputClass} value={paddingLeft} onChange={(event) => setPaddingLeft(event.target.value as Spacing)}>
                  {PADDING_OPTIONS.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </select>
              </ControlGroup>
            </div>

            <div className="grid gap-sm sm:grid-cols-2">
              <ControlGroup label="Label">
                <input className={inputClass} type="text" value={label} onChange={(event) => setLabel(event.target.value)} placeholder="Primary action" disabled={iconOnly} />
              </ControlGroup>
              <ControlGroup label="Custom className">
                <input
                  className={inputClass}
                  type="text"
                  value={customClassName}
                  onChange={(event) => setCustomClassName(event.target.value)}
                  placeholder='e.g. "ring-2 ring-primary-500"'
                />
              </ControlGroup>
            </div>

            <div className="grid gap-sm sm:grid-cols-2">
              <CheckboxControl label="Icon only" checked={iconOnly} onChange={(checked) => setIconOnly(checked)} />
              <CheckboxControl label="Disabled" checked={isDisabled} onChange={(checked) => setIsDisabled(checked)} />
            </div>

            <div className="grid gap-sm sm:grid-cols-2">
              <CheckboxControl label="Loading (isPending)" checked={isPending} onChange={(checked) => setIsPending(checked)} />
            </div>

            {showIconToggles && (
              <div className="grid gap-sm sm:grid-cols-2">
                <CheckboxControl label="Leading icon" checked={startIcon} onChange={(checked) => setStartIcon(checked)} />
                <CheckboxControl label="Trailing icon" checked={endIcon} onChange={(checked) => setEndIcon(checked)} />
              </div>
            )}
          </div>
        </div>

        <div className="flex flex-col gap-sm rounded-lg border border-divider bg-background/60 p-lg">
          <h2 className="text-h4 font-semibold">Preview</h2>
          <div className="space-y-sm">
            <div className={previewSurfaceClass}>
              <div className={previewRowClass}>
                <Button
                  variant={variant}
                  tone={tone}
                  width={iconOnly ? "icon" : width}
                  radius={radius}
                  padding={resolvedPadding}
                  iconOnly={iconOnly}
                  className={customClassName || undefined}
                  {...buttonModeProps}
                  onPress={handlePress}
                  isDisabled={isDisabled}
                  aria-label={iconOnly ? previewLabel : undefined}
                >
                  {previewContent}
                </Button>
              </div>
            </div>
            <dl className="grid gap-2xs rounded-lg border border-divider/70 bg-alt-background/50 p-sm text-sm text-neutral-text sm:grid-cols-2">
              <div className="flex flex-col">
                <dt className="text-xs font-semibold text-neutral uppercase">Pressed</dt>
                <dd>{pressCount} times</dd>
              </div>
              <div className="flex flex-col">
                <dt className="text-xs font-semibold text-neutral uppercase">Toggle state</dt>
                <dd>{mode === "toggle" ? (isToggleSelected ? "Selected" : "Not selected") : "N/A"}</dd>
              </div>
              <div className="sm:col-span-2">
                <dt className="text-xs font-semibold text-neutral uppercase">Status</dt>
                <dd className="text-text">{statusText}</dd>
              </div>
            </dl>
          </div>
        </div>
      </section>

      <section className="space-y-md">
        <div>
          <h2 className="text-h4 font-semibold text-text">Variants by Tone</h2>
          <p className="text-sm text-neutral-text">Every tone rendered for each variant to quickly compare surface treatments.</p>
        </div>
        <div className="grid gap-md">
          {variantGroups.map((group) => (
            <div key={group.title} className="space-y-sm rounded-lg border border-divider bg-background/40 p-md">
              <div className="text-xs font-semibold tracking-[0.2em] text-neutral uppercase">{group.title}</div>
              <div className="grid gap-sm md:grid-cols-2">
                {group.variants.map((variantName) => {
                  const isGlassVariant = variantName === "glass";
                  return (
                    <div
                      key={variantName}
                      className={clsx("space-y-2 rounded-md border border-divider/70 p-sm", isGlassVariant && "bg-gradient-to-br from-primary-950 via-background to-secondary-900")}
                    >
                      <div className="font-mono text-xs text-neutral-text uppercase">{variantName}</div>
                      <div className="flex flex-wrap gap-2xs">
                        {TONE_OPTIONS.map((toneOption) => (
                          <Button key={`${variantName}-${toneOption}`} variant={variantName} tone={toneOption} padding="2xs">
                            {humanize(toneOption)}
                          </Button>
                        ))}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="space-y-md">
        <div>
          <h2 className="text-h4 font-semibold text-text">Toggle interactions</h2>
          <p className="text-sm text-neutral-text">Every tone can act as a toggle — tap to flip the state.</p>
        </div>
        <div className="rounded-lg border border-divider bg-alt-background/50 p-md">
          <div className="grid gap-sm sm:grid-cols-2 lg:grid-cols-3">
            {TONE_OPTIONS.map((toneOption) => (
              <Button
                key={`toggle-${toneOption}`}
                mode="toggle"
                variant="outline"
                tone={toneOption}
                width="full"
                isSelected={toneToggleState[toneOption]}
                onChange={(selected) => setToneToggleState((prev) => ({ ...prev, [toneOption]: selected }))}
                className="text-sm"
              >
                <span className="flex w-full items-center justify-between">
                  <span>{humanize(toneOption)}</span>
                  <span className="text-xs text-neutral-text">{toneToggleState[toneOption] ? "Selected" : "Idle"}</span>
                </span>
              </Button>
            ))}
          </div>
        </div>
      </section>
    </div>
  );
}

function ControlGroup({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="space-y-2xs text-sm text-text">
      <span className="text-xs font-semibold tracking-wide text-neutral uppercase">{label}</span>
      {children}
    </label>
  );
}

function CheckboxControl({ label, checked, onChange }: { label: string; checked: boolean; onChange: (checked: boolean) => void }) {
  return (
    <Checkbox width="full" isSelected={checked} onChange={onChange}>
      {label}
    </Checkbox>
  );
}

function humanize(value: string) {
  return value.charAt(0).toUpperCase() + value.slice(1).replace(/-/g, " ");
}

function DemoIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" className={className}>
      <path d="M12 3v4" />
      <path d="M12 17v4" />
      <path d="M5 12h4" />
      <path d="M15 12h4" />
      <path d="m7 7 2.5 2.5" />
      <path d="M14.5 14.5 17 17" />
      <path d="m17 7-2.5 2.5" />
      <path d="M9.5 14.5 7 17" />
    </svg>
  );
}

function resolvePaddingFormat(top: Spacing, right: Spacing, bottom: Spacing, left: Spacing): PaddingFormat {
  if (top === right && top === bottom && top === left) return top;
  return [top, right, bottom, left];
}
