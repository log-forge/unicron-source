import type { Route } from "../../../.react-router/types/app/routes/showcases/+types/checkbox-showcase";
import { useState, type ReactNode } from "react";
import Checkbox from "../../components/library/forms/Checkbox";
import type { CheckboxLabelPlacement, CheckboxTone, CheckboxVariant, CheckboxWidth } from "../../components/library/forms/checkbox.styles";
import type { BaseStatus, PaddingFormat, RadiusFormat } from "../../components/library/components.styles";

export function meta({}: Route.MetaArgs) {
  return [{ title: "Checkbox Showcase | Unicron" }];
}

const TONE_OPTIONS: CheckboxTone[] = ["default", "primary", "secondary", "success", "warning", "error", "neutral"];
const VARIANT_OPTIONS: CheckboxVariant[] = ["solid", "pill", "ripple", "cartoon", "outline", "ghost", "subtle", "text", "glass"];
const WIDTH_OPTIONS: CheckboxWidth[] = ["content", "full"];
const STATUS_OPTIONS: BaseStatus[] = ["default", "success", "warning", "error"];
const PLACEMENT_OPTIONS: CheckboxLabelPlacement[] = ["right", "left", "top", "bottom"];
const SPACING_OPTIONS: Spacing[] = ["0", "4xs", "3xs", "2xs", "xs", "sm", "md", "lg"];
const FONT_SIZES: FontSize[] = ["h5", "base", "sm", "xs", "2xs"];
const RADIUS_OPTIONS: Radius[] = ["none", "sm", "md", "lg", "full"];
const controlInputClass =
  "w-full rounded-md border border-divider bg-background px-sm py-2xs text-sm text-text shadow-sm focus-visible:border-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500";

export default function CheckboxShowcase() {
  const [isSelected, setIsSelected] = useState(false);
  const [isIndeterminate, setIsIndeterminate] = useState(false);
  const [isDisabled, setIsDisabled] = useState(false);
  const [isReadOnly, setIsReadOnly] = useState(false);
  const [isRequired, setIsRequired] = useState(false);
  const [isInvalid, setIsInvalid] = useState(false);
  const [checkboxProps, setCheckboxProps] = useState({
    label: "I agree to the terms and conditions.",
    variant: "solid" as CheckboxVariant,
    tone: "default" as CheckboxTone,
    status: "default" as BaseStatus,
    size: "sm" as FontSize,
    width: "content" as CheckboxWidth,
    labelPlacement: "right" as CheckboxLabelPlacement,
    padding: "3xs" as PaddingFormat,
    radius: "sm" as RadiusFormat,
    gap: "xs" as Spacing,
    messageGap: "4xs" as Spacing,
    labelTextSize: "base" as FontSize,
    descriptionTextSize: "xs" as FontSize,
    messageTextSize: "xs" as FontSize,
    doesStatusEffectLabel: true,
    doesStatusEffectDescription: true,
    description: "This is a description for the checkbox.",
    errorMessage: "This is an error message for the checkbox.",
    className: "max-w-[420px]",
    controlClassName: "",
    inputClassName: "",
    labelClassName: "",
    descriptionClassName: "",
    messageClassName: "",
  });

  const updateCheckboxProp = <K extends keyof typeof checkboxProps>(key: K, value: (typeof checkboxProps)[K]) => {
    setCheckboxProps((prev) => ({ ...prev, [key]: value }));
  };

  return (
    <div className="flex w-full flex-col gap-lg pb-4xl">
      <header className="space-y-3 text-center">
        <h1 className="text-gradient bg-gradient-to-r from-primary-500 to-secondary-500 bg-clip-text text-5xl font-bold text-transparent">Checkbox Showcase</h1>
        <p className="text-base text-neutral-text">Configure tone, placement, spacing, and validation for the React Aria powered Checkbox wrapper with live preview.</p>
      </header>

      <section className="grid w-full justify-items-center gap-md rounded-lg border border-divider bg-foreground/20 p-md">
        <h2 className="mx-auto text-h4 font-semibold">Preview</h2>
        <Checkbox
          {...{
            ...checkboxProps,
            isSelected,
            onChange: setIsSelected,
            isIndeterminate,
            isDisabled,
            isReadOnly,
            isRequired,
            isInvalid,
          }}
        />

        <dl className="grid w-full grid-cols-4 justify-items-center gap-2xs rounded-lg border border-divider/70 bg-alt-background p-sm text-sm text-neutral-text">
          <div className="flex flex-col">
            <dt className="text-xs font-semibold text-neutral uppercase">Variant</dt>
            <dd className="text-text">{checkboxProps.variant}</dd>
          </div>
          <div className="flex flex-col">
            <dt className="text-xs font-semibold text-neutral uppercase">Label Placement</dt>
            <dd className="text-text">{checkboxProps.labelPlacement}</dd>
          </div>
          <div className="flex flex-col">
            <dt className="text-xs font-semibold text-neutral uppercase">Value</dt>
            <dd className="text-text">{isIndeterminate ? "Indeterminate" : isSelected ? "Selected" : "Unselected"}</dd>
          </div>
          <div className="flex flex-col">
            <dt className="text-xs font-semibold text-neutral uppercase">State</dt>
            <dd className="text-text">{isDisabled ? "Disabled" : isReadOnly ? "Read only" : isRequired ? "Required" : "Active"}</dd>
          </div>
          <div className="flex flex-col">
            <dt className="text-xs font-semibold text-neutral uppercase">Status</dt>
            <dd className="text-text">{checkboxProps.status}</dd>
          </div>
        </dl>
      </section>

      <section className="grid w-full gap-md rounded-lg border border-divider bg-foreground/20 p-lg">
        <div className="space-y-2">
          <h2 className="text-h4 font-semibold text-text">Playground Controls</h2>
          <p className="text-sm text-neutral-text">Tweak the Checkbox wrapper props, helper content, and state flags.</p>
        </div>
        <div className="grid w-full gap-md lg:grid-cols-3">
          <div className="space-y-sm rounded-lg border border-divider/70 bg-background/80 p-md">
            <div>
              <h3 className="text-base font-semibold text-text">Checkbox props</h3>
              <p className="text-xs text-neutral-text">Adjust tone, layout, spacing, and helper copy.</p>
            </div>
            <div className="grid gap-sm">
              <div className="grid items-end gap-sm sm:grid-cols-2">
                <ControlGroup label="Variant">
                  <select className={controlInputClass} value={checkboxProps.variant} onChange={(event) => updateCheckboxProp("variant", event.target.value as CheckboxVariant)}>
                    {VARIANT_OPTIONS.map((option) => (
                      <option key={option} value={option}>
                        {humanize(option)}
                      </option>
                    ))}
                  </select>
                </ControlGroup>
                <ControlGroup label="Tone">
                  <select className={controlInputClass} value={checkboxProps.tone} onChange={(event) => updateCheckboxProp("tone", event.target.value as CheckboxTone)}>
                    {TONE_OPTIONS.map((option) => (
                      <option key={option} value={option}>
                        {humanize(option)}
                      </option>
                    ))}
                  </select>
                </ControlGroup>
                <ControlGroup label="Status">
                  <select className={controlInputClass} value={checkboxProps.status} onChange={(event) => updateCheckboxProp("status", event.target.value as BaseStatus)}>
                    {STATUS_OPTIONS.map((option) => (
                      <option key={option} value={option}>
                        {humanize(option)}
                      </option>
                    ))}
                  </select>
                </ControlGroup>
                <ControlGroup label="Width">
                  <select className={controlInputClass} value={checkboxProps.width} onChange={(event) => updateCheckboxProp("width", event.target.value as CheckboxWidth)}>
                    {WIDTH_OPTIONS.map((option) => (
                      <option key={option} value={option}>
                        {humanize(option)}
                      </option>
                    ))}
                  </select>
                </ControlGroup>
                <ControlGroup label="Label placement">
                  <select
                    className={controlInputClass}
                    value={checkboxProps.labelPlacement}
                    onChange={(event) => updateCheckboxProp("labelPlacement", event.target.value as CheckboxLabelPlacement)}
                  >
                    {PLACEMENT_OPTIONS.map((option) => (
                      <option key={option} value={option}>
                        {humanize(option)}
                      </option>
                    ))}
                  </select>
                </ControlGroup>
                <ControlGroup label="Radius">
                  <select className={controlInputClass} value={String(checkboxProps.radius)} onChange={(event) => updateCheckboxProp("radius", event.target.value as RadiusFormat)}>
                    {RADIUS_OPTIONS.map((option) => (
                      <option key={option} value={option}>
                        {humanize(option)}
                      </option>
                    ))}
                  </select>
                </ControlGroup>
                <ControlGroup label="Size">
                  <select className={controlInputClass} value={checkboxProps.size} onChange={(event) => updateCheckboxProp("size", event.target.value as FontSize)}>
                    {FONT_SIZES.map((option) => (
                      <option key={option} value={option}>
                        {option.toUpperCase()}
                      </option>
                    ))}
                  </select>
                </ControlGroup>
                <ControlGroup label="Padding">
                  <select
                    className={controlInputClass}
                    value={String(checkboxProps.padding)}
                    onChange={(event) => updateCheckboxProp("padding", event.target.value as PaddingFormat)}
                  >
                    {SPACING_OPTIONS.map((option) => (
                      <option key={option} value={option}>
                        {option}
                      </option>
                    ))}
                  </select>
                </ControlGroup>
                <ControlGroup label="Control gap">
                  <select className={controlInputClass} value={checkboxProps.gap} onChange={(event) => updateCheckboxProp("gap", event.target.value as Spacing)}>
                    {SPACING_OPTIONS.map((option) => (
                      <option key={option} value={option}>
                        {option}
                      </option>
                    ))}
                  </select>
                </ControlGroup>
                <ControlGroup label="Message gap">
                  <select className={controlInputClass} value={checkboxProps.messageGap} onChange={(event) => updateCheckboxProp("messageGap", event.target.value as Spacing)}>
                    {SPACING_OPTIONS.map((option) => (
                      <option key={option} value={option}>
                        {option}
                      </option>
                    ))}
                  </select>
                </ControlGroup>
                <ControlGroup label="Label text size">
                  <select
                    className={controlInputClass}
                    value={checkboxProps.labelTextSize}
                    onChange={(event) => updateCheckboxProp("labelTextSize", event.target.value as FontSize)}
                  >
                    {FONT_SIZES.map((option) => (
                      <option key={option} value={option}>
                        {option.toUpperCase()}
                      </option>
                    ))}
                  </select>
                </ControlGroup>
                <ControlGroup label="Description text size">
                  <select
                    className={controlInputClass}
                    value={checkboxProps.descriptionTextSize}
                    onChange={(event) => updateCheckboxProp("descriptionTextSize", event.target.value as FontSize)}
                  >
                    {FONT_SIZES.map((option) => (
                      <option key={option} value={option}>
                        {option.toUpperCase()}
                      </option>
                    ))}
                  </select>
                </ControlGroup>
                <ControlGroup label="Message text size">
                  <select
                    className={controlInputClass}
                    value={checkboxProps.messageTextSize}
                    onChange={(event) => updateCheckboxProp("messageTextSize", event.target.value as FontSize)}
                  >
                    {FONT_SIZES.map((option) => (
                      <option key={option} value={option}>
                        {option.toUpperCase()}
                      </option>
                    ))}
                  </select>
                </ControlGroup>
              </div>
              <ControlGroup label="Label text">
                <input className={controlInputClass} type="text" value={checkboxProps.label} onChange={(event) => updateCheckboxProp("label", event.target.value)} />
              </ControlGroup>
              <ControlGroup label="Description">
                <textarea
                  className={`${controlInputClass} min-h-[80px]`}
                  value={checkboxProps.description}
                  onChange={(event) => updateCheckboxProp("description", event.target.value)}
                />
              </ControlGroup>
              <ControlGroup label="Error message">
                <textarea
                  className={`${controlInputClass} min-h-[80px]`}
                  value={checkboxProps.errorMessage}
                  onChange={(event) => updateCheckboxProp("errorMessage", event.target.value)}
                />
              </ControlGroup>
              <div className="grid items-end gap-sm sm:grid-cols-2">
                <ControlGroup label="Wrapper className">
                  <input className={controlInputClass} type="text" value={checkboxProps.className} onChange={(event) => updateCheckboxProp("className", event.target.value)} />
                </ControlGroup>
                <ControlGroup label="Control className">
                  <input
                    className={controlInputClass}
                    type="text"
                    value={checkboxProps.controlClassName}
                    onChange={(event) => updateCheckboxProp("controlClassName", event.target.value)}
                  />
                </ControlGroup>
                <ControlGroup label="Input className">
                  <input
                    className={controlInputClass}
                    type="text"
                    value={checkboxProps.inputClassName}
                    onChange={(event) => updateCheckboxProp("inputClassName", event.target.value)}
                  />
                </ControlGroup>
                <ControlGroup label="Label className">
                  <input
                    className={controlInputClass}
                    type="text"
                    value={checkboxProps.labelClassName}
                    onChange={(event) => updateCheckboxProp("labelClassName", event.target.value)}
                  />
                </ControlGroup>
                <ControlGroup label="Description className">
                  <input
                    className={controlInputClass}
                    type="text"
                    value={checkboxProps.descriptionClassName}
                    onChange={(event) => updateCheckboxProp("descriptionClassName", event.target.value)}
                  />
                </ControlGroup>
                <ControlGroup label="Message className">
                  <input
                    className={controlInputClass}
                    type="text"
                    value={checkboxProps.messageClassName}
                    onChange={(event) => updateCheckboxProp("messageClassName", event.target.value)}
                  />
                </ControlGroup>
              </div>
              <div className="grid gap-2xs">
                <CheckboxControl
                  label="Status affects label"
                  checked={checkboxProps.doesStatusEffectLabel}
                  onChange={(checked) => updateCheckboxProp("doesStatusEffectLabel", checked)}
                />
                <CheckboxControl
                  label="Status affects description"
                  checked={checkboxProps.doesStatusEffectDescription}
                  onChange={(checked) => updateCheckboxProp("doesStatusEffectDescription", checked)}
                />
              </div>
            </div>
          </div>
          <div className="space-y-sm rounded-lg border border-divider/70 bg-background/80 p-md">
            <div>
              <h3 className="text-base font-semibold text-text">State toggles</h3>
              <p className="text-xs text-neutral-text">Drive the checkbox selection and validation flags.</p>
            </div>
            <div className="grid gap-2xs">
              <CheckboxControl label="Selected" checked={isSelected} onChange={setIsSelected} />
              <CheckboxControl label="Indeterminate" checked={isIndeterminate} onChange={setIsIndeterminate} />
              <CheckboxControl label="Disabled" checked={isDisabled} onChange={setIsDisabled} />
              <CheckboxControl label="Read only" checked={isReadOnly} onChange={setIsReadOnly} />
              <CheckboxControl label="Required" checked={isRequired} onChange={setIsRequired} />
              <CheckboxControl label="Invalid" checked={isInvalid} onChange={setIsInvalid} />
            </div>
          </div>
          <div className="space-y-sm rounded-lg border border-divider/70 bg-background/80 p-md">
            <div>
              <h3 className="text-base font-semibold text-text">Quick presets</h3>
              <p className="text-xs text-neutral-text">Jump to common configurations.</p>
            </div>
            <div className="grid gap-2xs">
              <button
                type="button"
                className={controlInputClass}
                onClick={() =>
                  setCheckboxProps((prev) => ({
                    ...prev,
                    variant: "solid",
                    tone: "primary",
                    status: "default",
                    labelPlacement: "right",
                    doesStatusEffectLabel: true,
                    doesStatusEffectDescription: true,
                  }))
                }
              >
                Primary solid
              </button>
              <button
                type="button"
                className={controlInputClass}
                onClick={() => {
                  setCheckboxProps((prev) => ({
                    ...prev,
                    variant: "outline",
                    tone: "warning",
                    status: "warning",
                    doesStatusEffectLabel: true,
                    doesStatusEffectDescription: true,
                  }));
                  setIsInvalid(true);
                }}
              >
                Warning outline
              </button>
              <button
                type="button"
                className={controlInputClass}
                onClick={() =>
                  setCheckboxProps((prev) => ({
                    ...prev,
                    variant: "ghost",
                    tone: "neutral",
                    status: "default",
                    labelPlacement: "left",
                    doesStatusEffectLabel: false,
                    doesStatusEffectDescription: false,
                  }))
                }
              >
                Neutral ghost (tone fixed)
              </button>
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
