export type BaseWidthMode = "content" | "full";
export type BaseTone = "default" | "primary" | "secondary" | "success" | "warning" | "error" | "neutral";
export type BaseVariant = "solid" | "outline" | "ghost" | "subtle" | "text";
export type BaseStatus = "default" | "error" | "warning" | "success";
export type PaddingFormat = Spacing | [Spacing, Spacing] | [Spacing, Spacing, Spacing] | [Spacing, Spacing, Spacing, Spacing] | 0;
export type RadiusFormat = Radius | [Radius, Radius] | [Radius, Radius, Radius] | [Radius, Radius, Radius, Radius];

export function widthToClass(width: BaseWidthMode): string {
  switch (width) {
    case "full":
      return "w-full";
    case "content":
    default:
      return "w-fit";
  }
}

export function radiusToClass(radius: RadiusFormat, defaultRadius: Radius = "md"): string {
  if (radius === "none") return "rounded-none";

  if (typeof radius === "string") {
    if (radius === "full") return "rounded-full";
    return `rounded-${radius}`;
  } else if (Array.isArray(radius)) {
    switch (radius.length) {
      case 2:
        return `rounded-y-${radius[0]} rounded-x-${radius[1]}`;
      case 3:
        return `rounded-t-${radius[0]} rounded-x-${radius[1]} rounded-b-${radius[2]}`;
      case 4:
        return `rounded-tl-${radius[0]} rounded-tr-${radius[1]} rounded-br-${radius[2]} rounded-bl-${radius[3]}`;
      default:
        return "";
    }
  }

  return `rounded-${defaultRadius}`;
}

export function paddingToClass(padding: PaddingFormat, defaultPadding: Spacing = "xs"): string {
  if (typeof padding === "string" || (typeof padding === "number" && padding === 0)) {
    return `p-${padding}`;
  } else if (Array.isArray(padding)) {
    switch (padding.length) {
      case 2:
        return `px-${padding[0]} py-${padding[1]}`;
      case 3:
        return `pt-${padding[0]} px-${padding[1]} pb-${padding[2]}`;
      case 4:
        return `pt-${padding[0]} pr-${padding[1]} pl-${padding[2]} pb-${padding[3]}`;
      default:
        return "";
    }
  }

  return `p-${defaultPadding}`;
}

export function statusToTone(status: BaseStatus, tone: BaseTone): BaseTone {
  if (status === "default") {
    return tone;
  }

  return status;
}

export function getHorizontalPaddingTokens(padding: PaddingFormat): { left: Spacing | 0; right: Spacing | 0 } {
  if (typeof padding === "string" || typeof padding === "number") {
    const token = padding as Spacing | 0;
    return { left: token, right: token };
  }

  if (Array.isArray(padding)) {
    if (padding.length === 2) {
      const token = (padding[0] ?? "xs") as Spacing | 0;
      return { left: token, right: token };
    }

    if (padding.length === 3) {
      const token = (padding[1] ?? "xs") as Spacing | 0;
      return { left: token, right: token };
    }

    if (padding.length === 4) {
      return {
        right: (padding[1] ?? padding[2] ?? "xs") as Spacing | 0,
        left: (padding[2] ?? padding[1] ?? "xs") as Spacing | 0,
      };
    }
  }

  return { left: "xs", right: "xs" };
}

/**
 * Extracts the vertical padding token from a padding format.
 * Falls back to the provided default when padding is undefined.
 */
export function getYPaddingToken(padding: PaddingFormat | undefined, fallback: Spacing | 0 = "xs"): Spacing | 0 {
  if (padding === undefined) return fallback;
  if (padding === 0) return 0;

  if (typeof padding === "string") {
    return padding;
  }

  if (Array.isArray(padding)) {
    if (padding.length === 2) return padding[1] ?? fallback; // [px, py]
    if (padding.length === 3) return padding[2] ?? padding[0] ?? fallback; // [pt, px, pb]
    if (padding.length === 4) return padding[3] ?? padding[0] ?? fallback; // [pt, pr, pl, pb]
  }

  return fallback;
}

export const spacingToVar = (token: Spacing | 0 | undefined) => (token === 0 ? "0px" : `var(--spacing-${token ?? "0"})`);
