import type { ComboBoxProps as RaComboBoxProps, ValidationResult } from "react-aria-components";
import type { ReactNode } from "react";
import type { BaseStatus, BaseTone, BaseVariant, BaseWidthMode, PaddingFormat, RadiusFormat } from "../../components.styles";
import type { InputProps } from "../../forms/Input";
import type { UiButtonModeButtonProps } from "../../buttons/Button";
import clsx from "clsx";
import type { FieldVariant } from "../../forms/fields/text-field.styles";

/* -------------------------------------------------------------------------- */
/* Visual tokens                                                              */
/* -------------------------------------------------------------------------- */

export type ComboBoxVariant = FieldVariant;
export type PopoverVariant = "solid" | "outline" | "ghost" | "subtle";
export type ComboBoxTone = BaseTone;
export type ComboBoxStatus = BaseStatus;
export type ComboBoxWidth = BaseWidthMode;

/** Props we don't want the consumer to override on the child Input/Button */
type OmittedChildVisualProps = "tone" | "status" | "textSize" | "isDisabled" | "isReadOnly" | "isRequired" | "isInvalid";

/** Props forwarded into the inner Input (minus visual ownership props + width/disabled/readOnly/required) */
export type ComboBoxInputProps = Omit<InputProps, OmittedChildVisualProps | "width" | "radius" | "name">;

/** Props forwarded into the trigger Button (minus visual ownership props + mode/width/iconOnly) */
export type ComboBoxButtonProps = Omit<UiButtonModeButtonProps, OmittedChildVisualProps | "mode" | "width" | "iconOnly">;

/* -------------------------------------------------------------------------- */
/* Public ComboBox props                                                      */
/* -------------------------------------------------------------------------- */

export interface ComboBoxProps<T extends object> extends Omit<RaComboBoxProps<T>, "children"> {
  /* ----- Visual recipe for the overall field -------------------------------- */

  /** Visual style recipe for the field */
  variant?: ComboBoxVariant;
  /** Visual style recipe for the Popover */
  popoverVariant?: PopoverVariant;
  /** Base color tone (mapped via status if needed) */
  tone?: ComboBoxTone;
  /** Status state (can map to tone) */
  status?: ComboBoxStatus;
  /** Width behavior of the field */
  width?: ComboBoxWidth;

  /** Radius for the main control (input/button cluster) */
  radius?: RadiusFormat;
  /** Radius for the Popover surface */
  popoverRadius?: RadiusFormat;

  /** Padding for the main control */
  padding?: PaddingFormat;
  /** Padding for the Popover surface */
  popoverPadding?: PaddingFormat;

  /** Gap between input and button */
  gap?: string;
  /** Gap between label and input */
  labelGap?: string;
  /** Gap between description/error message and input */
  messageGap?: string;
  /** Gap between list box items */
  listBoxGap?: string;

  /** Text size for the input text, button icon, etc. */
  textSize?: FontSize;
  /** Text size for the label */
  labelTextSize?: FontSize;
  /** Text size for description + error message */
  messageTextSize?: FontSize;

  /** Whether status (error/warning/success) should affect the input tone */
  doesStatusEffectInput?: boolean;
  /** Whether status (error/warning/success) should affect the label tone */
  doesStatusEffectLabel?: boolean;
  /** Whether status should affect the description tone */
  doesStatusEffectDescription?: boolean;

  /** Extra className overrides for internal slots */
  popoverClassName?: string;
  listBoxClassName?: string;
  labelClassName?: string;
  descriptionClassName?: string;
  messageClassName?: string;

  /* ----- Field content ----------------------------------------------------- */

  /** Simple string label (mapped to React Aria label under the hood) */
  label?: string;
  /** Optional description text under the field */
  description?: string | null;
  /** Static or validation-based error message text */
  errorMessage?: string | ((validation: ValidationResult) => string);

  /**
   * Collection content:
   *  - Static children (ListBoxItem elements)
   *  - Or a render function receiving each item from `items`
   */
  children: ReactNode | ((item: T) => ReactNode);

  /* ----- Slot props for inner Input + Button -------------------------------- */

  /** Extra props forwarded to the inner Input (non-visual ownership props) */
  inputProps?: ComboBoxInputProps;
  /** Extra props forwarded to the trigger Button (non-visual ownership props) */
  buttonProps?: ComboBoxButtonProps;
}

const labelTone: Record<ComboBoxTone, string> = {
  default: "text-text",
  primary: "text-primary",
  secondary: "text-secondary",
  success: "text-success-text",
  warning: "text-warning-text",
  error: "text-error-text",
  neutral: "text-neutral-text",
};

const descriptionTone: Record<ComboBoxTone, string> = {
  default: "text-neutral-text/80",
  primary: "text-neutral-text/80",
  secondary: "text-neutral-text/80",
  success: "text-success-text",
  warning: "text-warning-text",
  error: "text-error-text",
  neutral: "text-neutral-text/80",
};

const fieldErrorTone: Record<ComboBoxTone, string> = {
  default: "text-error",
  primary: "text-error",
  secondary: "text-error",
  success: "text-success-text",
  warning: "text-warning-text",
  error: "text-error-text",
  neutral: "text-error",
};

const popoverTone: Record<ComboBoxTone, string> = {
  default: "border-divider/20 shadow-divider bg-background text-text focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary-500 focus-visible:outline-none",
  primary: "border-primary/20 shadow-primary bg-background text-text focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary-500 focus-visible:outline-none",
  secondary: "border-secondary/70 bg-background text-text focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-secondary-500 focus-visible:outline-none",
  success: "border-success/70 bg-background text-success focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-success-500 focus-visible:outline-none",
  warning: "border-warning/70 bg-background text-warning focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-warning-500 focus-visible:outline-none",
  error: "border-error/70 bg-background text-error focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-error-500 focus-visible:outline-none",
  neutral: "border-neutral/70 bg-background text-neutral focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-secondary-500 focus-visible:outline-none",
};

const listBoxTone: Record<ComboBoxTone, string> = {
  default: "text-text",
  primary: "text-text",
  secondary: "text-text",
  success: "text-success",
  warning: "text-warning",
  error: "text-error",
  neutral: "text-neutral",
};

const popoverVariantBase: Record<PopoverVariant, string> = {
  solid: "shadow-sm border",
  outline: "border shadow-lg",
  ghost: "shadow-lg backdrop-blur-[2px] bg-background/90",
  subtle: "shadow-lg bg-alt-background/80",
};

const popoverSizeBase = "min-w-[var(--trigger-width)] max-w-[min(28rem,calc(100vw-2rem))]";
const popoverAnimationBase = "animate-cb-popover will-change-[transform,opacity]";

const variantBase: Record<ComboBoxVariant, { wrapper: string; label: string; controlWrapper: string; description: string; fieldError: string }> = {
  stacked: {
    wrapper: "flex flex-col items-start justify-start",
    label: "basis-full",
    controlWrapper: "basis-full w-full",
    description: "basis-full",
    fieldError: "basis-full",
  },
  inline: {
    wrapper: "grid grid-cols-[auto_minmax(0,_1fr)] auto-rows-auto items-start",
    label: "col-start-1 row-start-1 justify-self-start",
    controlWrapper: "col-start-2 row-start-1 w-full min-w-0",
    description: "col-span-2 row-start-2",
    fieldError: "col-span-2 row-start-3",
  },
  floating: {
    wrapper: "relative flex flex-col items-start justify-start",
    label: clsx(
      "absolute top-1/2 -translate-y-1/2 left-0 m-0! origin-left",
      "peer-focus-within/input:animate-[float-label_0.15s_ease-out_forwards] peer-data-[has-value=true]/input:animate-[float-label_0.15s_ease-out_forwards]",
    ),
    controlWrapper: "relative w-full",
    description: "",
    fieldError: "",
  },
  nested_floating: {
    wrapper: "relative flex flex-col items-start justify-start",
    label: clsx(
      "absolute top-1/2 -translate-y-1/2 left-0 m-0! origin-left",
      "peer-focus-within/input:top-0 peer-data-[has-value=true]/input:top-0",
      "peer-focus-within/input:-translate-y-1 peer-data-[has-value=true]/input:-translate-y-1",
      "peer-focus-within/input:scale-80 peer-data-[has-value=true]/input:scale-80",
    ),
    controlWrapper: "relative w-full",
    description: "",
    fieldError: "",
  },
};

export function toneRecepies(variant: ComboBoxVariant, tone: ComboBoxTone, popoverVariant: PopoverVariant) {
  return {
    wrapper: clsx("flex w-full flex-col gap-1", variantBase[variant].wrapper),
    controlWrapper: clsx(variantBase[variant].controlWrapper),
    inputWrapper: clsx(),
    input: clsx(
      (variant === "floating" || variant === "nested_floating") && "placeholder-transparent!",
      variant === "nested_floating" && ["focus-within:translate-y-1/4", "data-[has-value=true]:translate-y-1/4"],
    ),
    buttonWrapper: clsx(),
    button: clsx(),
    popover: clsx(popoverSizeBase, popoverVariantBase[popoverVariant], popoverTone[tone], popoverAnimationBase),
    listBox: clsx("overflow-auto", listBoxTone[tone]),
    label: clsx(labelTone[tone], variantBase[variant].label),
    description: clsx(descriptionTone[tone], variantBase[variant].description),
    fieldError: clsx(fieldErrorTone[tone], variantBase[variant].fieldError),
  };
}
