import type { Route } from "../../../.react-router/types/app/routes/showcases/+types/combo-box-showcase";
import { useState, type Key, type ReactNode } from "react";
import { User } from "lucide-react";
import { ListBoxLoadMoreItem } from "react-aria-components";
import type { ButtonVariant } from "../../components/library/buttons/button.styles";
import type { PaddingFormat, RadiusFormat } from "../../components/library/components.styles";
import type { InputVariant } from "../../components/library/forms/input.styles";
import { ComboBox, ListBoxItem } from "../../components/library/pickers/combo box/ComboBox";
import type { ComboBoxVariant, ComboBoxTone, ComboBoxStatus, ComboBoxWidth, PopoverVariant } from "../../components/library/pickers/combo box/combo-box.styles";
import clsx from "clsx";
import Checkbox from "../../components/library/forms/Checkbox";

export function meta({}: Route.MetaArgs) {
  return [{ title: "ComboBox Showcase | Unicron" }];
}

const COMBO_BOX_OPTIONS = [
  { id: "orion", label: "Orion Nebula" },
  { id: "andromeda", label: "Andromeda Galaxy" },
  { id: "perseus", label: "Perseus Cluster" },
  { id: "centaurus", label: "Centaurus A" },
  { id: "triangulum", label: "Triangulum Galaxy" },
];

const VARIANT_OPTIONS: ComboBoxVariant[] = ["stacked", "inline", "floating", "nested_floating"];
const POPOVER_VARIANT_OPTIONS: PopoverVariant[] = ["solid", "outline", "ghost", "subtle"];
const TONE_OPTIONS: ComboBoxTone[] = ["default", "primary", "secondary", "success", "warning", "error", "neutral"];
const STATUS_OPTIONS: ComboBoxStatus[] = ["default", "success", "warning", "error"];
const WIDTH_OPTIONS: ComboBoxWidth[] = ["content", "full"];
const RADIUS_OPTIONS: Radius[] = ["none", "sm", "md", "lg", "full"];
const PADDING_OPTIONS: Spacing[] = ["0", "4xs", "3xs", "2xs", "xs", "sm", "md", "lg"];
const OPTIONAL_PADDING_OPTIONS: (Spacing | 0)[] = [0, "4xs", "3xs", "2xs", "xs", "sm", "md", "lg"];
const FONT_SIZE_OPTIONS: FontSize[] = ["h1", "h2", "h3", "h4", "h5", "base", "sm", "xs", "2xs"];
const controlInputClass =
  "w-full rounded-md border border-divider bg-background px-sm py-2xs text-sm text-text shadow-sm focus-visible:border-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500";

export default function ComboBoxShowcase() {
  const [inputValue, setInputValue] = useState(COMBO_BOX_OPTIONS[0].label);
  const [selectedKey, setSelectedKey] = useState<string | null>(COMBO_BOX_OPTIONS[0].id);
  const [isDisabled, setIsDisabled] = useState(false);
  const [isReadOnly, setIsReadOnly] = useState(false);
  const [isRequired, setIsRequired] = useState(false);
  const [isInvalid, setIsInvalid] = useState(false);
  const [showStartAdornment, setShowStartAdornment] = useState(true);
  const [comboBoxProps, setComboBoxProps] = useState({
    variant: "stacked" as ComboBoxVariant,
    popoverVariant: "solid" as PopoverVariant,
    tone: "default" as ComboBoxTone,
    status: "default" as ComboBoxStatus,
    width: "full" as ComboBoxWidth,
    radius: "md" as RadiusFormat,
    popoverRadius: "md" as RadiusFormat,
    listBoxRadius: "md" as RadiusFormat,
    padding: "xs" as PaddingFormat,
    popoverPadding: "xs" as Spacing | 0,
    textSize: "sm" as FontSize,
    labelTextSize: "base" as FontSize,
    messageTextSize: "xs" as FontSize,
    gap: "3xs" as string,
    labelGap: "xs" as string,
    messageGap: "4xs" as string,
    doesStatusEffectLabel: false as boolean,
    doesStatusEffectDescription: false as boolean,
    popoverClassName: "" as string,
    listBoxClassName: "" as string,
    labelClassName: "font-bold" as string,
    descriptionClassName: "" as string,
    messageClassName: "" as string,
    label: "Combo box picker" as string,
    description: "" as string | null,
    errorMessage: "" as string | ((validation: any) => string),
  });
  const [inputProps, setInputProps] = useState({
    variant: "solid" as InputVariant,
    padding: ["sm", "4xs"] as PaddingFormat,
    wrapperClassName: "",
    inputClassName: "",
    startPadding: "sm" as Spacing | 0,
    endPadding: "sm" as Spacing | 0,
    placeholder: "Search options",
  });
  const [buttonProps, setButtonProps] = useState({
    variant: "solid" as ButtonVariant,
    radius: "md" as RadiusFormat,
    padding: "4xs" as PaddingFormat,
    className: "" as string,
  });
  const [comboBoxPadding, setComboBoxPadding] = useState({
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
  const [buttonPadding, setButtonPadding] = useState({
    paddingTop: "4xs",
    paddingRight: "4xs",
    paddingBottom: "4xs",
    paddingLeft: "4xs",
  });
  const [isLoading, setIsLoading] = useState(false);

  const startAdornment = showStartAdornment ? (
    <User className="" style={{ height: `var(--text-${comboBoxProps.textSize})`, width: `var(--text-${comboBoxProps.textSize})` }} />
  ) : undefined;

  const updateComboBoxProps = (prop: keyof typeof comboBoxProps, value: any) => {
    setComboBoxProps((prev) => ({ ...prev, [prop]: value }));
  };

  const updateInputProps = (prop: keyof typeof inputProps, value: any) => {
    setInputProps((prev) => ({ ...prev, [prop]: value }));
  };

  const updateButtonProps = (prop: keyof typeof buttonProps, value: any) => {
    setButtonProps((prev) => ({ ...prev, [prop]: value }));
  };

  const paddingObjectToPaddingFormat = (obj: { paddingTop: any; paddingRight: any; paddingBottom: any; paddingLeft: any }): PaddingFormat => {
    const top = String(obj.paddingTop);
    const right = String(obj.paddingRight);
    const bottom = String(obj.paddingBottom);
    const left = String(obj.paddingLeft);

    if (top === right && top === bottom && top === left) {
      return top as unknown as PaddingFormat;
    }

    if (top === bottom && right === left) {
      return [right as any, top as any] as unknown as PaddingFormat;
    }

    return [top as any, right as any, bottom as any, left as any] as unknown as PaddingFormat;
  };

  const handleSelectionChange = (key: Key | null) => {
    const keyAsString = key ? String(key) : null;
    setSelectedKey(keyAsString);
    const selectedOption = COMBO_BOX_OPTIONS.find((option) => option.id === keyAsString);
    setInputValue(selectedOption?.label ?? "");
  };

  const selectedOptionLabel = COMBO_BOX_OPTIONS.find((option) => option.id === selectedKey)?.label;

  return (
    <div className="flex w-full flex-col items-center gap-lg pb-4xl">
      <header className="space-y-3 text-center">
        <h1 className="text-gradient bg-linear-to-r from-primary-500 to-secondary-500 bg-clip-text text-5xl font-bold text-transparent">ComboBox Showcase</h1>
        <p className="text-base text-neutral-text">Preview the ComboBox component with selectable options and synchronized input state.</p>
      </header>

      <section className="grid w-full justify-items-center gap-sm rounded-lg border border-divider bg-foreground/20 p-md">
        <h2 className="mx-auto text-h4 font-semibold">ComboBox Preview</h2>
        <ComboBox
          {...{
            ...comboBoxProps,
            isInvalid,
            padding: paddingObjectToPaddingFormat(comboBoxPadding),
            inputProps: { ...inputProps, padding: paddingObjectToPaddingFormat(inputPadding), startContent: startAdornment },
            buttonProps: { ...buttonProps, padding: paddingObjectToPaddingFormat(buttonPadding), isPending: isLoading },
            inputValue,
            onInputChange: (value: string) => {
              setInputValue(value);
              setSelectedKey(null);
            },
            selectedKey,
            onSelectionChange: handleSelectionChange,
            isDisabled,
            isReadOnly,
            isRequired,
            className: clsx("max-w-[380px]"),
          }}
        >
          {COMBO_BOX_OPTIONS.map((item) => (
            <ListBoxItem key={item.id} id={item.id} textValue={item.label}>
              {item.label}
            </ListBoxItem>
          ))}
          {isLoading && <ListBoxLoadMoreItem isLoading>Loading results…</ListBoxLoadMoreItem>}
        </ComboBox>

        <dl className="grid w-full grid-cols-4 justify-items-center gap-2xs rounded-lg border border-divider/70 bg-alt-background p-sm text-sm text-neutral-text">
          <div className="flex flex-col">
            <dt className="text-xs font-semibold text-neutral uppercase">Layout</dt>
            <dd className="text-text">{comboBoxProps.variant}</dd>
          </div>
          <div className="flex flex-col">
            <dt className="text-xs font-semibold text-neutral uppercase">Value</dt>
            <dd className="truncate text-text">{selectedOptionLabel ?? (inputValue.length > 0 ? inputValue : <span className="text-neutral-text">Empty</span>)}</dd>
          </div>
          <div className="flex flex-col">
            <dt className="text-xs font-semibold text-neutral uppercase">State</dt>
            <dd className="text-text">{isDisabled ? "Disabled" : isReadOnly ? "Read only" : isRequired ? "Required" : "Active"}</dd>
          </div>
          <div className="flex flex-col">
            <dt className="text-xs font-semibold text-neutral uppercase">Status</dt>
            <dd className="text-text">{comboBoxProps.status}</dd>
          </div>
        </dl>
      </section>

      <section className="grid w-full gap-md rounded-lg border border-divider bg-foreground/20 p-lg">
        <div className="space-y-2">
          <h2 className="text-h4 font-semibold text-text">Playground Controls</h2>
          <p className="text-sm text-neutral-text">Tweak any of the props passed into the ComboBox wrapper, its Input primitive, and the trigger button.</p>
        </div>
        <div className="grid w-full gap-md lg:grid-cols-3">
          <div className="space-y-sm rounded-lg border border-divider/70 bg-background/80 p-md">
            <div>
              <h3 className="text-base font-semibold text-text">ComboBox props</h3>
              <p className="text-xs text-neutral-text">Layout, tone, spacing, and copy.</p>
            </div>
            <div className="grid gap-sm">
              <div className="grid items-end gap-sm sm:grid-cols-2">
                <ControlGroup label="Variant">
                  <select className={controlInputClass} value={comboBoxProps.variant} onChange={(event) => updateComboBoxProps("variant", event.target.value as ComboBoxVariant)}>
                    {VARIANT_OPTIONS.map((option) => (
                      <option key={option} value={option}>
                        {humanize(option)}
                      </option>
                    ))}
                  </select>
                </ControlGroup>
                <ControlGroup label="Popover variant">
                  <select
                    className={controlInputClass}
                    value={comboBoxProps.popoverVariant}
                    onChange={(event) => updateComboBoxProps("popoverVariant", event.target.value as PopoverVariant)}
                  >
                    {POPOVER_VARIANT_OPTIONS.map((option) => (
                      <option key={option} value={option}>
                        {humanize(option)}
                      </option>
                    ))}
                  </select>
                </ControlGroup>
                <ControlGroup label="Tone">
                  <select className={controlInputClass} value={comboBoxProps.tone} onChange={(event) => updateComboBoxProps("tone", event.target.value as ComboBoxTone)}>
                    {TONE_OPTIONS.map((option) => (
                      <option key={option} value={option}>
                        {humanize(option)}
                      </option>
                    ))}
                  </select>
                </ControlGroup>
                <ControlGroup label="Status">
                  <select className={controlInputClass} value={comboBoxProps.status} onChange={(event) => updateComboBoxProps("status", event.target.value as ComboBoxStatus)}>
                    {STATUS_OPTIONS.map((option) => (
                      <option key={option} value={option}>
                        {humanize(option)}
                      </option>
                    ))}
                  </select>
                </ControlGroup>
                <ControlGroup label="Width">
                  <select className={controlInputClass} value={comboBoxProps.width} onChange={(event) => updateComboBoxProps("width", event.target.value as ComboBoxWidth)}>
                    {WIDTH_OPTIONS.map((option) => (
                      <option key={option} value={option}>
                        {humanize(option)}
                      </option>
                    ))}
                  </select>
                </ControlGroup>
                <ControlGroup label="Radius">
                  <select className={controlInputClass} value={comboBoxProps.radius} onChange={(event) => updateComboBoxProps("radius", event.target.value as Radius)}>
                    {RADIUS_OPTIONS.map((option) => (
                      <option key={option} value={option}>
                        {option}
                      </option>
                    ))}
                  </select>
                </ControlGroup>
                <ControlGroup label="Popover radius">
                  <select
                    className={controlInputClass}
                    value={comboBoxProps.popoverRadius}
                    onChange={(event) => updateComboBoxProps("popoverRadius", event.target.value as Radius)}
                  >
                    {RADIUS_OPTIONS.map((option) => (
                      <option key={option} value={option}>
                        {option}
                      </option>
                    ))}
                  </select>
                </ControlGroup>
                <ControlGroup label="ListBox radius">
                  <select
                    className={controlInputClass}
                    value={comboBoxProps.listBoxRadius}
                    onChange={(event) => updateComboBoxProps("listBoxRadius", event.target.value as Radius)}
                  >
                    {RADIUS_OPTIONS.map((option) => (
                      <option key={option} value={option}>
                        {option}
                      </option>
                    ))}
                  </select>
                </ControlGroup>
              </div>

              <div className="grid gap-sm sm:grid-cols-2">
                <ControlGroup label="Field padding (top)">
                  <select
                    className={controlInputClass}
                    value={comboBoxPadding.paddingTop}
                    onChange={(event) => setComboBoxPadding((prev) => ({ ...prev, paddingTop: event.target.value as Spacing }))}
                  >
                    {PADDING_OPTIONS.map((option) => (
                      <option key={option} value={option}>
                        {option}
                      </option>
                    ))}
                  </select>
                </ControlGroup>
                <ControlGroup label="Field padding (right)">
                  <select
                    className={controlInputClass}
                    value={comboBoxPadding.paddingRight}
                    onChange={(event) => setComboBoxPadding((prev) => ({ ...prev, paddingRight: event.target.value as Spacing }))}
                  >
                    {PADDING_OPTIONS.map((option) => (
                      <option key={option} value={option}>
                        {option}
                      </option>
                    ))}
                  </select>
                </ControlGroup>
              </div>
              <div className="grid gap-sm sm:grid-cols-2">
                <ControlGroup label="Field padding (bottom)">
                  <select
                    className={controlInputClass}
                    value={comboBoxPadding.paddingBottom}
                    onChange={(event) => setComboBoxPadding((prev) => ({ ...prev, paddingBottom: event.target.value as Spacing }))}
                  >
                    {PADDING_OPTIONS.map((option) => (
                      <option key={option} value={option}>
                        {option}
                      </option>
                    ))}
                  </select>
                </ControlGroup>
                <ControlGroup label="Field padding (left)">
                  <select
                    className={controlInputClass}
                    value={comboBoxPadding.paddingLeft}
                    onChange={(event) => setComboBoxPadding((prev) => ({ ...prev, paddingLeft: event.target.value as Spacing }))}
                  >
                    {PADDING_OPTIONS.map((option) => (
                      <option key={option} value={option}>
                        {option}
                      </option>
                    ))}
                  </select>
                </ControlGroup>
              </div>

              <div className="grid gap-sm sm:grid-cols-2">
                <ControlGroup label="Popover padding">
                  <select
                    className={controlInputClass}
                    value={comboBoxProps.popoverPadding}
                    onChange={(event) => updateComboBoxProps("popoverPadding", event.target.value as PaddingFormat)}
                  >
                    {OPTIONAL_PADDING_OPTIONS.map((option) => (
                      <option key={option} value={option}>
                        {option}
                      </option>
                    ))}
                  </select>
                </ControlGroup>
              </div>

              <div className="grid gap-sm sm:grid-cols-2">
                <ControlGroup label="Field text size">
                  <select className={controlInputClass} value={comboBoxProps.textSize} onChange={(event) => updateComboBoxProps("textSize", event.target.value as FontSize)}>
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
                    value={comboBoxProps.labelTextSize}
                    onChange={(event) => updateComboBoxProps("labelTextSize", event.target.value as FontSize)}
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
                    value={comboBoxProps.messageTextSize}
                    onChange={(event) => updateComboBoxProps("messageTextSize", event.target.value as FontSize)}
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
                <input className={controlInputClass} type="text" value={comboBoxProps.label} onChange={(event) => updateComboBoxProps("label", event.target.value)} />
              </ControlGroup>
              <ControlGroup label="Description">
                <textarea
                  className={`${controlInputClass} min-h-[80px]`}
                  value={comboBoxProps.description ?? ""}
                  onChange={(event) => updateComboBoxProps("description", event.target.value)}
                />
              </ControlGroup>
              <ControlGroup label="Error message">
                <textarea
                  className={`${controlInputClass} min-h-[80px]`}
                  value={typeof comboBoxProps.errorMessage === "string" ? comboBoxProps.errorMessage : ""}
                  onChange={(event) => updateComboBoxProps("errorMessage", event.target.value)}
                />
              </ControlGroup>
              <div className="grid gap-sm sm:grid-cols-2">
                <ControlGroup label="Label className">
                  <input
                    className={controlInputClass}
                    type="text"
                    value={comboBoxProps.labelClassName}
                    onChange={(event) => updateComboBoxProps("labelClassName", event.target.value)}
                  />
                </ControlGroup>
                <ControlGroup label="Description className">
                  <input
                    className={controlInputClass}
                    type="text"
                    value={comboBoxProps.descriptionClassName}
                    onChange={(event) => updateComboBoxProps("descriptionClassName", event.target.value)}
                  />
                </ControlGroup>
                <ControlGroup label="Message className">
                  <input
                    className={controlInputClass}
                    type="text"
                    value={comboBoxProps.messageClassName}
                    onChange={(event) => updateComboBoxProps("messageClassName", event.target.value)}
                  />
                </ControlGroup>
                <ControlGroup label="Popover className">
                  <input
                    className={controlInputClass}
                    type="text"
                    value={comboBoxProps.popoverClassName}
                    onChange={(event) => updateComboBoxProps("popoverClassName", event.target.value)}
                  />
                </ControlGroup>
                <ControlGroup label="ListBox className">
                  <input
                    className={controlInputClass}
                    type="text"
                    value={comboBoxProps.listBoxClassName}
                    onChange={(event) => updateComboBoxProps("listBoxClassName", event.target.value)}
                  />
                </ControlGroup>
              </div>

              <div className="flex flex-wrap items-center gap-sm">
                <Checkbox
                  size="sm"
                  variant="outline"
                  width="content"
                  labelPlacement="right"
                  isSelected={comboBoxProps.doesStatusEffectLabel}
                  onChange={(checked) => updateComboBoxProps("doesStatusEffectLabel", checked)}
                >
                  Status affects label
                </Checkbox>
                <Checkbox
                  size="sm"
                  variant="outline"
                  width="content"
                  labelPlacement="right"
                  isSelected={comboBoxProps.doesStatusEffectDescription}
                  onChange={(checked) => updateComboBoxProps("doesStatusEffectDescription", checked)}
                >
                  Status affects description
                </Checkbox>
              </div>
            </div>
          </div>

          <div className="space-y-sm rounded-lg border border-divider/70 bg-background/80 p-md">
            <div>
              <h3 className="text-base font-semibold text-text">Input props</h3>
              <p className="text-xs text-neutral-text">Padding, adornments, and placeholder.</p>
            </div>
            <div className="grid gap-sm">
              <div className="grid gap-sm sm:grid-cols-2">
                <ControlGroup label="Variant">
                  <select className={controlInputClass} value={inputProps.variant} onChange={(event) => updateInputProps("variant", event.target.value as InputVariant)}>
                    {["solid", "outline", "subtle", "ghost", "text", "underline"].map((option) => (
                      <option key={option} value={option}>
                        {humanize(option)}
                      </option>
                    ))}
                  </select>
                </ControlGroup>
                <ControlGroup label="Placeholder">
                  <input className={controlInputClass} type="text" value={inputProps.placeholder} onChange={(event) => updateInputProps("placeholder", event.target.value)} />
                </ControlGroup>
              </div>

              <div className="grid gap-sm sm:grid-cols-2">
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
              </div>
              <div className="grid gap-sm sm:grid-cols-2">
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

              <div className="grid gap-sm sm:grid-cols-2">
                <ControlGroup label="Start padding">
                  <select
                    className={controlInputClass}
                    value={inputProps.startPadding === 0 ? "0" : (inputProps.startPadding as string)}
                    onChange={(event) => updateInputProps("startPadding", event.target.value === "0" ? 0 : (event.target.value as Spacing))}
                  >
                    {OPTIONAL_PADDING_OPTIONS.map((option) => (
                      <option key={option} value={option}>
                        {option}
                      </option>
                    ))}
                  </select>
                </ControlGroup>
                <ControlGroup label="End padding">
                  <select
                    className={controlInputClass}
                    value={inputProps.endPadding === 0 ? "0" : (inputProps.endPadding as string)}
                    onChange={(event) => updateInputProps("endPadding", event.target.value === "0" ? 0 : (event.target.value as Spacing))}
                  >
                    {OPTIONAL_PADDING_OPTIONS.map((option) => (
                      <option key={option} value={option}>
                        {option}
                      </option>
                    ))}
                  </select>
                </ControlGroup>
              </div>

              <div className="grid gap-sm sm:grid-cols-2">
                <ControlGroup label="Wrapper className">
                  <input
                    className={controlInputClass}
                    type="text"
                    value={inputProps.wrapperClassName}
                    onChange={(event) => updateInputProps("wrapperClassName", event.target.value)}
                  />
                </ControlGroup>
                <ControlGroup label="Input className">
                  <input className={controlInputClass} type="text" value={inputProps.inputClassName} onChange={(event) => updateInputProps("inputClassName", event.target.value)} />
                </ControlGroup>
              </div>

              <Checkbox size="sm" variant="outline" width="content" labelPlacement="right" isSelected={showStartAdornment} onChange={setShowStartAdornment}>
                Show start adornment
              </Checkbox>
            </div>
          </div>

          <div className="space-y-sm rounded-lg border border-divider/70 bg-background/80 p-md">
            <div>
              <h3 className="text-base font-semibold text-text">Trigger button</h3>
              <p className="text-xs text-neutral-text">Chevron styling and padding.</p>
            </div>
            <div className="grid gap-sm">
              <ControlGroup label="Variant">
                <select className={controlInputClass} value={buttonProps.variant} onChange={(event) => updateButtonProps("variant", event.target.value as ButtonVariant)}>
                  {["solid", "pill", "ripple", "cartoon", "outline", "ghost", "subtle", "text", "glass"].map((option) => (
                    <option key={option} value={option}>
                      {humanize(option)}
                    </option>
                  ))}
                </select>
              </ControlGroup>

              <div className="grid gap-sm sm:grid-cols-2">
                <ControlGroup label="Radius">
                  <select className={controlInputClass} value={buttonProps.radius} onChange={(event) => updateButtonProps("radius", event.target.value as Radius)}>
                    {RADIUS_OPTIONS.map((option) => (
                      <option key={option} value={option}>
                        {option}
                      </option>
                    ))}
                  </select>
                </ControlGroup>
                <ControlGroup label="Padding">
                  <select className={controlInputClass} value={buttonProps.padding} onChange={(event) => updateButtonProps("padding", event.target.value as PaddingFormat)}>
                    {OPTIONAL_PADDING_OPTIONS.map((option) => (
                      <option key={option} value={option}>
                        {option}
                      </option>
                    ))}
                  </select>
                </ControlGroup>
              </div>

              <ControlGroup label="ClassName">
                <input className={controlInputClass} type="text" value={buttonProps.className} onChange={(event) => updateButtonProps("className", event.target.value)} />
              </ControlGroup>

              <div className="flex flex-wrap items-center gap-sm">
                <Checkbox size="sm" variant="outline" width="content" labelPlacement="right" isSelected={isDisabled} onChange={setIsDisabled}>
                  Disabled
                </Checkbox>
                <Checkbox size="sm" variant="outline" width="content" labelPlacement="right" isSelected={isReadOnly} onChange={setIsReadOnly}>
                  Read only
                </Checkbox>
                <Checkbox size="sm" variant="outline" width="content" labelPlacement="right" isSelected={isRequired} onChange={setIsRequired}>
                  Required
                </Checkbox>
                <Checkbox size="sm" variant="outline" width="content" labelPlacement="right" isSelected={isInvalid} onChange={setIsInvalid}>
                  Invalid
                </Checkbox>
                <Checkbox size="sm" variant="outline" width="content" labelPlacement="right" isSelected={isLoading} onChange={setIsLoading}>
                  Loading (async)
                </Checkbox>
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

function humanize(value: string) {
  return value
    .replace(/_/g, " ")
    .replace(/-/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}
