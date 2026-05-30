import * as React from "react";
import { Button as RaButton, ToggleButton as RaToggleButton, type ButtonProps as RaButtonProps, type ToggleButtonProps as RaToggleButtonProps } from "react-aria-components";
import { paddingToClass, radiusToClass, type PaddingFormat, type RadiusFormat } from "../components.styles";
import { toneRecepies, widthToClass, type ButtonTone, type ButtonVariant, type ButtonWidth } from "./button.styles";
import clsx from "clsx";

type VisualProps = {
  /** Visual style */
  variant?: ButtonVariant;
  /** Color tone (mapped to theme tokens) */
  tone?: ButtonTone;
  /** Width behavior */
  width?: ButtonWidth;
  /** Radius size */
  radius?: RadiusFormat;
  /** Padding tokens (from app.css @source) */
  padding?: PaddingFormat;
  /** Text size token/length */
  textSize?: FontSize;
  /** Treat as icon-only (square) button */
  iconOnly?: boolean;
  /** Extra classes merged at the end */
  className?: string;
};

/** React Aria Button mode (default) */
export type UiButtonModeButtonProps = VisualProps &
  Omit<RaButtonProps, keyof VisualProps | "className"> & {
    mode?: "button";
  };

/** React Aria ToggleButton mode */
export type UiButtonModeToggleProps = VisualProps &
  Omit<RaToggleButtonProps, keyof VisualProps | "className"> & {
    mode: "toggle";
  };

export type ButtonProps = UiButtonModeButtonProps | UiButtonModeToggleProps;

export function Button({
  mode = "button",
  variant = "solid",
  tone = "default",
  width = "content",
  radius = "md",
  padding = ["xs", "3xs"],
  textSize = "base",
  iconOnly = false,
  className,
  children,
  ...rest
}: ButtonProps) {
  const isRipple = variant === "ripple";
  const [ripple, setRipple] = React.useState<null | { x: number; y: number; key: number }>(null);
  const rippleTimeout = React.useRef<number | null>(null);

  const startRipple = (e: any) => {
    if (!isRipple) return;
    if (e.x === -1 && e.y === -1) return;

    setRipple({ x: e.x, y: e.y, key: Date.now() });

    if (rippleTimeout.current != null) window.clearTimeout(rippleTimeout.current);
    rippleTimeout.current = window.setTimeout(() => setRipple(null), 400);
  };

  React.useEffect(() => {
    return () => {
      if (rippleTimeout.current != null) window.clearTimeout(rippleTimeout.current);
    };
  }, []);

  const radiusClass = variant === "pill" ? radiusToClass("full") : radiusToClass(radius);
  const widthClass = widthToClass(width, iconOnly);
  const paddingClass = paddingToClass(padding);

  const baseClass = [
    isRipple ? "relative" : "",
    "select-none text-base group/button cursor-pointer",
    "transition-all duration-150 ease-out",
    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:ring-offset-background",
    "data-[disabled]:opacity-50 data-[disabled]:cursor-not-allowed data-[disabled]:shadow-none data-[disabled]:pointer-events-none",
    "data-[pressed]:scale-[0.98]",
    "data-[selected]:ring-2 data-[selected]:ring-offset-2 data-[selected]:ring-offset-background",
    "whitespace-nowrap",
  ].join(" ");

  const visualClass = clsx(radiusClass, widthClass, paddingClass, toneRecepies(variant, tone), className);

  const content = (
    <>
      {isRipple && ripple && (
        <span
          key={ripple.key}
          className={clsx(
            "pointer-events-none absolute aspect-square w-[50%] -translate-x-1/2 -translate-y-1/2 animate-ping rounded-full",
            'group-data-[tone="default"]/button:bg-background/40',
            'group-data-[tone="primary"]/button:bg-background/40',
            'group-data-[tone="secondary"]/button:bg-background/40',
            'group-data-[tone="success"]/button:bg-background/40',
            'group-data-[tone="warning"]/button:bg-background/40',
            'group-data-[tone="error"]/button:bg-background/40',
            'group-data-[tone="neutral"]/button:bg-background/40',
          )}
          style={{ left: ripple.x, top: ripple.y }}
        />
      )}
      {children as React.ReactNode}
    </>
  );

  if (mode === "toggle") {
    const { onPress, ...toggleRest } = rest as RaToggleButtonProps & {
      onPress?: RaToggleButtonProps["onPress"];
    };

    return (
      <RaToggleButton
        {...toggleRest}
        onPress={(e) => {
          startRipple(e);
          onPress?.(e);
        }}
        data-tone={tone}
        data-variant={variant}
        className={`text-${textSize} ${baseClass} ${visualClass}`}
      >
        {content}
      </RaToggleButton>
    );
  }

  const { onPress, ...buttonRest } = rest as RaButtonProps & {
    onPress?: RaButtonProps["onPress"];
  };

  return (
    <RaButton
      {...buttonRest}
      onPress={(e) => {
        startRipple(e);
        onPress?.(e);
      }}
      data-tone={tone}
      data-variant={variant}
      className={`text-${textSize} ${baseClass} ${visualClass}`}
    >
      {content}
    </RaButton>
  );
}
