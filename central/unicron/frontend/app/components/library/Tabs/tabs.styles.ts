import clsx from "clsx";
import type { BaseTone } from "../components.styles";

export type TabsVariant = "underline" | "text" | "pill" | "subtle" | "solid";
export type TabsTone = BaseTone;

const focusVisibleBase = "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-offset-background";

const toneRingColor: Record<TabsTone, string> = {
  default: "focus-visible:ring-divider-500",
  primary: "focus-visible:ring-primary-500",
  secondary: "focus-visible:ring-secondary-500",
  success: "focus-visible:ring-success-500",
  warning: "focus-visible:ring-warning-500",
  error: "focus-visible:ring-error-500",
  neutral: "focus-visible:ring-secondary-500",
};

const underlineRecipes: Record<TabsTone, string> = {
  default: clsx("text-text", "font-normal", "data-[hovered]:text-text/80", "data-[pressed]:text-text/70", "data-[selected]:text-text", focusVisibleBase, toneRingColor.default),
  primary: clsx(
    "text-text",
    "font-normal",
    "data-[hovered]:text-primary/90",
    "data-[pressed]:text-primary/80",
    "data-[selected]:text-primary",
    focusVisibleBase,
    toneRingColor.primary,
  ),
  secondary: clsx(
    "text-secondary",
    "font-normal",
    "data-[hovered]:text-secondary/90",
    "data-[pressed]:text-secondary/80",
    "data-[selected]:text-secondary",
    focusVisibleBase,
    toneRingColor.secondary,
  ),
  success: clsx(
    "text-success",
    "font-normal",
    "data-[hovered]:text-success/90",
    "data-[pressed]:text-success/80",
    "data-[selected]:text-success",
    focusVisibleBase,
    toneRingColor.success,
  ),
  warning: clsx(
    "text-warning",
    "font-normal",
    "data-[hovered]:text-warning/90",
    "data-[pressed]:text-warning/80",
    "data-[selected]:text-warning",
    focusVisibleBase,
    toneRingColor.warning,
  ),
  error: clsx("text-error", "font-normal", "data-[hovered]:text-error/90", "data-[pressed]:text-error/80", "data-[selected]:text-error", focusVisibleBase, toneRingColor.error),
  neutral: clsx(
    "text-neutral",
    "font-normal",
    "data-[hovered]:text-neutral/90",
    "data-[pressed]:text-neutral/80",
    "data-[selected]:text-neutral",
    focusVisibleBase,
    toneRingColor.neutral,
  ),
};

const textRecipes: Record<TabsTone, string> = {
  default: clsx("text-text", "font-normal", "no-underline", "data-[pressed]:opacity-80", "data-[selected]:font-semibold", focusVisibleBase, toneRingColor.default),
  primary: clsx("text-primary", "font-normal", "no-underline", "data-[pressed]:opacity-80", "data-[selected]:font-semibold", focusVisibleBase, toneRingColor.primary),
  secondary: clsx("text-secondary", "font-normal", "no-underline", "data-[pressed]:opacity-80", "data-[selected]:font-semibold", focusVisibleBase, toneRingColor.secondary),
  success: clsx("text-success", "font-normal", "no-underline", "data-[pressed]:opacity-80", "data-[selected]:font-semibold", focusVisibleBase, toneRingColor.success),
  warning: clsx("text-warning", "font-normal", "no-underline", "data-[pressed]:opacity-80", "data-[selected]:font-semibold", focusVisibleBase, toneRingColor.warning),
  error: clsx("text-error", "font-normal", "no-underline", "data-[pressed]:opacity-80", "data-[selected]:font-semibold", focusVisibleBase, toneRingColor.error),
  neutral: clsx("text-neutral", "font-normal", "no-underline", "data-[pressed]:opacity-80", "data-[selected]:font-semibold", focusVisibleBase, toneRingColor.neutral),
};

const pillRecipes: Record<TabsTone, string> = {
  default: clsx(
    "text-text font-normal border border-transparent",
    "data-[hovered]:bg-foreground/10 data-[pressed]:bg-foreground/20 data-[selected]:text-text",
    focusVisibleBase,
    toneRingColor.default,
  ),
  primary: clsx(
    "text-primary font-normal border border-primary/20",
    "data-[hovered]:bg-primary/10 data-[pressed]:bg-primary/20 data-[selected]:text-primary",
    focusVisibleBase,
    toneRingColor.primary,
  ),
  secondary: clsx(
    "text-secondary font-normal border border-secondary/20",
    "data-[hovered]:bg-secondary/10 data-[pressed]:bg-secondary/20 data-[selected]:text-secondary",
    focusVisibleBase,
    toneRingColor.secondary,
  ),
  success: clsx(
    "text-success font-normal border border-success/20",
    "data-[hovered]:bg-success/10 data-[pressed]:bg-success/20 data-[selected]:text-success",
    focusVisibleBase,
    toneRingColor.success,
  ),
  warning: clsx(
    "text-warning font-normal border border-warning/20",
    "data-[hovered]:bg-warning/10 data-[pressed]:bg-warning/20 data-[selected]:text-warning",
    focusVisibleBase,
    toneRingColor.warning,
  ),
  error: clsx(
    "text-error font-normal border border-error/20",
    "data-[hovered]:bg-error/10 data-[pressed]:bg-error/20 data-[selected]:text-error",
    focusVisibleBase,
    toneRingColor.error,
  ),
  neutral: clsx(
    "text-neutral font-normal border border-neutral/20",
    "data-[hovered]:bg-neutral/10 data-[pressed]:bg-neutral/20 data-[selected]:text-neutral",
    focusVisibleBase,
    toneRingColor.neutral,
  ),
};

const subtleRecipes: Record<TabsTone, string> = {
  default: clsx(
    "border border-transparent",
    "bg-transparent",
    "text-text",
    "shadow-none",
    "data-[hovered]:bg-foreground/10",
    "data-[pressed]:bg-foreground/15",
    "data-[selected]:bg-foreground/20",
    "data-[selected]:text-text",
    "transition-colors duration-150",
    focusVisibleBase,
    toneRingColor.default,
  ),
  primary: clsx(
    "border border-transparent",
    "bg-transparent",
    "text-primary",
    "shadow-none",
    "data-[hovered]:bg-primary/10",
    "data-[pressed]:bg-primary/15",
    "data-[selected]:bg-primary/20",
    "data-[selected]:text-primary",
    "transition-colors duration-150",
    focusVisibleBase,
    toneRingColor.primary,
  ),
  secondary: clsx(
    "border border-transparent",
    "bg-transparent",
    "text-secondary",
    "shadow-none",
    "data-[hovered]:bg-secondary/10",
    "data-[pressed]:bg-secondary/15",
    "data-[selected]:bg-secondary/20",
    "data-[selected]:text-secondary",
    "transition-colors duration-150",
    focusVisibleBase,
    toneRingColor.secondary,
  ),
  success: clsx(
    "border border-transparent",
    "bg-transparent",
    "text-success",
    "shadow-none",
    "data-[hovered]:bg-success/10",
    "data-[pressed]:bg-success/15",
    "data-[selected]:bg-success/20",
    "data-[selected]:text-success",
    "transition-colors duration-150",
    focusVisibleBase,
    toneRingColor.success,
  ),
  warning: clsx(
    "border border-transparent",
    "bg-transparent",
    "text-warning",
    "shadow-none",
    "data-[hovered]:bg-warning/10",
    "data-[pressed]:bg-warning/15",
    "data-[selected]:bg-warning/20",
    "data-[selected]:text-warning",
    "transition-colors duration-150",
    focusVisibleBase,
    toneRingColor.warning,
  ),
  error: clsx(
    "border border-transparent",
    "bg-transparent",
    "text-error",
    "shadow-none",
    "data-[hovered]:bg-error/10",
    "data-[pressed]:bg-error/15",
    "data-[selected]:bg-error/20",
    "data-[selected]:text-error",
    "transition-colors duration-150",
    focusVisibleBase,
    toneRingColor.error,
  ),
  neutral: clsx(
    "border border-transparent",
    "bg-transparent",
    "text-neutral",
    "shadow-none",
    "data-[hovered]:bg-neutral/10",
    "data-[pressed]:bg-neutral/15",
    "data-[selected]:bg-neutral/20",
    "data-[selected]:text-neutral",
    "transition-colors duration-150",
    focusVisibleBase,
    toneRingColor.neutral,
  ),
};

const solidRecipes: Record<TabsTone, string> = {
  default: clsx(
    "border border-divider/80",
    "bg-foreground/80",
    "text-text",
    "shadow-sm",
    "data-[hovered]:bg-foreground/90",
    "data-[pressed]:bg-foreground",
    "data-[selected]:shadow-md",
    "data-[selected]:text-text",
    "transition-colors duration-150",
    focusVisibleBase,
    toneRingColor.default,
  ),
  primary: clsx(
    "border border-primary",
    "bg-primary/90",
    "text-background",
    "shadow-sm",
    "data-[hovered]:bg-primary",
    "data-[pressed]:bg-primary",
    "data-[selected]:shadow-md",
    focusVisibleBase,
    toneRingColor.primary,
  ),
  secondary: clsx(
    "border border-secondary",
    "bg-secondary/90",
    "text-background",
    "shadow-sm",
    "data-[hovered]:bg-secondary",
    "data-[pressed]:bg-secondary",
    "data-[selected]:shadow-md",
    focusVisibleBase,
    toneRingColor.secondary,
  ),
  success: clsx(
    "border border-success",
    "bg-success/90",
    "text-background",
    "shadow-sm",
    "data-[hovered]:bg-success",
    "data-[pressed]:bg-success",
    "data-[selected]:shadow-md",
    focusVisibleBase,
    toneRingColor.success,
  ),
  warning: clsx(
    "border border-warning",
    "bg-warning/90",
    "text-background",
    "shadow-sm",
    "data-[hovered]:bg-warning",
    "data-[pressed]:bg-warning",
    "data-[selected]:shadow-md",
    focusVisibleBase,
    toneRingColor.warning,
  ),
  error: clsx(
    "border border-error",
    "bg-error/90",
    "text-background",
    "shadow-sm",
    "data-[hovered]:bg-error",
    "data-[pressed]:bg-error",
    "data-[selected]:shadow-md",
    focusVisibleBase,
    toneRingColor.error,
  ),
  neutral: clsx(
    "border border-neutral",
    "bg-neutral/90",
    "text-background",
    "shadow-sm",
    "data-[hovered]:bg-neutral",
    "data-[pressed]:bg-neutral",
    "data-[selected]:shadow-md",
    focusVisibleBase,
    toneRingColor.neutral,
  ),
};

export function tabVariantClasses(tone: TabsTone, variant: TabsVariant) {
  const recipes: Record<TabsVariant, Record<TabsTone, string>> = {
    underline: underlineRecipes,
    text: textRecipes,
    pill: pillRecipes,
    subtle: subtleRecipes,
    solid: solidRecipes,
  };

  return recipes[variant][tone];
}

const underlineIndicatorRecipes: Record<TabsTone, string> = {
  default: "bg-text",
  primary: "bg-primary",
  secondary: "bg-secondary",
  success: "bg-success",
  warning: "bg-warning",
  error: "bg-error",
  neutral: "bg-neutral",
};

const pillIndicatorRecipes: Record<TabsTone, string> = {
  default: "bg-foreground/80 border border-divider/60",
  primary: "bg-primary/80 border border-primary/60",
  secondary: "bg-secondary/80 border border-secondary/60",
  success: "bg-success/80 border border-success/60",
  warning: "bg-warning/80 border border-warning/60",
  error: "bg-error/80 border border-error/60",
  neutral: "bg-neutral/80 border border-neutral/60",
};

const subtleIndicatorColor: Record<TabsTone, string> = {
  default: "bg-foreground/20",
  primary: "bg-primary/20",
  secondary: "bg-secondary/20",
  success: "bg-success/20",
  warning: "bg-warning/20",
  error: "bg-error/20",
  neutral: "bg-neutral/20",
};

const solidIndicatorColor: Record<TabsTone, string> = {
  default: "bg-foreground border border-divider/60",
  primary: "bg-primary border border-primary",
  secondary: "bg-secondary border border-secondary",
  success: "bg-success border border-success",
  warning: "bg-warning border border-warning",
  error: "bg-error border border-error",
  neutral: "bg-neutral border border-neutral",
};

export function indicatorVariantClasses(tone: TabsTone, variant: TabsVariant, animated: boolean) {
  const base = clsx(
    "react-aria-SelectionIndicator absolute pointer-events-none",
    animated ? "transition-[translate,width,height] duration-200 ease-out motion-reduce:transition-none" : "transition-none",
  );

  switch (variant) {
    case "underline":
      return clsx(base, "w-full", underlineIndicatorRecipes[tone]);
    case "text":
      return clsx("hidden");
    case "pill":
      return clsx(base, pillIndicatorRecipes[tone]);
    case "solid":
      return clsx(base, "shadow-md", solidIndicatorColor[tone]);
    case "subtle":
      return clsx(base, subtleIndicatorColor[tone]);
    default:
      return base;
  }
}
