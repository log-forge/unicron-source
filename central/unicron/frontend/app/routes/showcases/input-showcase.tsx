import type { Route } from "../../../.react-router/types/app/routes/showcases/+types/input-showcase";
import { useMemo, useState, type ChangeEvent, type HTMLInputTypeAttribute, type ReactNode } from "react";
import clsx from "clsx";
import Checkbox from "../../components/library/forms/Checkbox";
import { Input, InputClear } from "../../components/library/forms/Input";
import type { InputTone, InputVariant, InputWidth } from "../../components/library/forms/input.styles";
import type { PaddingFormat } from "../../components/library/components.styles";

export function meta({}: Route.MetaArgs) {
  return [{ title: "Input Showcase | Unicron" }];
}

const TONE_OPTIONS: InputTone[] = ["default", "primary", "secondary", "success", "warning", "error", "neutral"];
const VARIANT_OPTIONS: InputVariant[] = ["solid", "outline", "subtle", "ghost", "text", "underline"];
const WIDTH_OPTIONS: InputWidth[] = ["content", "full"];
const RADIUS_OPTIONS: Radius[] = ["none", "sm", "md", "lg", "full"];
const PADDING_OPTIONS: Spacing[] = ["0", "4xs", "3xs", "2xs", "xs", "sm", "md", "lg"];
const TEXT_SIZE_OPTIONS: FontSize[] = ["h5", "base", "sm", "xs", "2xs"];
const INPUT_TYPE_OPTIONS: HTMLInputTypeAttribute[] = ["text", "email", "password", "search", "url", "number"];

const controlInputClass =
  "w-full rounded-md border border-divider bg-background px-sm py-2xs text-sm text-text shadow-sm focus-visible:border-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500";

export default function InputShowcase() {
  const [value, setValue] = useState("unicron.dev");
  const [placeholder, setPlaceholder] = useState("Enter a value");
  const [wrapperClassName, setWrapperClassName] = useState("");
  const [inputClassName, setInputClassName] = useState("");
  const [variant, setVariant] = useState<InputVariant>("outline");
  const [tone, setTone] = useState<InputTone>("default");
  const [width, setWidth] = useState<InputWidth>("full");
  const [radius, setRadius] = useState<Radius>("md");
  const [paddingTop, setPaddingTop] = useState<Spacing>("xs");
  const [paddingRight, setPaddingRight] = useState<Spacing>("xs");
  const [paddingBottom, setPaddingBottom] = useState<Spacing>("xs");
  const [paddingLeft, setPaddingLeft] = useState<Spacing>("xs");
  const [textSize, setTextSize] = useState<FontSize>("base");
  const [startPadding, setStartPadding] = useState<Spacing | 0>(0);
  const [endPadding, setEndPadding] = useState<Spacing | 0>(0);
  const [inputType, setInputType] = useState<HTMLInputTypeAttribute>("text");
  const [isDisabled, setIsDisabled] = useState(false);
  const [isReadOnly, setIsReadOnly] = useState(false);
  const [isRequired, setIsRequired] = useState(false);
  const [statusText, setStatusText] = useState("Start typing in the preview to see value stats.");
  const [showStartAdornment, setShowStartAdornment] = useState(false);
  const [showEndAdornment, setShowEndAdornment] = useState(false);
  const [showClearOverlay, setShowClearOverlay] = useState(false);

  const handleChange = (event: ChangeEvent<HTMLInputElement>) => {
    const nextValue = event.target.value;
    setValue(nextValue);
    setStatusText(`Length: ${nextValue.length} ${nextValue.length === 1 ? "character" : "characters"}`);
  };

  const previewPlaceholder = placeholder.trim().length === 0 ? undefined : placeholder;
  const startAdornment = showStartAdornment ? <DemoIcon className="h-(--text-base) w-(--text-base)" /> : undefined;
  const endAdornment = showEndAdornment ? <span className="text-base font-semibold text-current uppercase">ID</span> : undefined;
  const clearOverlay = showClearOverlay ? (
    <InputClear
      buttonProps={{ tone: "secondary", padding: "4xs" }}
      onClear={() => {
        setValue("");
        setStatusText("Cleared via overlay button");
      }}
      textSize={textSize}
    />
  ) : undefined;

  const variantGroups = useMemo(
    () => [
      { title: "Framed", variants: ["solid", "outline", "subtle"] as InputVariant[] },
      { title: "Minimal", variants: ["ghost", "text", "underline"] as InputVariant[] },
    ],
    [],
  );

  return (
    <div className="flex w-full flex-col gap-lg pb-4xl">
      <header className="space-y-3 text-center">
        <h1 className="text-gradient bg-gradient-to-r from-primary-500 to-secondary-500 bg-clip-text text-5xl font-bold text-transparent">Input Showcase</h1>
        <p className="text-base text-neutral-text">Experiment with every Input recipe, tweak spacings, and observe the live value feedback below.</p>
      </header>

      <section className="grid gap-md rounded-lg border border-divider bg-alt-background/40 p-lg lg:grid-cols-[minmax(0,0.75fr)_minmax(0,1fr)]">
        <div className="space-y-md">
          <h2 className="text-h4 font-semibold text-text">Playground Controls</h2>
          <div className="grid gap-sm">
            <ControlGroup label="Variant">
              <select className={controlInputClass} value={variant} onChange={(event) => setVariant(event.target.value as InputVariant)}>
                {VARIANT_OPTIONS.map((option) => (
                  <option key={option} value={option}>
                    {humanize(option)}
                  </option>
                ))}
              </select>
            </ControlGroup>

            <ControlGroup label="Tone">
              <select className={controlInputClass} value={tone} onChange={(event) => setTone(event.target.value as InputTone)}>
                {TONE_OPTIONS.map((option) => (
                  <option key={option} value={option}>
                    {humanize(option)}
                  </option>
                ))}
              </select>
            </ControlGroup>

            <div className="grid gap-sm sm:grid-cols-2">
              <ControlGroup label="Width">
                <select className={controlInputClass} value={width} onChange={(event) => setWidth(event.target.value as InputWidth)}>
                  {WIDTH_OPTIONS.map((option) => (
                    <option key={option} value={option}>
                      {humanize(option)}
                    </option>
                  ))}
                </select>
              </ControlGroup>
              <ControlGroup label="Input type">
                <select className={controlInputClass} value={inputType} onChange={(event) => setInputType(event.target.value as HTMLInputTypeAttribute)}>
                  {INPUT_TYPE_OPTIONS.map((option) => (
                    <option key={option} value={option}>
                      {humanize(option)}
                    </option>
                  ))}
                </select>
              </ControlGroup>
            </div>

            <div className="grid gap-sm sm:grid-cols-2">
              <ControlGroup label="Radius">
                <select className={controlInputClass} value={radius} onChange={(event) => setRadius(event.target.value as Radius)}>
                  {RADIUS_OPTIONS.map((option) => (
                    <option key={option} value={option}>
                      {humanize(option)}
                    </option>
                  ))}
                </select>
              </ControlGroup>
              <ControlGroup label="Padding top">
                <select className={controlInputClass} value={paddingTop} onChange={(event) => setPaddingTop(event.target.value as Spacing)}>
                  {PADDING_OPTIONS.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </select>
              </ControlGroup>
            </div>

            <div className="grid gap-sm sm:grid-cols-2">
              <ControlGroup label="Padding right">
                <select className={controlInputClass} value={paddingRight} onChange={(event) => setPaddingRight(event.target.value as Spacing)}>
                  {PADDING_OPTIONS.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </select>
              </ControlGroup>
              <ControlGroup label="Padding bottom">
                <select className={controlInputClass} value={paddingBottom} onChange={(event) => setPaddingBottom(event.target.value as Spacing)}>
                  {PADDING_OPTIONS.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </select>
              </ControlGroup>
            </div>

            <div className="grid gap-sm sm:grid-cols-2">
              <ControlGroup label="Padding left">
                <select className={controlInputClass} value={paddingLeft} onChange={(event) => setPaddingLeft(event.target.value as Spacing)}>
                  {PADDING_OPTIONS.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </select>
              </ControlGroup>
              <ControlGroup label="Text size">
                <select className={controlInputClass} value={textSize} onChange={(event) => setTextSize(event.target.value as FontSize)}>
                  {TEXT_SIZE_OPTIONS.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </select>
              </ControlGroup>
            </div>

            <div className="grid gap-sm sm:grid-cols-2">
              <ControlGroup label="Start padding">
                <select
                  className={controlInputClass}
                  value={startPadding === 0 ? "0" : (startPadding as string)}
                  onChange={(event) => setStartPadding(event.target.value === "0" ? 0 : (event.target.value as Spacing))}
                >
                  {PADDING_OPTIONS.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </select>
              </ControlGroup>
              <ControlGroup label="End padding">
                <select
                  className={controlInputClass}
                  value={endPadding === 0 ? "0" : (endPadding as string)}
                  onChange={(event) => setEndPadding(event.target.value === "0" ? 0 : (event.target.value as Spacing))}
                >
                  {PADDING_OPTIONS.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </select>
              </ControlGroup>
            </div>

            <ControlGroup label="Placeholder">
              <input className={controlInputClass} type="text" value={placeholder} onChange={(event) => setPlaceholder(event.target.value)} placeholder="Placeholder text" />
            </ControlGroup>

            <div className="grid gap-sm sm:grid-cols-2">
              <ControlGroup label="Wrapper className">
                <input
                  className={controlInputClass}
                  type="text"
                  value={wrapperClassName}
                  onChange={(event) => setWrapperClassName(event.target.value)}
                  placeholder='e.g. "ring-2 ring-primary-500"'
                />
              </ControlGroup>
              <ControlGroup label="Input className">
                <input
                  className={controlInputClass}
                  type="text"
                  value={inputClassName}
                  onChange={(event) => setInputClassName(event.target.value)}
                  placeholder='e.g. "text-sm tracking-wide"'
                />
              </ControlGroup>
            </div>

            <div className="flex flex-row flex-wrap items-center justify-start gap-sm">
              <CheckboxControl label="Disabled" checked={isDisabled} onChange={setIsDisabled} />
              <CheckboxControl label="Read only" checked={isReadOnly} onChange={setIsReadOnly} />
              <CheckboxControl label="Required" checked={isRequired} onChange={setIsRequired} />
            </div>

            <div className="flex flex-row flex-wrap items-center justify-start gap-sm">
              <CheckboxControl label="Start adornment" checked={showStartAdornment} onChange={setShowStartAdornment} />
              <CheckboxControl label="End adornment" checked={showEndAdornment} onChange={setShowEndAdornment} />
              <CheckboxControl label="Clear button" checked={showClearOverlay} onChange={setShowClearOverlay} />
            </div>
          </div>
        </div>

        <div className="flex flex-col gap-sm rounded-lg border border-divider bg-background/60 p-lg">
          <h2 className="text-h4 font-semibold">Preview</h2>
          <div className={clsx("space-y-2", width === "content" ? "mx-auto w-full max-w-md" : "w-full")}>
            <label className="flex flex-col gap-2xs text-sm text-text">
              <Input
                variant={variant}
                tone={tone}
                width={width}
                radius={radius}
                padding={resolvePaddingFormat(paddingTop, paddingRight, paddingBottom, paddingLeft)}
                textSize={textSize}
                wrapperClassName={wrapperClassName || undefined}
                inputClassName={inputClassName || undefined}
                startContent={startAdornment}
                startPadding={startPadding}
                endContent={endAdornment}
                endPadding={endPadding}
                overlayContent={clearOverlay}
                type={inputType}
                value={value}
                onChange={handleChange}
                placeholder={previewPlaceholder}
                disabled={isDisabled}
                readOnly={isReadOnly}
                required={isRequired}
              />
            </label>
          </div>

          <dl className="grid gap-2xs rounded-lg border border-divider/70 bg-alt-background/50 p-sm text-sm text-neutral-text sm:grid-cols-3">
            <div className="flex flex-col">
              <dt className="text-xs font-semibold text-neutral uppercase">Type</dt>
              <dd className="text-text">{inputType}</dd>
            </div>
            <div className="flex flex-col">
              <dt className="text-xs font-semibold text-neutral uppercase">Value</dt>
              <dd className="truncate text-text">{value.length > 0 ? value : <span className="text-neutral-text">Empty</span>}</dd>
            </div>
            <div className="flex flex-col">
              <dt className="text-xs font-semibold text-neutral uppercase">State</dt>
              <dd className="text-text">{isDisabled ? "Disabled" : isReadOnly ? "Read only" : isRequired ? "Required" : "Active"}</dd>
            </div>
            <div className="sm:col-span-3">
              <dt className="text-xs font-semibold text-neutral uppercase">Status</dt>
              <dd className="text-text">{statusText}</dd>
            </div>
          </dl>
        </div>
      </section>

      <section className="space-y-md">
        <div>
          <h2 className="text-h4 font-semibold text-text">Variants by tone</h2>
          <p className="text-sm text-neutral-text">See each tone applied across the variants to understand the visual recipes.</p>
        </div>
        <div className="grid gap-md">
          {variantGroups.map((group) => (
            <div key={group.title} className="space-y-sm rounded-lg border border-divider bg-background/40 p-md">
              <div className="text-xs font-semibold tracking-[0.2em] text-neutral uppercase">{group.title}</div>
              <div className="grid gap-sm md:grid-cols-2">
                {group.variants.map((variantName) => (
                  <div key={variantName} className="space-y-2 rounded-md border border-divider/70 p-sm">
                    <div className="font-mono text-xs text-neutral-text uppercase">{variantName}</div>
                    <div className="space-y-2">
                      {TONE_OPTIONS.map((toneOption) => (
                        <div key={`${variantName}-${toneOption}`} className="space-y-1">
                          <p className="text-2xs font-semibold tracking-wide text-neutral uppercase">{humanize(toneOption)}</p>
                          <Input variant={variantName} tone={toneOption} padding="2xs" placeholder={humanize(toneOption)} />
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
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
    <Checkbox size="sm" variant="outline" width="full" labelPlacement="right" isSelected={checked} onChange={onChange}>
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
      <path d="M12 4v4" />
      <path d="M12 16v4" />
      <path d="M4 12h4" />
      <path d="M16 12h4" />
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
