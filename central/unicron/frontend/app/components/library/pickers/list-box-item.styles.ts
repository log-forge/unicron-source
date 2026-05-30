import clsx from "clsx";
import { paddingToClass, radiusToClass, type BaseTone, type BaseVariant, type PaddingFormat, type RadiusFormat } from "../components.styles";

export type ListBoxItemVariant = BaseVariant | "glass" | "subtle";
export type ListBoxItemTone = BaseTone;

const variantBase: Record<ListBoxItemVariant, string> = {
  solid: "border border-transparent",
  outline: "border border-transparent",
  ghost: "border border-transparent",
  subtle: "border border-transparent",
  text: "border border-transparent",
  glass: "border border-transparent backdrop-blur-[2px]",
};

const toneRecipes: Record<ListBoxItemVariant, Record<ListBoxItemTone, string>> = {
  solid: {
    default:
      "text-text data-[hovered]:bg-foreground/50 data-[focused]:bg-foreground/50 data-[selected]:bg-foreground/70 data-[selected]:text-text data-[focus-visible]:inset-ring-1 data-[focus-visible]:ring-primary-500",
    primary:
      "text-text data-[hovered]:bg-primary/20 data-[focused]:bg-primary/20 data-[selected]:bg-primary/40 data-[focus-visible]:inset-ring-1 data-[focus-visible]:ring-primary-500",
    secondary:
      "text-text data-[hovered]:bg-secondary/20 data-[focused]:bg-secondary/20 data-[selected]:bg-secondary/40 data-[focus-visible]:inset-ring-1 data-[focus-visible]:ring-secondary-500",
    success:
      "text-success data-[hovered]:bg-success/20 data-[focused]:bg-success/20 data-[selected]:bg-success/40 data-[focus-visible]:inset-ring-1 data-[focus-visible]:ring-success-500",
    warning:
      "text-warning data-[hovered]:bg-warning/20 data-[focused]:bg-warning/20 data-[selected]:bg-warning/40 data-[focus-visible]:inset-ring-1 data-[focus-visible]:ring-warning-500",
    error: "text-error data-[hovered]:bg-error/20 data-[focused]:bg-error/20 data-[selected]:bg-error/40 data-[focus-visible]:inset-ring-1 data-[focus-visible]:ring-error-500",
    neutral:
      "text-neutral data-[hovered]:bg-neutral/20 data-[focused]:bg-neutral/20 data-[selected]:bg-neutral/40 data-[focus-visible]:inset-ring-1 data-[focus-visible]:ring-secondary-500",
  },
  outline: {
    default:
      "text-text border-divider data-[hovered]:bg-foreground/10 data-[focused]:bg-foreground/10 data-[selected]:border-primary data-[selected]:text-primary data-[focus-visible]:inset-ring-1 data-[focus-visible]:ring-primary-500",
    primary:
      "text-primary border-primary/60 data-[hovered]:bg-primary/5 data-[focused]:bg-primary/5 data-[selected]:border-primary data-[selected]:text-primary data-[focus-visible]:inset-ring-1 data-[focus-visible]:ring-primary-500",
    secondary:
      "text-secondary border-secondary/60 data-[hovered]:bg-secondary/5 data-[focused]:bg-secondary/5 data-[selected]:border-secondary data-[selected]:text-secondary data-[focus-visible]:inset-ring-1 data-[focus-visible]:ring-secondary-500",
    success:
      "text-success border-success/60 data-[hovered]:bg-success/5 data-[focused]:bg-success/5 data-[selected]:border-success data-[selected]:text-success data-[focus-visible]:inset-ring-1 data-[focus-visible]:ring-success-500",
    warning:
      "text-warning border-warning/60 data-[hovered]:bg-warning/5 data-[focused]:bg-warning/5 data-[selected]:border-warning data-[selected]:text-warning data-[focus-visible]:inset-ring-1 data-[focus-visible]:ring-warning-500",
    error:
      "text-error border-error/60 data-[hovered]:bg-error/5 data-[focused]:bg-error/5 data-[selected]:border-error data-[selected]:text-error data-[focus-visible]:inset-ring-1 data-[focus-visible]:ring-error-500",
    neutral:
      "text-neutral border-neutral/60 data-[hovered]:bg-neutral/5 data-[focused]:bg-neutral/5 data-[selected]:border-neutral data-[selected]:text-neutral data-[focus-visible]:inset-ring-1 data-[focus-visible]:ring-secondary-500",
  },
  ghost: {
    default:
      "text-text data-[hovered]:bg-foreground/10 data-[focused]:bg-foreground/10 data-[selected]:bg-foreground/20 data-[focus-visible]:inset-ring-1 data-[focus-visible]:ring-primary-500",
    primary:
      "text-primary data-[hovered]:bg-primary/5 data-[focused]:bg-primary/5 data-[selected]:bg-primary/15 data-[focus-visible]:inset-ring-1 data-[focus-visible]:ring-primary-500",
    secondary:
      "text-secondary data-[hovered]:bg-secondary/5 data-[focused]:bg-secondary/5 data-[selected]:bg-secondary/15 data-[focus-visible]:inset-ring-1 data-[focus-visible]:ring-secondary-500",
    success:
      "text-success data-[hovered]:bg-success/5 data-[focused]:bg-success/5 data-[selected]:bg-success/15 data-[focus-visible]:inset-ring-1 data-[focus-visible]:ring-success-500",
    warning:
      "text-warning data-[hovered]:bg-warning/5 data-[focused]:bg-warning/5 data-[selected]:bg-warning/15 data-[focus-visible]:inset-ring-1 data-[focus-visible]:ring-warning-500",
    error: "text-error data-[hovered]:bg-error/5 data-[focused]:bg-error/5 data-[selected]:bg-error/15 data-[focus-visible]:inset-ring-1 data-[focus-visible]:ring-error-500",
    neutral:
      "text-neutral data-[hovered]:bg-neutral/5 data-[focused]:bg-neutral/5 data-[selected]:bg-neutral/15 data-[focus-visible]:inset-ring-1 data-[focus-visible]:ring-secondary-500",
  },
  subtle: {
    default:
      "text-text bg-alt-background data-[hovered]:bg-foreground/10 data-[focused]:bg-foreground/10 data-[selected]:bg-foreground/20 data-[focus-visible]:inset-ring-1 data-[focus-visible]:ring-primary-500",
    primary:
      "text-primary bg-primary/5 data-[hovered]:bg-primary/10 data-[focused]:bg-primary/10 data-[selected]:bg-primary/20 data-[focus-visible]:inset-ring-1 data-[focus-visible]:ring-primary-500",
    secondary:
      "text-secondary bg-secondary/5 data-[hovered]:bg-secondary/10 data-[focused]:bg-secondary/10 data-[selected]:bg-secondary/20 data-[focus-visible]:inset-ring-1 data-[focus-visible]:ring-secondary-500",
    success:
      "text-success bg-success/5 data-[hovered]:bg-success/10 data-[focused]:bg-success/10 data-[selected]:bg-success/20 data-[focus-visible]:inset-ring-1 data-[focus-visible]:ring-success-500",
    warning:
      "text-warning bg-warning/5 data-[hovered]:bg-warning/10 data-[focused]:bg-warning/10 data-[selected]:bg-warning/20 data-[focus-visible]:inset-ring-1 data-[focus-visible]:ring-warning-500",
    error:
      "text-error bg-error/5 data-[hovered]:bg-error/10 data-[focused]:bg-error/10 data-[selected]:bg-error/20 data-[focus-visible]:inset-ring-1 data-[focus-visible]:ring-error-500",
    neutral:
      "text-neutral bg-neutral/5 data-[hovered]:bg-neutral/10 data-[focused]:bg-neutral/10 data-[selected]:bg-neutral/20 data-[focus-visible]:inset-ring-1 data-[focus-visible]:ring-secondary-500",
  },
  text: {
    default: "text-text data-[hovered]:underline data-[focused]:underline data-[selected]:font-semibold data-[focus-visible]:inset-ring-1 data-[focus-visible]:ring-primary-500",
    primary: "text-primary data-[hovered]:underline data-[focused]:underline data-[selected]:font-semibold data-[focus-visible]:inset-ring-1 data-[focus-visible]:ring-primary-500",
    secondary:
      "text-secondary data-[hovered]:underline data-[focused]:underline data-[selected]:font-semibold data-[focus-visible]:inset-ring-1 data-[focus-visible]:ring-secondary-500",
    success: "text-success data-[hovered]:underline data-[focused]:underline data-[selected]:font-semibold data-[focus-visible]:inset-ring-1 data-[focus-visible]:ring-success-500",
    warning: "text-warning data-[hovered]:underline data-[focused]:underline data-[selected]:font-semibold data-[focus-visible]:inset-ring-1 data-[focus-visible]:ring-warning-500",
    error: "text-error data-[hovered]:underline data-[focused]:underline data-[selected]:font-semibold data-[focus-visible]:inset-ring-1 data-[focus-visible]:ring-error-500",
    neutral:
      "text-neutral data-[hovered]:underline data-[focused]:underline data-[selected]:font-semibold data-[focus-visible]:inset-ring-1 data-[focus-visible]:ring-secondary-500",
  },
  glass: {
    default:
      "text-text border border-divider/40 backdrop-blur-[2px] data-[hovered]:bg-background/20 data-[focused]:bg-background/20 data-[selected]:bg-background/30 data-[focus-visible]:inset-ring-1 data-[focus-visible]:ring-primary-500",
    primary:
      "text-primary border border-primary/40 backdrop-blur-[2px] data-[hovered]:bg-primary/10 data-[focused]:bg-primary/10 data-[selected]:bg-primary/20 data-[focus-visible]:inset-ring-1 data-[focus-visible]:ring-primary-500",
    secondary:
      "text-secondary border border-secondary/40 backdrop-blur-[2px] data-[hovered]:bg-secondary/10 data-[focused]:bg-secondary/10 data-[selected]:bg-secondary/20 data-[focus-visible]:inset-ring-1 data-[focus-visible]:ring-secondary-500",
    success:
      "text-success border border-success/40 backdrop-blur-[2px] data-[hovered]:bg-success/10 data-[focused]:bg-success/10 data-[selected]:bg-success/20 data-[focus-visible]:inset-ring-1 data-[focus-visible]:ring-success-500",
    warning:
      "text-warning border border-warning/40 backdrop-blur-[2px] data-[hovered]:bg-warning/10 data-[focused]:bg-warning/10 data-[selected]:bg-warning/20 data-[focus-visible]:inset-ring-1 data-[focus-visible]:ring-warning-500",
    error:
      "text-error border border-error/40 backdrop-blur-[2px] data-[hovered]:bg-error/10 data-[focused]:bg-error/10 data-[selected]:bg-error/20 data-[focus-visible]:inset-ring-1 data-[focus-visible]:ring-error-500",
    neutral:
      "text-neutral border border-neutral/40 backdrop-blur-[2px] data-[hovered]:bg-neutral/10 data-[focused]:bg-neutral/10 data-[selected]:bg-neutral/20 data-[focus-visible]:inset-ring-1 data-[focus-visible]:ring-secondary-500",
  },
};

export function listBoxItemToneRecipe(variant: ListBoxItemVariant, tone: ListBoxItemTone) {
  return clsx(variantBase[variant], toneRecipes[variant][tone]);
}

export function listBoxItemClassNames({
  variant,
  tone,
  padding,
  radius,
  defaultPadding = "2xs",
  defaultRadius = "md",
}: {
  variant: ListBoxItemVariant;
  tone: ListBoxItemTone;
  padding?: PaddingFormat;
  radius?: RadiusFormat;
  defaultPadding?: Spacing | 0;
  defaultRadius?: Radius;
}) {
  return clsx(listBoxItemToneRecipe(variant, tone), paddingToClass(padding ?? defaultPadding, "2xs"), radiusToClass(radius ?? defaultRadius, defaultRadius));
}
