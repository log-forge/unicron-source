import { NumberField as RaNumberField, Label, Text, FieldError, Group } from "react-aria-components";
import { Input } from "../Input";
import { getHorizontalPaddingTokens, paddingToClass, spacingToVar, statusToTone, widthToClass, type RadiusFormat } from "../../components.styles";
import clsx from "clsx";
import { Button } from "../../buttons/Button";
import { Minus, Plus } from "lucide-react";
import { classRecepies, stepperPlacementRecipes, type NumberFieldButtonProps, type NumberFieldInputProps, type NumberFieldProps } from "./number-field.styles";

const defaultInputProps: NumberFieldInputProps = {
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

const defaultButtonProps: NumberFieldButtonProps = { variant: "solid", radius: "md", padding: "4xs", className: "" };

export function NumberField({
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
  stepperPosition = "right-stacked",
  stepperStartPadding,
  stepperEndPadding,
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
}: NumberFieldProps) {
  const isFloatingVariant = variant === "floating" || variant === "nested_floating";
  const isNestedFloatingVariant = variant === "nested_floating";
  const { isInvalid: fieldIsInvalid, isDisabled: fieldIsDisabled, isReadOnly: fieldIsReadOnly, isRequired: fieldIsRequired, ...restFieldProps } = rest;
  const derivedStatusBase = fieldIsInvalid ? "error" : status;
  const toneForState = statusToTone(derivedStatusBase, tone);
  const baseRecipe = classRecepies(variant, tone, stepperPosition);
  const statusRecipe = classRecepies(variant, toneForState, stepperPosition);
  const placement = stepperPlacementRecipes(stepperPosition);
  const labelRecipe = doesStatusEffectLabel ? statusRecipe.label : baseRecipe.label;
  const inputWrapperRecipe = doesStatusEffectInput ? statusRecipe.inputWrapper : baseRecipe.inputWrapper;
  const inputRecipe = doesStatusEffectInput ? statusRecipe.input : baseRecipe.input;
  const buttonWrapperRecipe = doesStatusEffectInput ? statusRecipe.buttonWrapper : baseRecipe.buttonWrapper;
  const secondaryButtonWrapperRecipe = doesStatusEffectInput ? statusRecipe.secondaryButtonWrapper : baseRecipe.secondaryButtonWrapper;
  const buttonRecipe = doesStatusEffectInput ? statusRecipe.button : baseRecipe.button;
  const primaryDirection = baseRecipe.buttonDirection ?? placement.primaryDirection;
  const secondaryDirection = baseRecipe.secondaryButtonDirection ?? placement.secondaryDirection;
  const primarySide: "left" | "right" = stepperPosition === "split" ? "left" : stepperPosition.startsWith("left") ? "left" : "right";
  const secondarySide: "left" | "right" | null = stepperPosition === "split" ? "right" : null;
  const primaryButtons: "both" | "increment" | "decrement" = stepperPosition === "split" ? "decrement" : "both";
  const secondaryButtons: "both" | "increment" | "decrement" = "increment";
  const descriptionRecipe = doesStatusEffectDescription ? statusRecipe.description : baseRecipe.description;
  const fieldErrorRecipe = statusRecipe.fieldError;

  const mergedInputProps = { ...defaultInputProps, ...inputProps };
  const mergedButtonProps = { ...defaultButtonProps, ...buttonProps };
  const usesLeftStepper = stepperPosition === "left-stacked" || stepperPosition === "left-inline" || stepperPosition === "split";
  const usesRightStepper = stepperPosition === "right-stacked" || stepperPosition === "right-inline" || stepperPosition === "split";
  const { left: baseLeftPadding, right: baseRightPadding } = getHorizontalPaddingTokens(mergedInputProps.padding ?? 0);
  const resolvedStepperStartPadding = stepperStartPadding ?? baseLeftPadding ?? "xs";
  const resolvedStepperEndPadding = stepperEndPadding ?? baseRightPadding ?? "xs";
  const leftTransformStyle = usesLeftStepper ? { transform: `translateX(${spacingToVar(resolvedStepperStartPadding)})` } : undefined;
  const rightTransformStyle = usesRightStepper ? { transform: `translateX(calc(${spacingToVar(resolvedStepperEndPadding)} * -1))` } : undefined;
  const startPaddingFromProps = inputProps?.startPadding;
  const endPaddingFromProps = inputProps?.endPadding;
  const resolvedStartPadding =
    usesLeftStepper && (startPaddingFromProps === undefined || startPaddingFromProps === 0)
      ? resolvedStepperStartPadding
      : (mergedInputProps.startPadding ?? resolvedStepperStartPadding);
  const resolvedEndPadding =
    usesRightStepper && (endPaddingFromProps === undefined || endPaddingFromProps === 0) ? resolvedStepperEndPadding : (mergedInputProps.endPadding ?? resolvedStepperEndPadding);

  const resolvedInputProps = {
    ...mergedInputProps,
    wrapperClassName: clsx(inputWrapperRecipe, mergedInputProps?.wrapperClassName),
    inputClassName: clsx(
      inputRecipe,
      "[appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none",
      mergedInputProps?.inputClassName,
    ),
    startPadding: resolvedStartPadding,
    endPadding: resolvedEndPadding,
    startContent: mergedInputProps.startContent ?? (usesLeftStepper ? <span aria-hidden className="pointer-events-none" /> : undefined),
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
  const buttonTone = doesStatusEffectInput ? toneForState : tone;
  const makeStepperButton = (kind: "increment" | "decrement", radiusOverride?: RadiusFormat, extraClassName?: string) => {
    const Icon = kind === "increment" ? Plus : Minus;
    return (
      <Button
        {...{
          ...resolvedButtonProps,
          radius: radiusOverride ?? resolvedButtonProps.radius,
          className: clsx(resolvedButtonProps.className, extraClassName),
          mode: "button",
          tone: buttonTone,
          width: "icon",
          textSize,
          disabled: fieldIsDisabled,
        }}
        iconOnly
        aria-label={kind === "increment" ? "Increment value" : "Decrement value"}
        slot={kind}
      >
        <Icon className="aspect-square" style={{ width: `var(--text-${textSize})`, height: `var(--text-${textSize})` }} />
      </Button>
    );
  };

  const renderStepperGroup = (
    wrapperClassName: string | undefined,
    direction: "vertical" | "horizontal" | undefined,
    side: "left" | "right",
    buttons: "both" | "increment" | "decrement" = "both",
  ) => {
    if (!wrapperClassName) return null;

    const resolvedDirection = direction ?? "horizontal";
    const directionClass = resolvedDirection === "vertical" ? "flex-col" : "flex-row";
    const isStackedBoth = resolvedDirection === "vertical" && buttons === "both";
    const isInlineBoth = resolvedDirection === "horizontal" && buttons === "both";
    const gapClass = isStackedBoth || isInlineBoth ? "gap-0" : "gap-2xs";
    const baseRadius = resolvedButtonProps.radius ?? radius;
    const stackedTopRadius: RadiusFormat = [baseRadius as Radius, baseRadius as Radius, "none", "none"];
    const stackedBottomRadius: RadiusFormat = ["none", "none", baseRadius as Radius, baseRadius as Radius];
    const inlineLeftRadius: RadiusFormat = [baseRadius as Radius, "none", "none", baseRadius as Radius];
    const inlineRightRadius: RadiusFormat = ["none", baseRadius as Radius, baseRadius as Radius, "none"];

    const renderButtons = () => {
      if (buttons === "increment") return makeStepperButton("increment");
      if (buttons === "decrement") return makeStepperButton("decrement");

      if (resolvedDirection === "vertical") {
        return (
          <>
            {makeStepperButton("increment", stackedTopRadius)}
            {makeStepperButton("decrement", stackedBottomRadius)}
          </>
        );
      }

      return (
        <>
          {makeStepperButton("decrement", isInlineBoth ? inlineLeftRadius : undefined)}
          {makeStepperButton("increment", isInlineBoth ? inlineRightRadius : undefined)}
        </>
      );
    };

    return (
      <Group className={clsx(wrapperClassName, directionClass, gapClass)} style={side === "left" ? leftTransformStyle : rightTransformStyle}>
        {renderButtons()}
      </Group>
    );
  };

  return (
    <RaNumberField
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
            slot: "input",
            type: "number",
            tone: doesStatusEffectInput ? toneForState : tone,
            status: doesStatusEffectInput ? derivedStatusBase : "default",
            radius: radius,
            width: width,
            textSize,
            disabled: fieldIsDisabled,
            readOnly: fieldIsReadOnly,
            required: fieldIsRequired,
            overlayContent: (
              <>
                {isFloatingVariant && (
                  <Label
                    data-variant={variant}
                    data-tone={tone}
                    className={clsx(
                      "leading-heading transition-all duration-150",
                      `text-${labelTextSize} ${resolvedInputProps.startContent ? `left-${resolvedInputProps.startPadding}` : "left-0"}`,
                      labelRecipe,
                      resolvedInputProps.padding && paddingToClass(resolvedInputProps.padding, "xs"),
                      labelClassName,
                    )}
                  >
                    {label}
                    <span className="text-error">{` ${fieldIsRequired ? "*" : ""}`}</span>
                  </Label>
                )}
                {renderStepperGroup(buttonWrapperRecipe, primaryDirection, primarySide, primaryButtons)}
                {secondarySide ? renderStepperGroup(secondaryButtonWrapperRecipe, secondaryDirection, secondarySide, secondaryButtons) : null}
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
    </RaNumberField>
  );
}
