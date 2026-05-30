import type { Route } from "../../../.react-router/types/app/routes/showcases/+types/number-field-showcase";
import { useState, type ReactNode } from "react";
import Checkbox from "../../components/library/forms/Checkbox";
import { NumberField } from "../../components/library/forms/fields/NumberField";
import type { FieldStatus, FieldTone, FieldVariant, FieldWidth } from "../../components/library/forms/fields/text-field.styles";
import type { StepperPosition } from "../../components/library/forms/fields/number-field.styles";
import type { InputVariant } from "../../components/library/forms/input.styles";
import type { PaddingFormat, RadiusFormat } from "../../components/library/components.styles";

export function meta({}: Route.MetaArgs) {
  return [{ title: "NumberField Showcase | Unicron" }];
}

const TONE_OPTIONS: FieldTone[] = ["default", "primary", "secondary", "success", "warning", "error", "neutral"];
const STATUS_OPTIONS: FieldStatus[] = ["default", "success", "warning", "error"];
const VARIANT_OPTIONS: FieldVariant[] = ["stacked", "inline", "floating", "nested_floating"];
const INPUT_VARIANT_OPTIONS: InputVariant[] = ["solid", "outline", "subtle", "ghost", "text", "underline"];
const WIDTH_OPTIONS: FieldWidth[] = ["content", "full"];
const RADIUS_OPTIONS: Radius[] = ["none", "sm", "md", "lg", "full"];
const PADDING_OPTIONS: Spacing[] = ["0", "4xs", "3xs", "2xs", "xs", "sm", "md", "lg"];
const FONT_SIZE_OPTIONS: FontSize[] = ["h5", "base", "sm", "xs", "2xs"];
const STEPPER_POSITIONS: StepperPosition[] = ["right-stacked", "right-inline", "left-stacked", "left-inline", "split"];
const OPTIONAL_PADDING_OPTIONS: (Spacing | 0)[] = [0, "4xs", "3xs", "2xs", "xs", "sm", "md", "lg"];
const controlInputClass =
  "w-full rounded-md border border-divider bg-background px-sm py-2xs text-sm text-text shadow-sm focus-visible:border-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500";

export default function NumberFieldShowcase() {
  const [value, setValue] = useState<number | null>(3);
  const [isDisabled, setIsDisabled] = useState(false);
  const [isReadOnly, setIsReadOnly] = useState(false);
  const [isRequired, setIsRequired] = useState(false);
  const [isInvalid, setIsInvalid] = useState(false);

  const [numberFieldProps, setNumberFieldProps] = useState({
    label: "Quantity",
    variant: "stacked" as FieldVariant,
    tone: "default" as FieldTone,
    status: "default" as FieldStatus,
    width: "content" as FieldWidth,
    padding: "sm" as PaddingFormat,
    gap: "3xs" as Spacing,
    labelGap: "3xs" as Spacing,
    messageGap: "4xs" as Spacing,
    textSize: "base" as FontSize,
    labelTextSize: "sm" as FontSize,
    messageTextSize: "xs" as FontSize,
    description: "Adjust quantity with steppers or type a value.",
    errorMessage: "Enter a value between 1 and 20.",
    className: "max-w-[420px]",
    doesStatusEffectLabel: false,
    doesStatusEffectInput: false,
    doesStatusEffectDescription: false,
    stepperPosition: "right-stacked" as StepperPosition,
    stepperStartPadding: "sm" as Spacing | 0,
    stepperEndPadding: "sm" as Spacing | 0,
  });

  const [inputProps, setInputProps] = useState({
    variant: "outline" as InputVariant,
    radius: "md" as RadiusFormat,
    padding: ["sm", "3xs"] as PaddingFormat,
    wrapperClassName: "",
    inputClassName: "",
  });

  const [fieldPadding, setFieldPadding] = useState({
    paddingTop: "sm",
    paddingRight: "sm",
    paddingBottom: "sm",
    paddingLeft: "sm",
  });
  const [inputPadding, setInputPadding] = useState({
    paddingTop: "3xs",
    paddingRight: "sm",
    paddingBottom: "3xs",
    paddingLeft: "sm",
  });

  const updateNumberFieldProp = (prop: keyof typeof numberFieldProps, next: any) => setNumberFieldProps((prev) => ({ ...prev, [prop]: next }));
  const updateInputProp = (prop: keyof typeof inputProps, next: any) => setInputProps((prev) => ({ ...prev, [prop]: next }));
  const parseOptionalSpacing = (raw: string): Spacing | 0 => (raw === "0" ? 0 : (raw as Spacing));

  const paddingObjectToPaddingFormat = (obj: { paddingTop: any; paddingRight: any; paddingBottom: any; paddingLeft: any }): PaddingFormat => {
    const top = String(obj.paddingTop);
    const right = String(obj.paddingRight);
    const bottom = String(obj.paddingBottom);
    const left = String(obj.paddingLeft);

    if (top === right && top === bottom && top === left) return top as PaddingFormat;
    if (top === bottom && right === left) return [right as any, top as any] as unknown as PaddingFormat;
    return [top as any, right as any, bottom as any, left as any] as unknown as PaddingFormat;
  };

  return (
    <div className="flex w-full flex-col items-center gap-lg pb-4xl">
      <header className="space-y-3 text-center">
        <h1 className="text-gradient bg-linear-to-r from-primary-500 to-secondary-500 bg-clip-text text-5xl font-bold text-transparent">NumberField Showcase</h1>
        <p className="text-base text-neutral-text">Try every layout, tone, and stepper placement for the NumberField wrapper.</p>
      </header>

      <section className="grid w-full justify-items-center rounded-lg border border-divider bg-foreground/20 p-md">
        <h2 className="mx-auto text-h4 font-semibold">Preview</h2>
        <NumberField
          {...{
            ...numberFieldProps,
            isInvalid,
            padding: paddingObjectToPaddingFormat(fieldPadding),
            inputProps: { ...inputProps, padding: paddingObjectToPaddingFormat(inputPadding) },
            value: value ?? undefined,
            onChange: setValue,
            isDisabled,
            isReadOnly,
            isRequired,
          }}
        />
        <dl className="grid w-full grid-cols-4 justify-items-center gap-2xs rounded-lg border border-divider/70 bg-alt-background p-sm text-sm text-neutral-text">
          <div className="flex flex-col">
            <dt className="text-xs font-semibold text-neutral uppercase">Variant</dt>
            <dd className="text-text">{humanize(numberFieldProps.variant)}</dd>
          </div>
          <div className="flex flex-col">
            <dt className="text-xs font-semibold text-neutral uppercase">Stepper</dt>
            <dd className="text-text">{humanize(numberFieldProps.stepperPosition)}</dd>
          </div>
          <div className="flex flex-col">
            <dt className="text-xs font-semibold text-neutral uppercase">Value</dt>
            <dd className="text-text">{value ?? <span className="text-neutral-text">Empty</span>}</dd>
          </div>
          <div className="flex flex-col">
            <dt className="text-xs font-semibold text-neutral uppercase">State</dt>
            <dd className="text-text">{isDisabled ? "Disabled" : isReadOnly ? "Read only" : isRequired ? "Required" : "Active"}</dd>
          </div>
        </dl>
      </section>

      <section className="grid w-full gap-md rounded-lg border border-divider bg-foreground/20 p-lg">
        <div className="space-y-2">
          <h2 className="text-h4 font-semibold text-text">Playground Controls</h2>
          <p className="text-sm text-neutral-text">Tweak layout, tones, padding, and stepper placement.</p>
        </div>

        <div className="grid w-full gap-md lg:grid-cols-3">
          <div className="space-y-sm rounded-lg border border-divider/70 bg-background/80 p-md">
            <div>
              <h3 className="text-base font-semibold text-text">Field props</h3>
              <p className="text-xs text-neutral-text">Layout, tone, spacing, and label copy.</p>
            </div>
            <div className="grid gap-sm">
              <div className="grid items-end gap-sm sm:grid-cols-2">
                <ControlGroup label="Variant">
                  <select className={controlInputClass} value={numberFieldProps.variant} onChange={(event) => updateNumberFieldProp("variant", event.target.value as FieldVariant)}>
                    {VARIANT_OPTIONS.map((option) => (
                      <option key={option} value={option}>
                        {humanize(option)}
                      </option>
                    ))}
                  </select>
                </ControlGroup>
                <ControlGroup label="Tone">
                  <select className={controlInputClass} value={numberFieldProps.tone} onChange={(event) => updateNumberFieldProp("tone", event.target.value as FieldTone)}>
                    {TONE_OPTIONS.map((option) => (
                      <option key={option} value={option}>
                        {humanize(option)}
                      </option>
                    ))}
                  </select>
                </ControlGroup>
              </div>

              <div className="grid items-end gap-sm sm:grid-cols-2">
                <ControlGroup label="Status">
                  <select className={controlInputClass} value={numberFieldProps.status} onChange={(event) => updateNumberFieldProp("status", event.target.value as FieldStatus)}>
                    {STATUS_OPTIONS.map((option) => (
                      <option key={option} value={option}>
                        {humanize(option)}
                      </option>
                    ))}
                  </select>
                </ControlGroup>
                <ControlGroup label="Width">
                  <select className={controlInputClass} value={numberFieldProps.width} onChange={(event) => updateNumberFieldProp("width", event.target.value as FieldWidth)}>
                    {WIDTH_OPTIONS.map((option) => (
                      <option key={option} value={option}>
                        {humanize(option)}
                      </option>
                    ))}
                  </select>
                </ControlGroup>
              </div>

              <div className="grid items-end gap-sm sm:grid-cols-2">
                <ControlGroup label="Gap">
                  <select className={controlInputClass} value={numberFieldProps.gap} onChange={(event) => updateNumberFieldProp("gap", event.target.value as Spacing)}>
                    {PADDING_OPTIONS.map((option) => (
                      <option key={option} value={option}>
                        {option}
                      </option>
                    ))}
                  </select>
                </ControlGroup>
                <ControlGroup label="Label gap">
                  <select className={controlInputClass} value={numberFieldProps.labelGap} onChange={(event) => updateNumberFieldProp("labelGap", event.target.value as Spacing)}>
                    {PADDING_OPTIONS.map((option) => (
                      <option key={option} value={option}>
                        {option}
                      </option>
                    ))}
                  </select>
                </ControlGroup>
              </div>

              <div className="grid items-end gap-sm sm:grid-cols-2">
                <ControlGroup label="Label text size">
                  <select
                    className={controlInputClass}
                    value={numberFieldProps.labelTextSize}
                    onChange={(event) => updateNumberFieldProp("labelTextSize", event.target.value as FontSize)}
                  >
                    {FONT_SIZE_OPTIONS.map((option) => (
                      <option key={option} value={option}>
                        {option.toUpperCase()}
                      </option>
                    ))}
                  </select>
                </ControlGroup>
                <ControlGroup label="Field text size">
                  <select className={controlInputClass} value={numberFieldProps.textSize} onChange={(event) => updateNumberFieldProp("textSize", event.target.value as FontSize)}>
                    {FONT_SIZE_OPTIONS.map((option) => (
                      <option key={option} value={option}>
                        {option.toUpperCase()}
                      </option>
                    ))}
                  </select>
                </ControlGroup>
              </div>

              <div className="grid items-end gap-sm sm:grid-cols-2">
                <ControlGroup label="Message text size">
                  <select
                    className={controlInputClass}
                    value={numberFieldProps.messageTextSize}
                    onChange={(event) => updateNumberFieldProp("messageTextSize", event.target.value as FontSize)}
                  >
                    {FONT_SIZE_OPTIONS.map((option) => (
                      <option key={option} value={option}>
                        {option.toUpperCase()}
                      </option>
                    ))}
                  </select>
                </ControlGroup>
                <ControlGroup label="Radius">
                  <select className={controlInputClass} value={inputProps.radius} onChange={(event) => updateInputProp("radius", event.target.value as Radius)}>
                    {RADIUS_OPTIONS.map((option) => (
                      <option key={option} value={option}>
                        {humanize(option)}
                      </option>
                    ))}
                  </select>
                </ControlGroup>
              </div>

              <div className="grid items-end gap-sm sm:grid-cols-2">
                <ControlGroup label="Field padding top">
                  <select
                    className={controlInputClass}
                    value={fieldPadding.paddingTop}
                    onChange={(event) => setFieldPadding((prev) => ({ ...prev, paddingTop: event.target.value }))}
                  >
                    {PADDING_OPTIONS.map((option) => (
                      <option key={option} value={option}>
                        {option}
                      </option>
                    ))}
                  </select>
                </ControlGroup>
                <ControlGroup label="Field padding right">
                  <select
                    className={controlInputClass}
                    value={fieldPadding.paddingRight}
                    onChange={(event) => setFieldPadding((prev) => ({ ...prev, paddingRight: event.target.value }))}
                  >
                    {PADDING_OPTIONS.map((option) => (
                      <option key={option} value={option}>
                        {option}
                      </option>
                    ))}
                  </select>
                </ControlGroup>
              </div>

              <div className="grid items-end gap-sm sm:grid-cols-2">
                <ControlGroup label="Field padding bottom">
                  <select
                    className={controlInputClass}
                    value={fieldPadding.paddingBottom}
                    onChange={(event) => setFieldPadding((prev) => ({ ...prev, paddingBottom: event.target.value }))}
                  >
                    {PADDING_OPTIONS.map((option) => (
                      <option key={option} value={option}>
                        {option}
                      </option>
                    ))}
                  </select>
                </ControlGroup>
                <ControlGroup label="Field padding left">
                  <select
                    className={controlInputClass}
                    value={fieldPadding.paddingLeft}
                    onChange={(event) => setFieldPadding((prev) => ({ ...prev, paddingLeft: event.target.value }))}
                  >
                    {PADDING_OPTIONS.map((option) => (
                      <option key={option} value={option}>
                        {option}
                      </option>
                    ))}
                  </select>
                </ControlGroup>
              </div>
            </div>
          </div>

          <div className="space-y-sm rounded-lg border border-divider/70 bg-background/80 p-md">
            <div>
              <h3 className="text-base font-semibold text-text">Steppers</h3>
              <p className="text-xs text-neutral-text">Choose where the stepper cluster sits and adjust padding.</p>
            </div>
            <div className="grid gap-sm">
              <ControlGroup label="Stepper position">
                <select
                  className={controlInputClass}
                  value={numberFieldProps.stepperPosition}
                  onChange={(event) => updateNumberFieldProp("stepperPosition", event.target.value as StepperPosition)}
                >
                  {STEPPER_POSITIONS.map((option) => (
                    <option key={option} value={option}>
                      {humanize(option)}
                    </option>
                  ))}
                </select>
              </ControlGroup>

              <div className="grid items-end gap-sm sm:grid-cols-2">
                <ControlGroup label="Stepper start padding">
                  <select
                    className={controlInputClass}
                    value={String(numberFieldProps.stepperStartPadding)}
                    onChange={(event) => updateNumberFieldProp("stepperStartPadding", parseOptionalSpacing(event.target.value))}
                  >
                    {OPTIONAL_PADDING_OPTIONS.map((option) => (
                      <option key={option} value={option === 0 ? "0" : option}>
                        {option === 0 ? "0" : option}
                      </option>
                    ))}
                  </select>
                </ControlGroup>
                <ControlGroup label="Stepper end padding">
                  <select
                    className={controlInputClass}
                    value={String(numberFieldProps.stepperEndPadding)}
                    onChange={(event) => updateNumberFieldProp("stepperEndPadding", parseOptionalSpacing(event.target.value))}
                  >
                    {OPTIONAL_PADDING_OPTIONS.map((option) => (
                      <option key={option} value={option === 0 ? "0" : option}>
                        {option === 0 ? "0" : option}
                      </option>
                    ))}
                  </select>
                </ControlGroup>
              </div>
            </div>
          </div>

          <div className="space-y-sm rounded-lg border border-divider/70 bg-background/80 p-md">
            <div>
              <h3 className="text-base font-semibold text-text">Input props</h3>
              <p className="text-xs text-neutral-text">Adjust input variant and padding.</p>
            </div>
            <div className="grid gap-sm">
              <ControlGroup label="Input variant">
                <select className={controlInputClass} value={inputProps.variant} onChange={(event) => updateInputProp("variant", event.target.value as InputVariant)}>
                  {INPUT_VARIANT_OPTIONS.map((option) => (
                    <option key={option} value={option}>
                      {humanize(option)}
                    </option>
                  ))}
                </select>
              </ControlGroup>

              <div className="grid items-end gap-sm sm:grid-cols-2">
                <ControlGroup label="Padding top">
                  <select
                    className={controlInputClass}
                    value={inputPadding.paddingTop}
                    onChange={(event) => setInputPadding((prev) => ({ ...prev, paddingTop: event.target.value }))}
                  >
                    {PADDING_OPTIONS.map((option) => (
                      <option key={option} value={option}>
                        {option}
                      </option>
                    ))}
                  </select>
                </ControlGroup>
                <ControlGroup label="Padding right">
                  <select
                    className={controlInputClass}
                    value={inputPadding.paddingRight}
                    onChange={(event) => setInputPadding((prev) => ({ ...prev, paddingRight: event.target.value }))}
                  >
                    {PADDING_OPTIONS.map((option) => (
                      <option key={option} value={option}>
                        {option}
                      </option>
                    ))}
                  </select>
                </ControlGroup>
              </div>

              <div className="grid items-end gap-sm sm:grid-cols-2">
                <ControlGroup label="Padding bottom">
                  <select
                    className={controlInputClass}
                    value={inputPadding.paddingBottom}
                    onChange={(event) => setInputPadding((prev) => ({ ...prev, paddingBottom: event.target.value }))}
                  >
                    {PADDING_OPTIONS.map((option) => (
                      <option key={option} value={option}>
                        {option}
                      </option>
                    ))}
                  </select>
                </ControlGroup>
                <ControlGroup label="Padding left">
                  <select
                    className={controlInputClass}
                    value={inputPadding.paddingLeft}
                    onChange={(event) => setInputPadding((prev) => ({ ...prev, paddingLeft: event.target.value }))}
                  >
                    {PADDING_OPTIONS.map((option) => (
                      <option key={option} value={option}>
                        {option}
                      </option>
                    ))}
                  </select>
                </ControlGroup>
              </div>

              <div className="grid gap-xs">
                <CheckboxControl label="Disabled" checked={isDisabled} onChange={setIsDisabled} />
                <CheckboxControl label="Read only" checked={isReadOnly} onChange={setIsReadOnly} />
                <CheckboxControl label="Required" checked={isRequired} onChange={setIsRequired} />
                <CheckboxControl label="Invalid" checked={isInvalid} onChange={setIsInvalid} />
                <CheckboxControl
                  label="Status affects input"
                  checked={numberFieldProps.doesStatusEffectInput}
                  onChange={(checked) => updateNumberFieldProp("doesStatusEffectInput", checked)}
                />
              </div>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}

function ControlGroup({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="space-y-1 text-sm text-text">
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
  return value
    .replace(/_/g, " ")
    .replace(/-/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}
