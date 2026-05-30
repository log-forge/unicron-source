import clsx from "clsx";
import { Input as RaInput, type InputProps as RaInputProps } from "react-aria-components";
import { X } from "lucide-react";
import { Button, type UiButtonModeButtonProps } from "../buttons/Button";
import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";
import { getHorizontalPaddingTokens, paddingToClass, radiusToClass, statusToTone, type PaddingFormat, type RadiusFormat } from "../components.styles";
import { toneRecepies, widthToClass, type InputStatus, type InputTone, type InputVariant, type InputWidth } from "./input.styles";

const spacingToVar = (token: Spacing | 0 | "0") => (token === 0 || token === "0" ? "0px" : `var(--spacing-${token})`);

export type BaseInputProps = {
  /** Visual style recipe */
  variant?: InputVariant;
  /** Color tone */
  tone?: InputTone;
  /** Status state */
  status?: InputStatus;
  /** Width behavior */
  width?: InputWidth;
  /** Radius tokens */
  radius?: RadiusFormat;
  /** Padding tokens */
  padding?: PaddingFormat;
  /** Optional text size token */
  textSize?: FontSize;
  /** Extra classes merged into the wrapper */
  wrapperClassName?: string;
  /** Extra classes merged into the input */
  inputClassName?: string;
  /** Leading adornment rendered inside the input */
  startContent?: ReactNode;
  /** Leading padding token override */
  startPadding?: Spacing | 0;
  /** Trailing adornment rendered inside the input */
  endContent?: ReactNode;
  /** Trailing padding token override */
  endPadding?: Spacing | 0;
  /** Overlay content rendered within the input wrapper (e.g., buttons) */
  overlayContent?: ReactNode;
};

export type InputProps = BaseInputProps & Omit<RaInputProps, keyof BaseInputProps | "className">;

export function Input({
  variant = "solid",
  tone = "default",
  status = "default",
  width = "full",
  radius = "md",
  padding = ["xs", "4xs"],
  textSize = "base",
  wrapperClassName,
  inputClassName,
  startContent,
  startPadding = 0,
  endContent,
  endPadding = 0,
  overlayContent,
  value,
  defaultValue,
  onChange,
  ...rest
}: InputProps) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const widthClass = widthToClass(width);
  const radiusClass = variant === "underline" || variant === "text" ? "rounded-none" : radiusToClass(radius);
  const paddingClass = paddingToClass(padding, "xs");
  const hasStart = Boolean(startContent);
  const hasEnd = Boolean(endContent) || Boolean(overlayContent);
  const { left: basePaddingLeft, right: basePaddingRight } = getHorizontalPaddingTokens(padding);
  const { wrapper: wrapperToneClass, input: inputToneClass } = toneRecepies(variant, statusToTone(status, tone));

  const wrapperBaseClass = clsx(
    "relative transition-[background,color,border,box-shadow] duration-150 ease-out py-0",
    "focus-visible:outline-none",
    "disabled:cursor-not-allowed disabled:opacity-60",
  );
  const inputBaseClass = clsx(
    "w-full transition-[background,color,border,box-shadow] duration-150 ease-out outline-none",
    "placeholder:text-neutral/60",
    "focus-visible:outline-none",
    "disabled:cursor-not-allowed disabled:opacity-60 ",
  );

  const resolvedTextSize = textSize ?? "base";
  const sizeClass = resolvedTextSize ? `text-${resolvedTextSize}` : "";

  const deriveHasValue = (maybeValue: unknown) => maybeValue !== null && maybeValue !== undefined && maybeValue !== "";
  const [hasValue, setHasValue] = useState(() => deriveHasValue(value ?? defaultValue));

  useEffect(() => {
    setHasValue(deriveHasValue(value));
  }, [value]);

  const handleChange: RaInputProps["onChange"] = (event) => {
    setHasValue(deriveHasValue(event.currentTarget.value));
    onChange?.(event);
  };

  const handleBlur: RaInputProps["onBlur"] = (event) => {
    rest.onBlur?.(event);
    setHasValue(deriveHasValue(event.currentTarget.value));
  };

  return (
    <div
      data-tone={statusToTone(status, tone)}
      data-variant={variant}
      onClick={(e) => {
        // If the user clicked an interactive child (button, link, input, etc.),
        // don't steal focus. Otherwise focus the inner input.
        const target = e.target as HTMLElement | null;
        if (target?.closest && target.closest('button, a, input, textarea, select, [role="button"]')) return;
        inputRef.current?.focus();
      }}
      className={clsx("group/input-wrapper", wrapperBaseClass, wrapperToneClass, widthClass, sizeClass, radiusClass, wrapperClassName)}
    >
      {startContent && <span className={`pointer-events-none absolute inset-y-0 left-0 flex translate-x-1/2 items-center justify-center text-current/70`}>{startContent}</span>}
      <RaInput
        {...rest}
        value={value}
        defaultValue={defaultValue}
        onChange={handleChange}
        onBlur={handleBlur}
        data-tone={statusToTone(status, tone)}
        data-variant={variant}
        data-has-value={hasValue ? "true" : "false"}
        ref={inputRef}
        style={{
          paddingLeft: hasStart && startPadding !== undefined ? `calc(${spacingToVar(basePaddingLeft)} + ${spacingToVar(startPadding)})` : spacingToVar(basePaddingLeft),
          paddingRight: hasEnd && endPadding !== undefined ? `calc(${spacingToVar(basePaddingRight)} + ${spacingToVar(endPadding)})` : spacingToVar(basePaddingRight),
          ...(rest.style as CSSProperties),
        }}
        className={clsx("group/input peer/input", inputBaseClass, inputToneClass, sizeClass, radiusClass, paddingClass, inputClassName)}
      />
      {endContent && <span className={`pointer-events-none absolute inset-y-0 right-0 flex -translate-x-1/2 items-center justify-center text-current/70`}>{endContent}</span>}
      {overlayContent}
    </div>
  );
}

type InputClearProps = {
  buttonProps?: Omit<UiButtonModeButtonProps, "children" | "variant" | "mode" | "iconOnly" | "radius" | "className" | "style" | "onPress" | "aria-label">;
  ariaLabel?: string;
  onClear?: () => void;
  className?: string;
  textSize?: FontSize;
};

export function InputClear({ buttonProps, ariaLabel = "Clear", onClear, className, textSize = "base" }: InputClearProps) {
  const iconSizeVar = `var(--text-${textSize})`;

  return (
    <Button
      {...buttonProps}
      variant="glass"
      mode="button"
      iconOnly
      radius={"full"}
      className={clsx("absolute! top-1/2 flex -translate-y-1/2 items-center justify-center", className)}
      style={{ right: iconSizeVar }}
      onPress={() => onClear?.()}
      aria-label={ariaLabel}
    >
      <X style={{ width: iconSizeVar, height: iconSizeVar }} />
    </Button>
  );
}
