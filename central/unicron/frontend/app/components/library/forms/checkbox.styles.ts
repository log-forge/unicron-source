import clsx from "clsx";
import { type CheckboxProps as RaCheckboxProps, type ValidationResult } from "react-aria-components";
import type { ButtonVariant } from "../buttons/button.styles";
import type { BaseStatus, BaseTone, BaseWidthMode, PaddingFormat, RadiusFormat } from "../components.styles";
import type { ReactNode } from "react";

export type CheckboxVariant = ButtonVariant;
export type CheckboxTone = BaseTone;
export type CheckboxWidth = BaseWidthMode;
export type CheckboxStatus = BaseStatus;
export type CheckboxLabelPlacement = "left" | "right" | "top" | "bottom";

export type BaseCheckboxProps = {
  label?: string;
  variant?: CheckboxVariant;
  tone?: CheckboxTone;
  status?: BaseStatus;
  size?: FontSize;
  width?: CheckboxWidth;
  labelPlacement?: CheckboxLabelPlacement;
  padding?: PaddingFormat;
  radius?: RadiusFormat;
  gap?: Spacing;
  messageGap?: Spacing;
  labelTextSize?: FontSize;
  messageTextSize?: FontSize;
  doesStatusEffectLabel?: boolean;
  doesStatusEffectDescription?: boolean;
  description?: string;
  errorMessage?: string | ((validation: ValidationResult) => string);
  className?: string;
  controlClassName?: string;
  inputClassName?: string;
  labelClassName?: string;
  descriptionClassName?: string;
  messageClassName?: string;
};

export type CheckboxProps = BaseCheckboxProps &
  Omit<RaCheckboxProps, keyof BaseCheckboxProps | "className" | "children"> & {
    children?: ReactNode;
  };

const labelTone: Record<CheckboxTone, string> = {
  default: "text-text",
  primary: "text-primary",
  secondary: "text-secondary",
  success: "text-success-text",
  warning: "text-warning-text",
  error: "text-error-text",
  neutral: "text-neutral-text",
};

const descriptionTone: Record<CheckboxTone, string> = {
  default: "text-neutral-text/80",
  primary: "text-neutral-text/80",
  secondary: "text-neutral-text/80",
  success: "text-success-text",
  warning: "text-warning-text",
  error: "text-error-text",
  neutral: "text-neutral-text/80",
};

const messageTone: Record<CheckboxTone, string> = {
  default: "",
  primary: "",
  secondary: "",
  success: "text-success-text",
  warning: "text-warning-text",
  error: "text-error-text",
  neutral: "",
};

const focusRingTone: Record<CheckboxTone, string> = {
  default: "ring-primary-500",
  primary: "ring-primary-500",
  secondary: "ring-secondary-500",
  success: "ring-success-500",
  warning: "ring-warning-500",
  error: "ring-error-500",
  neutral: "ring-neutral-500",
};

export function toneRecepies(_variant: CheckboxVariant, tone: CheckboxTone) {
  return {
    wrapper: clsx("text-text", "transition-[color,background,box-shadow] duration-150 ease-out"),
    control: clsx("transition-[filter,transform,box-shadow,border-color] duration-150 ease-out"),
    label: labelTone[tone],
    description: descriptionTone[tone],
    message: clsx("transition-colors duration-150 ease-out", messageTone[tone]),
    focusRing: clsx("ring-2 ring-offset-2 ring-offset-background", focusRingTone[tone]),
  };
}

export function labelPlacementToClass(labelPlacement: CheckboxLabelPlacement) {
  switch (labelPlacement) {
    case "left":
      return "flex-row-reverse items-center justify-start text-left";
    case "top":
      return "flex-col-reverse items-start justify-start text-left";
    case "bottom":
      return "flex-col items-start justify-start text-left";
    case "right":
    default:
      return "flex-row items-start justify-start text-left";
  }
}
