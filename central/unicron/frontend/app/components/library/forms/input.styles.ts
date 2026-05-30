import clsx from "clsx";
import type { BaseStatus, BaseTone, BaseVariant, BaseWidthMode } from "../components.styles";

export type InputVariant = BaseVariant | "underline";
export type InputTone = BaseTone;
export type InputWidth = BaseWidthMode;
export type InputStatus = BaseStatus;

const focusRingMap: Record<InputTone, string> = {
  default: "focus-within:ring-2 focus-within:ring-primary-500 focus-within:ring-offset-1 focus-within:ring-offset-background",
  primary: "focus-within:ring-2 focus-within:ring-primary-500 focus-within:ring-offset-1 focus-within:ring-offset-background",
  secondary: "focus-within:ring-2 focus-within:ring-secondary-500 focus-within:ring-offset-1 focus-within:ring-offset-background",
  success: "focus-within:ring-2 focus-within:ring-success-500 focus-within:ring-offset-1 focus-within:ring-offset-background",
  warning: "focus-within:ring-2 focus-within:ring-warning-500 focus-within:ring-offset-1 focus-within:ring-offset-background",
  error: "focus-within:ring-2 focus-within:ring-error-500 focus-within:ring-offset-1 focus-within:ring-offset-background",
  neutral: "focus-within:ring-2 focus-within:ring-neutral-500 focus-within:ring-offset-1 focus-within:ring-offset-background",
};

const wrapperVariantBase: Record<InputVariant, string> = {
  solid: "border-0 shadow-sm",
  outline: "border bg-transparent shadow-sm",
  ghost: "border border-transparent bg-foreground/10",
  subtle: "border border-transparent bg-alt-background/60 shadow-inner",
  text: "border-0 border-b bg-transparent shadow-none focus-within:ring-0 focus-within:ring-offset-0",
  underline: "border-0 border-b bg-transparent shadow-none focus-within:ring-0 focus-within:ring-offset-0",
};

const inputVariantBase: Record<InputVariant, string> = {
  solid: "border-0 bg-transparent",
  outline: "border-0 bg-transparent",
  ghost: "border-0 bg-transparent",
  subtle: "border-0 bg-transparent",
  text: "border-0 bg-transparent px-0",
  underline: "border-0 bg-transparent px-0",
};

const wrapperToneFilled: Record<InputTone, string> = {
  default: clsx("border-divider/60 bg-foreground/60 text-text", focusRingMap.default),
  primary: clsx("border-primary/70 bg-primary/10 text-text", focusRingMap.primary),
  secondary: clsx("border-secondary/70 bg-secondary/10 text-text", focusRingMap.secondary),
  success: clsx("border-success/70 bg-success/10 text-success", focusRingMap.success),
  warning: clsx("border-warning/70 bg-warning/10 text-warning", focusRingMap.warning),
  error: clsx("border-error/70 bg-error/10 text-error", focusRingMap.error),
  neutral: clsx("border-neutral/70 bg-neutral/10 text-neutral", focusRingMap.neutral),
};

const inputToneFilled: Record<InputTone, string> = {
  default: "text-text placeholder:text-neutral/50",
  primary: "text-text placeholder:text-primary/70",
  secondary: "text-text placeholder:text-secondary/70",
  success: "text-success placeholder:text-success/70",
  warning: "text-warning placeholder:text-warning/70",
  error: "text-error placeholder:text-error/70",
  neutral: "text-neutral placeholder:text-neutral/70",
};

const wrapperToneOutline: Record<InputTone, string> = {
  default: clsx("border-divider text-text", focusRingMap.default),
  primary: clsx("border-primary text-primary", focusRingMap.primary),
  secondary: clsx("border-secondary text-secondary", focusRingMap.secondary),
  success: clsx("border-success text-success", focusRingMap.success),
  warning: clsx("border-warning text-warning", focusRingMap.warning),
  error: clsx("border-error text-error", focusRingMap.error),
  neutral: clsx("border-neutral text-neutral", focusRingMap.neutral),
};

const inputToneOutline: Record<InputTone, string> = {
  default: "text-text placeholder:text-text/60",
  primary: "text-primary placeholder:text-primary/70",
  secondary: "text-secondary placeholder:text-secondary/70",
  success: "text-success placeholder:text-success/70",
  warning: "text-warning placeholder:text-warning/70",
  error: "text-error placeholder:text-error/70",
  neutral: "text-neutral placeholder:text-neutral/70",
};

const wrapperToneGhost: Record<InputTone, string> = {
  default: clsx("text-text", focusRingMap.default),
  primary: clsx("text-primary", focusRingMap.primary),
  secondary: clsx("text-secondary", focusRingMap.secondary),
  success: clsx("text-success", focusRingMap.success),
  warning: clsx("text-warning", focusRingMap.warning),
  error: clsx("text-error", focusRingMap.error),
  neutral: clsx("text-neutral", focusRingMap.neutral),
};

const inputToneGhost: Record<InputTone, string> = {
  default: "text-text placeholder:text-text/70",
  primary: "text-primary placeholder:text-primary/70",
  secondary: "text-secondary placeholder:text-secondary/70",
  success: "text-success placeholder:text-success/70",
  warning: "text-warning placeholder:text-warning/70",
  error: "text-error placeholder:text-error/70",
  neutral: "text-neutral placeholder:text-neutral/70",
};

const wrapperToneSubtle: Record<InputTone, string> = {
  default: clsx("text-text bg-alt-background/40", focusRingMap.default),
  primary: clsx("text-primary bg-primary/5", focusRingMap.primary),
  secondary: clsx("text-secondary bg-secondary/5", focusRingMap.secondary),
  success: clsx("text-success bg-success/5", focusRingMap.success),
  warning: clsx("text-warning bg-warning/5", focusRingMap.warning),
  error: clsx("text-error bg-error/5", focusRingMap.error),
  neutral: clsx("text-neutral bg-neutral/5", focusRingMap.neutral),
};

const inputToneSubtle: Record<InputTone, string> = {
  default: "text-text placeholder:text-text/60",
  primary: "text-primary placeholder:text-primary/70",
  secondary: "text-secondary placeholder:text-secondary/70",
  success: "text-success placeholder:text-success/70",
  warning: "text-warning placeholder:text-warning/70",
  error: "text-error placeholder:text-error/70",
  neutral: "text-neutral placeholder:text-neutral/70",
};

const wrapperToneMinimal: Record<InputTone, string> = {
  default: clsx("border-b-divider text-text", focusRingMap.default),
  primary: clsx("border-b-primary text-primary", focusRingMap.primary),
  secondary: clsx("border-b-secondary text-secondary", focusRingMap.secondary),
  success: clsx("border-b-success text-success", focusRingMap.success),
  warning: clsx("border-b-warning text-warning", focusRingMap.warning),
  error: clsx("border-b-error text-error", focusRingMap.error),
  neutral: clsx("border-b-neutral text-neutral", focusRingMap.neutral),
};

const inputToneMinimal: Record<InputTone, string> = {
  default: "text-text placeholder:text-text/60",
  primary: "text-primary placeholder:text-primary/70",
  secondary: "text-secondary placeholder:text-secondary/70",
  success: "text-success placeholder:text-success/70",
  warning: "text-warning placeholder:text-warning/70",
  error: "text-error placeholder:text-error/70",
  neutral: "text-neutral placeholder:text-neutral/70",
};

const wrapperTonePalette: Record<InputVariant, Record<InputTone, string>> = {
  solid: wrapperToneFilled,
  outline: wrapperToneOutline,
  ghost: wrapperToneGhost,
  subtle: wrapperToneSubtle,
  text: wrapperToneMinimal,
  underline: wrapperToneMinimal,
};

const inputTonePalette: Record<InputVariant, Record<InputTone, string>> = {
  solid: inputToneFilled,
  outline: inputToneOutline,
  ghost: inputToneGhost,
  subtle: inputToneSubtle,
  text: inputToneMinimal,
  underline: inputToneMinimal,
};

export const toneRecepies = (variant: InputVariant, tone: InputTone) => {
  return {
    wrapper: clsx(wrapperVariantBase[variant], wrapperTonePalette[variant][tone]),
    input: clsx(inputVariantBase[variant], inputTonePalette[variant][tone]),
  };
};

export function widthToClass(width: InputWidth): string {
  switch (width) {
    case "full":
      return "w-full";
    case "content":
    default:
      return "w-fit";
  }
}
