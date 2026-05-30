import clsx from "clsx";
import type { BaseTone, BaseWidthMode, PaddingFormat, RadiusFormat } from "../../components.styles";
import type { InputProps } from "../Input";
import type { NumberFieldProps as RaNumberFieldProps, ValidationResult } from "react-aria-components";
import type { UiButtonModeButtonProps } from "../../buttons/Button";
import type { FieldStatus, FieldTone, FieldVariant, FieldWidth } from "./text-field.styles";
export type StepperPosition = "right-stacked" | "right-inline" | "left-stacked" | "left-inline" | "split";

/** Props we don't want the consumer to override on the child Input/Button */
type OmittedChildVisualProps = "tone" | "status" | "textSize" | "isDisabled" | "isReadOnly" | "isRequired" | "isInvalid";

/** Props forwarded into the inner Input (minus visual ownership props + width/disabled/readOnly/required) */
export type NumberFieldInputProps = Omit<InputProps, OmittedChildVisualProps | "width" | "radius" | "name">;

/** Props forwarded into the trigger Button (minus visual ownership props + mode/width/iconOnly) */
export type NumberFieldButtonProps = Omit<UiButtonModeButtonProps, OmittedChildVisualProps | "mode" | "width" | "iconOnly">;

/* -------------------------------------------------------------------------- */
/* Public NumberField props                                                      */
/* -------------------------------------------------------------------------- */

export interface NumberFieldProps extends Omit<RaNumberFieldProps, "className"> {
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
  /** Where the increment/decrement stepper should render */
  stepperPosition?: StepperPosition;
  /** Extra left padding reserved when a stepper sits on the left */
  stepperStartPadding?: Spacing | 0;
  /** Extra right padding reserved when a stepper sits on the right */
  stepperEndPadding?: Spacing | 0;

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
  inputProps?: NumberFieldInputProps;
  /** Extra props forwarded to the trigger Button (non-visual ownership props) */
  buttonProps?: NumberFieldButtonProps;
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

type StepperPlacementConfig = {
  primaryWrapper: string;
  primaryDirection: "vertical" | "horizontal";
  secondaryWrapper?: string;
  secondaryDirection?: "vertical" | "horizontal";
};

const stepperPlacementBase: Record<StepperPosition, StepperPlacementConfig> = {
  "right-stacked": {
    primaryWrapper: "absolute inset-y-0 right-0 flex min-h-0 min-w-0 items-center justify-center",
    primaryDirection: "vertical",
  },
  "right-inline": {
    primaryWrapper: "absolute inset-y-0 right-0 flex min-h-0 min-w-0 items-center justify-center",
    primaryDirection: "horizontal",
  },
  "left-stacked": {
    primaryWrapper: "absolute inset-y-0 left-0 flex min-h-0 min-w-0 items-center justify-center",
    primaryDirection: "vertical",
  },
  "left-inline": {
    primaryWrapper: "absolute inset-y-0 left-0 flex min-h-0 min-w-0 items-center justify-center",
    primaryDirection: "horizontal",
  },
  split: {
    primaryWrapper: "absolute inset-y-0 left-0 flex min-h-0 min-w-0 items-center justify-center",
    primaryDirection: "horizontal",
    secondaryWrapper: "absolute inset-y-0 right-0 flex min-h-0 min-w-0 items-center justify-center",
    secondaryDirection: "horizontal",
  },
};

export function stepperPlacementRecipes(position: StepperPosition): StepperPlacementConfig {
  return stepperPlacementBase[position];
}

export function classRecepies(variant: FieldVariant, tone: FieldTone, stepperPosition: StepperPosition) {
  const placement = stepperPlacementBase[stepperPosition];
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
    buttonWrapper: clsx(placement.primaryWrapper, variantBase[variant].buttonWrapper),
    buttonDirection: placement.primaryDirection,
    secondaryButtonWrapper: clsx(placement.secondaryWrapper ?? "", variantBase[variant].buttonWrapper),
    secondaryButtonDirection: placement.secondaryDirection,
    button: clsx(variantBase[variant].button),
    description: clsx(descriptionTone[tone], variantBase[variant].description),
    fieldError: clsx(fieldErrorTone[tone], variantBase[variant].fieldError),
  };
}
