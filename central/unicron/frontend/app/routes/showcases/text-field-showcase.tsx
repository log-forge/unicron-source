import type { Route } from "../../../.react-router/types/app/routes/showcases/+types/text-field-showcase";
import { useState, type ReactNode } from "react";
import Checkbox from "../../components/library/forms/Checkbox";
import { TextField } from "../../components/library/forms/fields/TextField";
import type { FieldWidth, FieldStatus, FieldTone, FieldVariant } from "../../components/library/forms/fields/text-field.styles";
import type { InputVariant, InputWidth } from "../../components/library/forms/input.styles";
import { User } from "lucide-react";
import type { PaddingFormat, RadiusFormat } from "../../components/library/components.styles";

export function meta({}: Route.MetaArgs) {
  return [{ title: "TextField Showcase | Unicron" }];
}

const TONE_OPTIONS: FieldTone[] = ["default", "primary", "secondary", "success", "warning", "error", "neutral"];
const STATUS_OPTIONS: FieldStatus[] = ["default", "success", "warning", "error"];
const FIELD_VARIANT_OPTIONS: FieldVariant[] = ["stacked", "inline", "floating", "nested_floating"];
const INPUT_VARIANT_OPTIONS: InputVariant[] = ["solid", "outline", "subtle", "ghost", "text", "underline"];
const WIDTH_OPTIONS: FieldWidth[] = ["content", "full"];
const RADIUS_OPTIONS: Radius[] = ["none", "sm", "md", "lg", "full"];
const PADDING_OPTIONS: Spacing[] = ["0", "4xs", "3xs", "2xs", "xs", "sm", "md", "lg"];
const FONT_SIZE_OPTIONS: FontSize[] = ["h1", "h2", "h3", "h4", "h5", "base", "sm", "xs", "2xs"];
const INPUT_WIDTH_OPTIONS: InputWidth[] = ["content", "full"];
const OPTIONAL_PADDING_OPTIONS: (Spacing | 0)[] = [0, "4xs", "3xs", "2xs", "xs", "sm", "md", "lg"];
const controlInputClass =
  "w-full rounded-md border border-divider bg-background px-sm py-2xs text-sm text-text shadow-sm focus-visible:border-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500";

export default function TextFieldShowcase() {
  const [value, setValue] = useState("");
  const [isDisabled, setIsDisabled] = useState(false);
  const [isReadOnly, setIsReadOnly] = useState(false);
  const [isRequired, setIsRequired] = useState(false);
  const [isInvalid, setIsInvalid] = useState(false);
  const [textFieldProps, setTextFieldProps] = useState({
    label: "Full name",
    variant: "stacked" as FieldVariant,
    tone: "default" as FieldTone,
    status: "default" as FieldStatus,
    width: "full" as FieldWidth,
    padding: "sm" as PaddingFormat,
    gap: "4xs" as Spacing,
    textSize: "base" as FontSize,
    labelTextSize: "h5" as FontSize,
    messageTextSize: "xs" as FontSize,
    description: "This appears anywhere your profile is referenced.",
    errorMessage: "Enter at least three characters.",
    className: "max-w-[480px]",
    labelClassName: "mb-2xs",
    descriptionClassName: "",
    errorMessageClassName: "",
    doesStatusEffectLabel: false,
    doesStatusEffectInput: false,
    doesStatusEffectDescription: false,
  });
  const [inputProps, setInputProps] = useState({
    variant: "solid" as InputVariant,
    width: "full" as InputWidth,
    radius: "md" as RadiusFormat,
    padding: ["xs", "4xs"] as PaddingFormat,
    wrapperClassName: "",
    inputClassName: "",
    startPadding: 0 as Spacing | 0,
    endPadding: 0 as Spacing | 0,
    placeholder: "Enter your full name",
  });
  const [textFieldPadding, setTextFieldPadding] = useState({
    paddingTop: "sm",
    paddingRight: "sm",
    paddingBottom: "sm",
    paddingLeft: "sm",
  });
  const [inputPadding, setInputPadding] = useState({
    paddingTop: "4xs",
    paddingRight: "xs",
    paddingBottom: "4xs",
    paddingLeft: "xs",
  });
  const [showStartAdornment, setShowStartAdornment] = useState<boolean>(false);
  const [showEndAdornment, setShowEndAdornment] = useState<boolean>(false);

  const startAdornment = showStartAdornment ? <User className="h-(--text-base) w-(--text-base)" /> : undefined;
  const endAdornment = showEndAdornment ? <span className="flex h-full items-center text-2xs font-semibold text-current uppercase">ID</span> : undefined;

  const updateTextFieldProp = (prop: keyof typeof textFieldProps, value: any) => {
    setTextFieldProps((prev) => ({ ...prev, [prop]: value }));
  };

  const updateInputProp = (prop: keyof typeof inputProps, value: any) => {
    setInputProps((prev) => ({ ...prev, [prop]: value }));
  };

  const paddingObjectToPaddingFormat = (obj: { paddingTop: any; paddingRight: any; paddingBottom: any; paddingLeft: any }): PaddingFormat => {
    const top = String(obj.paddingTop);
    const right = String(obj.paddingRight);
    const bottom = String(obj.paddingBottom);
    const left = String(obj.paddingLeft);

    // All sides equal -> single-value shorthand
    if (top === right && top === bottom && top === left) {
      return top as unknown as PaddingFormat;
    }

    // Vertical / Horizontal shorthand when top===bottom and right===left
    if (top === bottom && right === left) {
      return [right as any, top as any] as unknown as PaddingFormat;
    }

    // Fall back to four-value CSS-style shorthand [top, right, bottom, left]
    return [top as any, right as any, bottom as any, left as any] as unknown as PaddingFormat;
  };

  return (
    <div className="flex w-full flex-col items-center gap-lg pb-4xl">
      <header className="space-y-3 text-center">
        <h1 className="text-gradient bg-linear-to-r from-primary-500 to-secondary-500 bg-clip-text text-5xl font-bold text-transparent">TextField Showcase</h1>
        <p className="text-base text-neutral-text">Adjust layout, tone, adornments, and validation behavior for the TextField wrapper built on the Input primitive.</p>
      </header>

      <section className="grid w-full justify-items-center rounded-lg border border-divider bg-foreground/20 p-md">
        <h2 className="mx-auto text-h4 font-semibold">Preview</h2>
        <TextField
          {...{
            ...textFieldProps,
            isInvalid,
            padding: paddingObjectToPaddingFormat(textFieldPadding),
            inputProps: { ...inputProps, padding: paddingObjectToPaddingFormat(inputPadding), startContent: startAdornment, endContent: endAdornment },
            value,
            onChange: setValue,
            isDisabled,
            isReadOnly,
            isRequired,
          }}
        />

        <dl className="grid w-full grid-cols-4 justify-items-center gap-2xs rounded-lg border border-divider/70 bg-alt-background p-sm text-sm text-neutral-text">
          <div className="flex flex-col">
            <dt className="text-xs font-semibold text-neutral uppercase">Layout</dt>
            <dd className="text-text">{textFieldProps.variant}</dd>
          </div>
          <div className="flex flex-col">
            <dt className="text-xs font-semibold text-neutral uppercase">Value</dt>
            <dd className="truncate text-text">{value.length > 0 ? value : <span className="text-neutral-text">Empty</span>}</dd>
          </div>
          <div className="flex flex-col">
            <dt className="text-xs font-semibold text-neutral uppercase">State</dt>
            <dd className="text-text">{isDisabled ? "Disabled" : isReadOnly ? "Read only" : isRequired ? "Required" : "Active"}</dd>
          </div>
          <div className="flex flex-col">
            <dt className="text-xs font-semibold text-neutral uppercase">Status</dt>
            <dd className="text-text">{textFieldProps.status}</dd>
          </div>
        </dl>
      </section>

      <section className="grid w-full gap-md rounded-lg border border-divider bg-foreground/20 p-lg">
        <div className="space-y-2">
          <h2 className="text-h4 font-semibold text-text">Playground Controls</h2>
          <p className="text-sm text-neutral-text">Tweak any of the props passed into the TextField wrapper, its Input primitive, and the adornments/state toggles.</p>
        </div>
        <div className="grid w-full gap-md lg:grid-cols-3">
          <div className="space-y-sm rounded-lg border border-divider/70 bg-background/80 p-md">
            <div>
              <h3 className="text-base font-semibold text-text">TextField props</h3>
              <p className="text-xs text-neutral-text">Fine-tune layout, tone, copy, and helper styling.</p>
            </div>
            <div className="grid gap-sm">
              <div className="grid items-end gap-sm sm:grid-cols-2">
                <ControlGroup label="Variant">
                  <select className={controlInputClass} value={textFieldProps.variant} onChange={(event) => updateTextFieldProp("variant", event.target.value as FieldVariant)}>
                    {FIELD_VARIANT_OPTIONS.map((option) => (
                      <option key={option} value={option}>
                        {humanize(option)}
                      </option>
                    ))}
                  </select>
                </ControlGroup>
                <ControlGroup label="Tone">
                  <select className={controlInputClass} value={textFieldProps.tone} onChange={(event) => updateTextFieldProp("tone", event.target.value as FieldTone)}>
                    {TONE_OPTIONS.map((option) => (
                      <option key={option} value={option}>
                        {humanize(option)}
                      </option>
                    ))}
                  </select>
                </ControlGroup>
                <ControlGroup label="Status">
                  <select className={controlInputClass} value={textFieldProps.status} onChange={(event) => updateTextFieldProp("status", event.target.value as FieldStatus)}>
                    {STATUS_OPTIONS.map((option) => (
                      <option key={option} value={option}>
                        {humanize(option)}
                      </option>
                    ))}
                  </select>
                </ControlGroup>
                <ControlGroup label="Field width">
                  <select className={controlInputClass} value={textFieldProps.width} onChange={(event) => updateTextFieldProp("width", event.target.value as FieldWidth)}>
                    {WIDTH_OPTIONS.map((option) => (
                      <option key={option} value={option}>
                        {humanize(option)}
                      </option>
                    ))}
                  </select>
                </ControlGroup>
                <ControlGroup label="Gap">
                  <select className={controlInputClass} value={textFieldProps.gap} onChange={(event) => updateTextFieldProp("gap", event.target.value as Spacing)}>
                    {PADDING_OPTIONS.map((option) => (
                      <option key={option} value={option}>
                        {option}
                      </option>
                    ))}
                  </select>
                </ControlGroup>
                <ControlGroup label="Field text size">
                  <select className={controlInputClass} value={textFieldProps.textSize} onChange={(event) => updateTextFieldProp("textSize", event.target.value as FontSize)}>
                    {FONT_SIZE_OPTIONS.map((option) => (
                      <option key={option} value={option}>
                        {option.toUpperCase()}
                      </option>
                    ))}
                  </select>
                </ControlGroup>
                <ControlGroup label="Label text size">
                  <select
                    className={controlInputClass}
                    value={textFieldProps.labelTextSize}
                    onChange={(event) => updateTextFieldProp("labelTextSize", event.target.value as FontSize)}
                  >
                    {FONT_SIZE_OPTIONS.map((option) => (
                      <option key={option} value={option}>
                        {option.toUpperCase()}
                      </option>
                    ))}
                  </select>
                </ControlGroup>
                <ControlGroup label="Message text size">
                  <select
                    className={controlInputClass}
                    value={textFieldProps.messageTextSize}
                    onChange={(event) => updateTextFieldProp("messageTextSize", event.target.value as FontSize)}
                  >
                    {FONT_SIZE_OPTIONS.map((option) => (
                      <option key={option} value={option}>
                        {option.toUpperCase()}
                      </option>
                    ))}
                  </select>
                </ControlGroup>
              </div>
              <ControlGroup label="Label text">
                <input className={controlInputClass} type="text" value={textFieldProps.label} onChange={(event) => updateTextFieldProp("label", event.target.value)} />
              </ControlGroup>
              <ControlGroup label="Description">
                <textarea
                  className={`${controlInputClass} min-h-[80px]`}
                  value={textFieldProps.description}
                  onChange={(event) => updateTextFieldProp("description", event.target.value)}
                />
              </ControlGroup>
              <ControlGroup label="Error message">
                <textarea
                  className={`${controlInputClass} min-h-[80px]`}
                  value={textFieldProps.errorMessage}
                  onChange={(event) => updateTextFieldProp("errorMessage", event.target.value)}
                />
              </ControlGroup>
              <div className="grid items-end gap-sm sm:grid-cols-2">
                <ControlGroup label="Wrapper className">
                  <input className={controlInputClass} type="text" value={textFieldProps.className} onChange={(event) => updateTextFieldProp("className", event.target.value)} />
                </ControlGroup>
                <ControlGroup label="Label className">
                  <input
                    className={controlInputClass}
                    type="text"
                    value={textFieldProps.labelClassName}
                    onChange={(event) => updateTextFieldProp("labelClassName", event.target.value)}
                  />
                </ControlGroup>
                <ControlGroup label="Description className">
                  <input
                    className={controlInputClass}
                    type="text"
                    value={textFieldProps.descriptionClassName}
                    onChange={(event) => updateTextFieldProp("descriptionClassName", event.target.value)}
                  />
                </ControlGroup>
                <ControlGroup label="Error className">
                  <input
                    className={controlInputClass}
                    type="text"
                    value={textFieldProps.errorMessageClassName}
                    onChange={(event) => updateTextFieldProp("errorMessageClassName", event.target.value)}
                  />
                </ControlGroup>
              </div>
              <div className="grid gap-2xs">
                <CheckboxControl
                  label="Label is effected"
                  checked={textFieldProps.doesStatusEffectLabel}
                  onChange={(checked) => updateTextFieldProp("doesStatusEffectLabel", checked)}
                />
                <CheckboxControl
                  label="Input is effected"
                  checked={textFieldProps.doesStatusEffectInput}
                  onChange={(checked) => updateTextFieldProp("doesStatusEffectInput", checked)}
                />
                <CheckboxControl
                  label="Description is effected"
                  checked={textFieldProps.doesStatusEffectDescription}
                  onChange={(checked) => updateTextFieldProp("doesStatusEffectDescription", checked)}
                />
              </div>
            </div>
          </div>
          <div className="space-y-sm rounded-lg border border-divider/70 bg-background/80 p-md">
            <div>
              <h3 className="text-base font-semibold text-text">Input props & adornments</h3>
              <p className="text-xs text-neutral-text">Adjust the primitive plus optional icons or tokens.</p>
            </div>
            <div className="grid gap-sm">
              <div className="grid items-end gap-sm sm:grid-cols-2">
                <ControlGroup label="Variant">
                  <select className={controlInputClass} value={inputProps.variant} onChange={(event) => updateInputProp("variant", event.target.value as InputVariant)}>
                    {INPUT_VARIANT_OPTIONS.map((option) => (
                      <option key={option} value={option}>
                        {humanize(option)}
                      </option>
                    ))}
                  </select>
                </ControlGroup>
                <ControlGroup label="Width">
                  <select className={controlInputClass} value={inputProps.width} onChange={(event) => updateInputProp("width", event.target.value as InputWidth)}>
                    {INPUT_WIDTH_OPTIONS.map((option) => (
                      <option key={option} value={option}>
                        {humanize(option)}
                      </option>
                    ))}
                  </select>
                </ControlGroup>
                <ControlGroup label="Radius">
                  <select
                    className={controlInputClass}
                    value={Array.isArray(inputProps.radius) ? inputProps.radius.join(",") : (inputProps.radius as Radius)}
                    onChange={(event) => updateInputProp("radius", event.target.value as RadiusFormat)}
                  >
                    {RADIUS_OPTIONS.map((option) => (
                      <option key={option} value={option}>
                        {humanize(option)}
                      </option>
                    ))}
                  </select>
                </ControlGroup>
                <ControlGroup label="Placeholder">
                  <input className={controlInputClass} type="text" value={inputProps.placeholder} onChange={(event) => updateInputProp("placeholder", event.target.value)} />
                </ControlGroup>
                <ControlGroup label="Start padding">
                  <select
                    className={controlInputClass}
                    value={String(inputProps.startPadding)}
                    onChange={(event) => updateInputProp("startPadding", event.target.value === "0" ? 0 : (event.target.value as Spacing))}
                  >
                    {OPTIONAL_PADDING_OPTIONS.map((option) => (
                      <option key={option} value={String(option)}>
                        {String(option)}
                      </option>
                    ))}
                  </select>
                </ControlGroup>
                <ControlGroup label="End padding">
                  <select
                    className={controlInputClass}
                    value={String(inputProps.endPadding)}
                    onChange={(event) => updateInputProp("endPadding", event.target.value === "0" ? 0 : (event.target.value as Spacing))}
                  >
                    {OPTIONAL_PADDING_OPTIONS.map((option) => (
                      <option key={option} value={String(option)}>
                        {String(option)}
                      </option>
                    ))}
                  </select>
                </ControlGroup>
                <ControlGroup label="Wrapper className">
                  <input
                    className={controlInputClass}
                    type="text"
                    value={inputProps.wrapperClassName}
                    onChange={(event) => updateInputProp("wrapperClassName", event.target.value)}
                  />
                </ControlGroup>
                <ControlGroup label="Input className">
                  <input className={controlInputClass} type="text" value={inputProps.inputClassName} onChange={(event) => updateInputProp("inputClassName", event.target.value)} />
                </ControlGroup>
              </div>
              <div className="grid gap-2xs">
                <CheckboxControl label="Show start adornment" checked={showStartAdornment} onChange={setShowStartAdornment} />
                <CheckboxControl label="Show end adornment" checked={showEndAdornment} onChange={setShowEndAdornment} />
              </div>
            </div>
          </div>
          <div className="space-y-sm rounded-lg border border-divider/70 bg-background/80 p-md">
            <div>
              <h3 className="text-base font-semibold text-text">Padding & state overrides</h3>
              <p className="text-xs text-neutral-text">Control per-side spacing along with disabled/read-only requirements.</p>
            </div>
            <div className="grid gap-md">
              <div className="space-y-2">
                <div className="text-xs font-semibold tracking-wide text-neutral uppercase">TextField padding</div>
                <div className="grid items-end gap-sm sm:grid-cols-2">
                  <ControlGroup label="Padding top">
                    <select
                      className={controlInputClass}
                      value={textFieldPadding.paddingTop}
                      onChange={(event) => setTextFieldPadding((prev) => ({ ...prev, paddingTop: event.target.value as Spacing }))}
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
                      value={textFieldPadding.paddingRight}
                      onChange={(event) => setTextFieldPadding((prev) => ({ ...prev, paddingRight: event.target.value as Spacing }))}
                    >
                      {PADDING_OPTIONS.map((option) => (
                        <option key={option} value={option}>
                          {option}
                        </option>
                      ))}
                    </select>
                  </ControlGroup>
                  <ControlGroup label="Padding bottom">
                    <select
                      className={controlInputClass}
                      value={textFieldPadding.paddingBottom}
                      onChange={(event) => setTextFieldPadding((prev) => ({ ...prev, paddingBottom: event.target.value as Spacing }))}
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
                      value={textFieldPadding.paddingLeft}
                      onChange={(event) => setTextFieldPadding((prev) => ({ ...prev, paddingLeft: event.target.value as Spacing }))}
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
              <div className="space-y-2">
                <div className="text-xs font-semibold tracking-wide text-neutral uppercase">Input padding</div>
                <div className="grid items-end gap-sm sm:grid-cols-2">
                  <ControlGroup label="Padding top">
                    <select
                      className={controlInputClass}
                      value={inputPadding.paddingTop}
                      onChange={(event) => setInputPadding((prev) => ({ ...prev, paddingTop: event.target.value as Spacing }))}
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
                      onChange={(event) => setInputPadding((prev) => ({ ...prev, paddingRight: event.target.value as Spacing }))}
                    >
                      {PADDING_OPTIONS.map((option) => (
                        <option key={option} value={option}>
                          {option}
                        </option>
                      ))}
                    </select>
                  </ControlGroup>
                  <ControlGroup label="Padding bottom">
                    <select
                      className={controlInputClass}
                      value={inputPadding.paddingBottom}
                      onChange={(event) => setInputPadding((prev) => ({ ...prev, paddingBottom: event.target.value as Spacing }))}
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
                      onChange={(event) => setInputPadding((prev) => ({ ...prev, paddingLeft: event.target.value as Spacing }))}
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
              <div className="grid gap-2xs">
                <CheckboxControl label="Disabled" checked={isDisabled} onChange={setIsDisabled} />
                <CheckboxControl label="Read only" checked={isReadOnly} onChange={setIsReadOnly} />
                <CheckboxControl label="Required" checked={isRequired} onChange={setIsRequired} />
                <CheckboxControl label="Invalid" checked={isInvalid} onChange={setIsInvalid} />
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
