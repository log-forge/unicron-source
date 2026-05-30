import clsx from "clsx";
import type { BaseStatus, BaseTone, BaseWidthMode, PaddingFormat, RadiusFormat } from "../../components.styles";
import type { InputProps } from "../Input";
import type { TextFieldProps as RaTextFieldProps, ValidationResult } from "react-aria-components";
import type { UiButtonModeButtonProps } from "../../buttons/Button";

/* -------------------------------------------------------------------------- */
/* Visual tokens                                                              */
/* -------------------------------------------------------------------------- */

export type FieldVariant = "stacked" | "inline" | "nested_floating" | "floating";
export type FieldTone = BaseTone;
export type FieldStatus = BaseStatus;
export type FieldWidth = BaseWidthMode;

/** Props we don't want the consumer to override on the child Input/Button */
type OmittedChildVisualProps = "tone" | "status" | "textSize" | "isDisabled" | "isReadOnly" | "isRequired" | "isInvalid";

/** Props forwarded into the inner Input (minus visual ownership props + width/disabled/readOnly/required) */
export type TextFieldInputProps = Omit<InputProps, OmittedChildVisualProps | "width" | "radius" | "name">;

/** Props forwarded into the trigger Button (minus visual ownership props + mode/width/iconOnly) */
export type TextFieldButtonProps = Omit<UiButtonModeButtonProps, OmittedChildVisualProps | "mode" | "width" | "iconOnly">;

/* -------------------------------------------------------------------------- */
/* Public TextField props                                                      */
/* -------------------------------------------------------------------------- */

export interface TextFieldProps extends Omit<RaTextFieldProps, "className"> {
  /* ----- Visual recipe for the overall field -------------------------------- */

  /** Visual style recipe for the field */
  variant?: FieldVariant;
  /** Base color tone (mapped via status if needed) */
  tone?: FieldTone;
  /** Status state (can map to tone) */
  status?: FieldStatus;
  /** Width behavior of the field */
  width?: FieldWidth;
  /** Radius for the main control (input/button cluster) */
  radius?: RadiusFormat;
  /** Padding for the main control */
  padding?: PaddingFormat;

  /** Gap between input and button */
  gap?: Spacing;
  /** Gap between label and input */
  labelGap?: Spacing;
  /** Gap between description/error message and input */
  messageGap?: Spacing;

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
  className?: string;
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

  /* ----- Slot props for inner Input + Button -------------------------------- */

  /** Extra props forwarded to the inner Input (non-visual ownership props) */
  inputProps?: TextFieldInputProps;
  /** Extra props forwarded to the trigger Button (non-visual ownership props) */
  buttonProps?: TextFieldButtonProps;
}

const variantBase = {
  stacked: {
    textField: "flex flex-col items-start justify-start",
    label: "basis-full",
    inputWrapper: "basis-full w-full",
    input: "",
    buttonWrapper: "",
    button: "",
    description: "basis-full",
    fieldError: "basis-full",
  },
  inline: {
    textField: "grid grid-cols-[auto_minmax(0,_1fr)] auto-rows-auto items-start",
    label: "col-start-1 row-start-1 justify-self-start leading-heading",
    inputWrapper: "col-start-2 row-start-1 w-full min-w-0",
    input: "",
    buttonWrapper: "",
    button: "",
    description: "col-span-2 row-start-2",
    fieldError: "col-span-2 row-start-3",
  },
  floating: {
    textField: "relative flex flex-col items-start justify-start",
    label: clsx(
      "absolute top-1/2 -translate-y-1/2 left-0 m-0!",
      "origin-left",
      "peer-focus-within/input:animate-[float-label_0.15s_ease-out_forwards] peer-data-[has-value=true]/input:animate-[float-label_0.15s_ease-out_forwards]",
    ),
    inputWrapper: "relative w-full",
    input: "placeholder-transparent!",
    buttonWrapper: "",
    button: "",
    description: "basis-full",
    fieldError: "basis-full",
  },
  nested_floating: {
    textField: "relative flex flex-col items-start justify-start",
    label: clsx(
      "absolute top-1/2 -translate-y-1/2 left-0 m-0!",
      "origin-left",
      "peer-focus-within/input:top-0 peer-data-[has-value=true]/input:top-0",
      "peer-focus-within/input:-translate-y-1 peer-data-[has-value=true]/input:-translate-y-1",
      "peer-focus-within/input:scale-80 peer-data-[has-value=true]/input:scale-80",
    ),
    inputWrapper: "relative w-full",
    input: clsx("placeholder-transparent!", "focus-within:translate-y-1/4", "data-[has-value=true]:translate-y-1/4"),
    buttonWrapper: "",
    button: "",
    description: "basis-full",
    fieldError: "basis-full",
  },
};

export function classRecepies(variant: FieldVariant, tone: FieldTone) {
  const labelTone: Record<FieldTone, string> = {
    default: "text-text",
    primary: "text-text",
    secondary: "text-text",
    success: "text-text",
    warning: "text-text",
    error: "text-text",
    neutral: "text-text",
  };
  const descriptionTone: Record<FieldTone, string> = {
    default: "text-neutral-text/80",
    primary: "text-neutral-text/80",
    secondary: "text-neutral-text/80",
    success: "text-success-text",
    warning: "text-warning-text",
    error: "text-error-text",
    neutral: "text-neutral-text/80",
  };
  const fieldErrorTone: Record<FieldTone, string> = {
    default: "text-error",
    primary: "text-error",
    secondary: "text-error",
    success: "text-success-text",
    warning: "text-warning-text",
    error: "text-error-text",
    neutral: "text-error",
  };

  return {
    textField: clsx("relative", variantBase[variant].textField),
    label: clsx(labelTone[tone], variantBase[variant].label),
    inputWrapper: clsx(variantBase[variant].inputWrapper),
    input: clsx(variantBase[variant].input),
    buttonWrapper: clsx("absolute inset-y-0 right-0 flex min-h-0 min-w-0 items-center justify-center", variantBase[variant].buttonWrapper),
    button: clsx(variantBase[variant].button),
    description: clsx(descriptionTone[tone], variantBase[variant].description),
    fieldError: clsx(fieldErrorTone[tone], variantBase[variant].fieldError),
  };
}
