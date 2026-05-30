import clsx from "clsx";
import type { BaseWidthMode, BaseTone, BaseVariant } from "../components.styles";

export type ButtonVariant = BaseVariant | "glass" | "cartoon" | "ripple" | "pill";
export type ButtonTone = BaseTone;
export type ButtonWidth = BaseWidthMode | "grow" | "icon";

export const toneRecepies = (variant: ButtonVariant, tone: ButtonTone) => {
  const variantSpecific: Record<ButtonVariant, string> = {
    solid: clsx(
      "shadow-shadow/10",
      "data-[hovered]:brightness-110 group-data-[hovered]/checkbox:brightness-110",
      "data-[pressed]:brightness-90 group-data-[pressed]/checkbox:brightness-90",
      "pending:animate-breathe-loading pending:cursor-wait",
    ),
    pill: clsx(
      "shadow-shadow/10 ",
      "data-[hovered]:brightness-110 group-data-[hovered]/checkbox:brightness-110",
      "data-[pressed]:brightness-90 group-data-[pressed]/checkbox:brightness-90",
      "pending:animate-breathe-loading pending:cursor-wait",
    ),
    ripple: clsx(
      "shadow-shadow/10 overflow-hidden",
      "data-[hovered]:brightness-110 group-data-[hovered]/checkbox:brightness-110",
      "data-[pressed]:brightness-90 group-data-[pressed]/checkbox:brightness-90",
      "pending:animate-breathe-loading pending:cursor-wait",
    ),
    outline: clsx(
      "border-1",
      "data-[hovered]:bg-foreground/5 group-data-[hovered]/checkbox:bg-foreground/5",
      "data-[pressed]:bg-foreground/10 group-data-[pressed]/checkbox:bg-foreground/10",
      "pending:animate-breathe-loading pending:cursor-wait",
    ),
    ghost: clsx(
      "data-[hovered]:bg-foreground/5 group-data-[hovered]/checkbox:bg-foreground/5",
      "data-[pressed]:bg-foreground/10 group-data-[pressed]/checkbox:bg-foreground/10",
      "pending:animate-breathe-loading pending:cursor-wait",
    ),
    subtle: clsx(
      "data-[hovered]:bg-foreground/10 group-data-[hovered]/checkbox:bg-foreground/10",
      "data-[pressed]:bg-foreground/20 group-data-[pressed]/checkbox:bg-foreground/20",
      "pending:animate-breathe-loading pending:cursor-wait",
    ),
    text: clsx(
      "data-[hovered]:underline group-data-[hovered]/checkbox:underline",
      "data-[pressed]:opacity-80 group-data-[pressed]/checkbox:opacity-80",
      "pending:animate-breathe-loading pending:cursor-wait",
    ),
    glass: clsx(
      "border border-divider/40 shadow-[0_4px_30px_rgba(0,0,0,0.1)] backdrop-blur-[2px] overflow-hidden",
      "data-[hovered]:backdrop-blur-[4px] group-data-[hovered]/checkbox:backdrop-blur-[4px]",
      "data-[hovered]:border-white/60 group-data-[hovered]/checkbox:border-white/60",
      "data-[hovered]:shadow-[0_6px_36px_rgba(0,0,0,0.15)] group-data-[hovered]/checkbox:shadow-[0_6px_36px_rgba(0,0,0,0.15)]",
      "data-[pressed]:backdrop-blur-[4px] group-data-[pressed]/checkbox:backdrop-blur-[4px]",
      "pending:animate-breathe-loading pending:cursor-wait",
    ),
    cartoon: clsx(
      "border-[2px] shadow-[3px_3px_0_0_rgba(0,0,0,0.35)]",
      "data-[pressed]:translate-y-[2px] group-data-[pressed]/checkbox:translate-y-[2px]",
      "data-[pressed]:translate-x-[1px] group-data-[pressed]/checkbox:translate-x-[1px] ",
      "data-[pressed]:shadow-none group-data-[pressed]/checkbox:shadow-none",
      "pending:animate-breathe-loading pending:cursor-wait",
    ),
  };

  /** Filled-style tones (solid/pill/ripple/cartoon) */
  const toneFilled: Record<ButtonTone, string> = {
    default: clsx("bg-foreground text-text border-divider", "data-[selected]:ring-divider-500 group-data-[selected]/checkbox:ring-divider-500"),
    primary: clsx("bg-primary text-text border-primary/80", "data-[selected]:ring-primary-500 group-data-[selected]/checkbox:ring-primary-500"),
    secondary: clsx("bg-secondary text-text border-secondary/80", "data-[selected]:ring-secondary-500 group-data-[selected]/checkbox:ring-secondary-500"),
    success: clsx("bg-success text-background border-success/80", "data-[selected]:ring-success-500 group-data-[selected]/checkbox:ring-success-500"),
    warning: clsx("bg-warning text-background border-warning/80", "data-[selected]:ring-warning-500 group-data-[selected]/checkbox:ring-warning-500"),
    error: clsx("bg-error text-background border-error/80", "data-[selected]:ring-error-500 group-data-[selected]/checkbox:ring-error-500"),
    neutral: clsx("bg-neutral text-background border-neutral/80", "data-[selected]:ring-secondary-500 group-data-[selected]/checkbox:ring-secondary-500"),
  };

  /** Ripple-style tones */
  const toneRipple: Record<ButtonTone, string> = {
    default: clsx("bg-foreground text-text border-divider", "data-[selected]:ring-divider-500 group-data-[selected]/checkbox:ring-divider-500"),
    primary: clsx("bg-primary text-background border-primary/80", "data-[selected]:ring-primary-500 group-data-[selected]/checkbox:ring-primary-500"),
    secondary: clsx("bg-secondary text-background border-secondary/80", "data-[selected]:ring-secondary-500 group-data-[selected]/checkbox:ring-secondary-500"),
    success: clsx("bg-success text-background border-success/80", "data-[selected]:ring-success-500 group-data-[selected]/checkbox:ring-success-500"),
    warning: clsx("bg-warning text-background border-warning/80", "data-[selected]:ring-warning-500 group-data-[selected]/checkbox:ring-warning-500"),
    error: clsx("bg-error text-background border-error/80", "data-[selected]:ring-error-500 group-data-[selected]/checkbox:ring-error-500"),
    neutral: clsx("bg-neutral text-background border-neutral/80", "data-[selected]:ring-secondary-500 group-data-[selected]/checkbox:ring-secondary-500"),
  };

  /** Outline-style tones */
  const toneOutline: Record<ButtonTone, string> = {
    default: clsx("bg-transparent text-text border-divider data-[selected]:ring-divider-500 group-data-[selected]/checkbox:ring-divider-500"),
    primary: clsx("bg-transparent text-text border-primary data-[selected]:ring-primary-500 group-data-[selected]/checkbox:ring-primary-500"),
    secondary: clsx("bg-transparent text-secondary border-secondary data-[selected]:ring-secondary-500 group-data-[selected]/checkbox:ring-secondary-500"),
    success: clsx("bg-transparent text-success border-success data-[selected]:ring-success-500 group-data-[selected]/checkbox:ring-success-500"),
    warning: clsx("bg-transparent text-warning border-warning data-[selected]:ring-warning-500 group-data-[selected]/checkbox:ring-warning-500"),
    error: clsx("bg-transparent text-error border-error data-[selected]:ring-error-500 group-data-[selected]/checkbox:ring-error-500"),
    neutral: clsx("bg-transparent text-neutral border-neutral data-[selected]:ring-secondary-500 group-data-[selected]/checkbox:ring-secondary-500"),
  };

  /** Ghost-style tones */
  const toneGhost: Record<ButtonTone, string> = {
    default: clsx("bg-transparent text-text border-transparent data-[selected]:ring-divider-500 group-data-[selected]/checkbox:ring-divider-500"),
    primary: clsx("bg-transparent text-text border-transparent data-[selected]:ring-primary-500 group-data-[selected]/checkbox:ring-primary-500"),
    secondary: clsx("bg-transparent text-secondary border-transparent data-[selected]:ring-secondary-500 group-data-[selected]/checkbox:ring-secondary-500"),
    success: clsx("bg-transparent text-success border-transparent data-[selected]:ring-success-500 group-data-[selected]/checkbox:ring-success-500"),
    warning: clsx("bg-transparent text-warning border-transparent data-[selected]:ring-warning-500 group-data-[selected]/checkbox:ring-warning-500"),
    error: clsx("bg-transparent text-error border-transparent data-[selected]:ring-error-500 group-data-[selected]/checkbox:ring-error-500"),
    neutral: clsx("bg-transparent text-neutral border-transparent data-[selected]:ring-secondary-500 group-data-[selected]/checkbox:ring-secondary-500"),
  };

  /** Subtle-style tones */
  const toneSubtle: Record<ButtonTone, string> = {
    default: clsx("bg-alt-background text-text border-transparent data-[selected]:ring-divider-500 group-data-[selected]/checkbox:ring-divider-500"),
    primary: clsx("bg-primary/10 text-text border-transparent data-[selected]:ring-primary-500 group-data-[selected]/checkbox:ring-primary-500"),
    secondary: clsx("bg-secondary/10 text-secondary border-transparent data-[selected]:ring-secondary-500 group-data-[selected]/checkbox:ring-secondary-500"),
    success: clsx("bg-success/10 text-success border-transparent data-[selected]:ring-success-500 group-data-[selected]/checkbox:ring-success-500"),
    warning: clsx("bg-warning/10 text-warning border-transparent data-[selected]:ring-warning-500 group-data-[selected]/checkbox:ring-warning-500"),
    error: clsx("bg-error/10 text-error border-transparent data-[selected]:ring-error-500 group-data-[selected]/checkbox:ring-error-500"),
    neutral: clsx("bg-neutral/10 text-neutral border-transparent data-[selected]:ring-secondary-500 group-data-[selected]/checkbox:ring-secondary-500"),
  };

  /** Glass-style tones */
  const toneGlass: Record<ButtonTone, string> = {
    default: clsx(
      "bg-white/20 text-text data-[selected]:ring-divider-500 group-data-[selected]/checkbox:ring-divider-500 supports-backdrop-filter:bg-white/20",
      "data-[hovered]:bg-white/30 group-data-[hovered]/checkbox:bg-white/30 supports-backdrop-filter:data-[hovered]:bg-white/30 supports-backdrop-filter:group-data-[hovered]/checkbox:bg-white/30",
    ),
    primary: clsx(
      "bg-primary/20 text-text data-[selected]:ring-primary-500 group-data-[selected]/checkbox:ring-primary-500 supports-backdrop-filter:bg-primary/20",
      "data-[hovered]:bg-primary/30 group-data-[hovered]/checkbox:bg-primary/30 supports-backdrop-filter:data-[hovered]:bg-primary/30 supports-backdrop-filter:group-data-[hovered]/checkbox:bg-primary/30",
    ),
    secondary: clsx(
      "bg-secondary/20 text-secondary data-[selected]:ring-secondary-500 group-data-[selected]/checkbox:ring-secondary-500 supports-backdrop-filter:bg-secondary/20",
      "data-[hovered]:bg-secondary/30 group-data-[hovered]/checkbox:bg-secondary/30 supports-backdrop-filter:data-[hovered]:bg-secondary/30 supports-backdrop-filter:group-data-[hovered]/checkbox:bg-secondary/30",
    ),
    success: clsx(
      "bg-success/20 text-success data-[selected]:ring-success-500 group-data-[selected]/checkbox:ring-success-500 supports-backdrop-filter:bg-success/20",
      "data-[hovered]:bg-success/30 group-data-[hovered]/checkbox:bg-success/30 supports-backdrop-filter:data-[hovered]:bg-success/30 supports-backdrop-filter:group-data-[hovered]/checkbox:bg-success/30",
    ),
    warning: clsx(
      "bg-warning/20 text-warning data-[selected]:ring-warning-500 group-data-[selected]/checkbox:ring-warning-500 supports-backdrop-filter:bg-warning/20",
      "data-[hovered]:bg-warning/30 group-data-[hovered]/checkbox:bg-warning/30 supports-backdrop-filter:data-[hovered]:bg-warning/30 supports-backdrop-filter:group-data-[hovered]/checkbox:bg-warning/30",
    ),
    error: clsx(
      "bg-error/20 text-error data-[selected]:ring-error-500 group-data-[selected]/checkbox:ring-error-500 supports-backdrop-filter:bg-error/20",
      "data-[hovered]:bg-error/30 group-data-[hovered]/checkbox:bg-error/30 supports-backdrop-filter:data-[hovered]:bg-error/30 supports-backdrop-filter:group-data-[hovered]/checkbox:bg-error/30",
    ),
    neutral: clsx(
      "bg-neutral/20 text-neutral data-[selected]:ring-secondary-500 group-data-[selected]/checkbox:ring-secondary-500 supports-backdrop-filter:bg-neutral/20",
      "data-[hovered]:bg-neutral/30 group-data-[hovered]/checkbox:bg-neutral/30 supports-backdrop-filter:data-[hovered]:bg-neutral/30 supports-backdrop-filter:group-data-[hovered]/checkbox:bg-neutral/30",
    ),
  };

  /** Text-style tones */
  const toneText: Record<ButtonTone, string> = {
    default: clsx("bg-transparent text-text border-transparent data-[selected]:ring-divider-500 group-data-[selected]/checkbox:ring-divider-500"),
    primary: clsx("bg-transparent text-primary border-transparent data-[selected]:ring-primary-500 group-data-[selected]/checkbox:ring-primary-500"),
    secondary: clsx("bg-transparent text-secondary border-transparent data-[selected]:ring-secondary-500 group-data-[selected]/checkbox:ring-secondary-500"),
    success: clsx("bg-transparent text-success border-transparent data-[selected]:ring-success-500 group-data-[selected]/checkbox:ring-success-500"),
    warning: clsx("bg-transparent text-warning border-transparent data-[selected]:ring-warning-500 group-data-[selected]/checkbox:ring-warning-500"),
    error: clsx("bg-transparent text-error border-transparent data-[selected]:ring-error-500 group-data-[selected]/checkbox:ring-error-500"),
    neutral: clsx("bg-transparent text-neutral border-transparent data-[selected]:ring-secondary-500 group-data-[selected]/checkbox:ring-secondary-500"),
  };

  const tones: Record<ButtonVariant, Record<ButtonTone, string>> = {
    solid: toneFilled,
    pill: toneFilled,
    ripple: toneRipple,
    cartoon: toneFilled,
    outline: toneOutline,
    ghost: toneGhost,
    subtle: toneSubtle,
    glass: toneGlass,
    text: toneText,
  };

  return `${variantSpecific[variant]} ${tones[variant][tone]}`;
};

export function widthToClass(width: ButtonWidth, iconOnly: boolean): string {
  if (iconOnly) return "aspect-square overflow-hidden w-fit h-fit";

  switch (width) {
    case "full":
      return "w-full";
    case "grow":
      return "w-full flex-1";
    case "icon":
      return "aspect-square overflow-hidden w-fit h-fit";
    case "content":
    default:
      return "w-fit";
  }
}
