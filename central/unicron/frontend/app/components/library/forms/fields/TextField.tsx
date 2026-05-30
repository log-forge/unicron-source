import { TextField as RaTextField, Label, Text, FieldError } from "react-aria-components";
import { Input } from "../Input";
import { getYPaddingToken, paddingToClass, spacingToVar, statusToTone, widthToClass } from "../../components.styles";
import clsx from "clsx";
import { Button } from "../../buttons/Button";
import { Eye, EyeClosed } from "lucide-react";
import { useState } from "react";
import { classRecepies, type TextFieldButtonProps, type TextFieldInputProps, type TextFieldProps } from "./text-field.styles";

const defaultInputProps: TextFieldInputProps = {
  variant: "solid",
  padding: ["sm", "3xs"],
  wrapperClassName: "",
  inputClassName: "",
  startContent: undefined,
  startPadding: 0,
  endContent: undefined,
  endPadding: 0,
  overlayContent: undefined,
  placeholder: "",
};

const defaultButtonProps: TextFieldButtonProps = { variant: "solid", radius: "md", padding: "4xs", className: "" };

export function TextField({
  variant = "stacked",
  tone = "default",
  status = "default",
  width = "full",
  radius = "md",
  padding = 0,
  gap = "3xs",
  labelGap = "3xs",
  messageGap = "4xs",
  textSize = "sm",
  labelTextSize = "sm",
  messageTextSize = "xs",
  doesStatusEffectInput = false,
  doesStatusEffectLabel = false,
  doesStatusEffectDescription = false,
  className,
  labelClassName = "",
  descriptionClassName = "",
  messageClassName = "",
  label,
  description,
  errorMessage,
  inputProps,
  buttonProps,
  ...rest
}: TextFieldProps) {
  const [passwordVisible, setPasswordVisible] = useState(false);

  const isFloatingVariant = variant === "floating" || variant === "nested_floating";
  const isNestedFloatingVariant = variant === "nested_floating";
  const { isInvalid: fieldIsInvalid, isDisabled: fieldIsDisabled, isReadOnly: fieldIsReadOnly, isRequired: fieldIsRequired, ...restFieldProps } = rest;
  const derivedStatusBase = fieldIsInvalid ? "error" : status;
  const toneForState = statusToTone(derivedStatusBase, tone);
  const baseRecipe = classRecepies(variant, tone);
  const statusRecipe = classRecepies(variant, toneForState);
  const labelRecipe = doesStatusEffectLabel ? statusRecipe.label : baseRecipe.label;
  const inputWrapperRecipe = doesStatusEffectInput ? statusRecipe.inputWrapper : baseRecipe.inputWrapper;
  const inputRecipe = doesStatusEffectInput ? statusRecipe.input : baseRecipe.input;
  const buttonWrapperRecipe = doesStatusEffectInput ? statusRecipe.buttonWrapper : baseRecipe.buttonWrapper;
  const buttonRecipe = doesStatusEffectInput ? statusRecipe.button : baseRecipe.button;
  const descriptionRecipe = doesStatusEffectDescription ? statusRecipe.description : baseRecipe.description;
  const fieldErrorRecipe = statusRecipe.fieldError;

  const mergedInputProps = { ...defaultInputProps, ...inputProps };
  const mergedButtonProps = { ...defaultButtonProps, ...buttonProps };

  const resolvedInputProps = {
    ...mergedInputProps,
    wrapperClassName: clsx(inputWrapperRecipe, mergedInputProps?.wrapperClassName),
    inputClassName: clsx(inputRecipe, mergedInputProps?.inputClassName),
    style: isNestedFloatingVariant
      ? { marginTop: `var(--text-${textSize})`, marginBottom: `var(--text-${textSize})`, ...mergedInputProps.style }
      : isFloatingVariant
        ? { marginTop: `calc(var(--text-${textSize}) * 1/4)`, marginBottom: `calc(var(--text-${textSize}) * 1/4)`, ...mergedInputProps.style }
        : { ...mergedInputProps.style },
  };
  const resolvedButtonProps = {
    ...mergedButtonProps,
    className: clsx(buttonRecipe, mergedButtonProps?.className),
  };

  return (
    <RaTextField
      data-variant={variant}
      data-tone={tone}
      isInvalid={fieldIsInvalid}
      isDisabled={fieldIsDisabled}
      isReadOnly={fieldIsReadOnly}
      isRequired={fieldIsRequired}
      {...{
        ...restFieldProps,
        className: clsx(
          "group/text-field flex flex-col items-start justify-start focus-visible:outline-none",
          `gap-${messageGap}`,
          widthToClass(width),
          paddingToClass(padding, "xs"),
          className,
        ),
      }}
    >
      <div className={clsx("w-full", `gap-${labelGap} gap-x-${gap}`, baseRecipe.textField)}>
        {!isFloatingVariant && (
          <Label data-variant={variant} data-tone={tone} className={clsx("transition-all duration-150", `text-${labelTextSize}`, labelRecipe, labelClassName)}>
            {label}
            <span className="text-error">{` ${fieldIsRequired ? "*" : ""}`}</span>
          </Label>
        )}
        <Input
          {...{
            ...resolvedInputProps,
            tone: doesStatusEffectInput ? toneForState : tone,
            status: doesStatusEffectInput ? derivedStatusBase : "default",
            radius: radius,
            width: width,
            textSize,
            disabled: fieldIsDisabled,
            readOnly: fieldIsReadOnly,
            required: fieldIsRequired,
            type: rest.type === "password" && passwordVisible ? "text" : rest.type,
            overlayContent: (
              <>
                {isFloatingVariant && (
                  <Label
                    data-variant={variant}
                    data-tone={tone}
                    className={clsx(
                      "leading-heading transition-all duration-150",
                      `text-${labelTextSize} ${mergedInputProps.startContent ? `left-${mergedInputProps.startPadding}` : "left-0"}`,
                      labelRecipe,
                      mergedInputProps.padding && paddingToClass(mergedInputProps.padding, "xs"),
                      labelClassName,
                    )}
                  >
                    {label}
                    <span className="text-error">{` ${fieldIsRequired ? "*" : ""}`}</span>
                  </Label>
                )}
                {rest.type === "password" && (
                  <span className={clsx(buttonWrapperRecipe)} style={{ transform: `translateX(calc(${spacingToVar(getYPaddingToken(mergedInputProps.padding, "4xs"))} * -1))` }}>
                    <Button
                      {...{
                        ...resolvedButtonProps,
                        mode: "button",
                        tone: doesStatusEffectInput ? toneForState : tone,
                        width: "icon",
                        textSize,
                        disabled: fieldIsDisabled,
                        onPress: () => setPasswordVisible(!passwordVisible),
                      }}
                      iconOnly
                      aria-label={passwordVisible ? "Hide password" : "Show password"}
                    >
                      {passwordVisible ? (
                        <Eye className="aspect-square" style={{ width: `var(--text-${textSize})`, height: `var(--text-${textSize})` }} />
                      ) : (
                        <EyeClosed className="aspect-square" style={{ width: `var(--text-${textSize})`, height: `var(--text-${textSize})` }} />
                      )}
                    </Button>
                  </span>
                )}
                {mergedInputProps.overlayContent ? mergedInputProps.overlayContent : undefined}
              </>
            ),
          }}
        />
      </div>

      <span className={clsx("flex flex-col items-start justify-start", `gap-${messageGap}`)}>
        {description && (
          <Text data-variant={variant} data-tone={tone} slot="description" className={clsx(`text-${messageTextSize}`, descriptionRecipe, descriptionClassName)}>
            {description}
          </Text>
        )}
        <FieldError data-variant={variant} data-tone={tone} className={clsx(`text-${messageTextSize}`, fieldErrorRecipe, messageClassName)}>
          {errorMessage}
        </FieldError>
      </span>
    </RaTextField>
  );
}
