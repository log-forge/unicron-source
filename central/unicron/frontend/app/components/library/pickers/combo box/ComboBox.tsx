import * as React from "react";
import { ComboBox as RaComboBox, FieldError, Label, ListBox, Popover, Text } from "react-aria-components";
import { toneRecepies, type ComboBoxButtonProps, type ComboBoxInputProps, type ComboBoxProps } from "./combo-box.styles";
import { ChevronsUpDown } from "lucide-react";
import { Input } from "../../forms/Input";
import { Button } from "../../buttons/Button";
import ListBoxItem from "../ListBoxItem";
import clsx from "clsx";
import { getYPaddingToken, paddingToClass, radiusToClass, statusToTone } from "../../components.styles";
import type { Key } from "react";

const defaultInputProps: ComboBoxInputProps = {
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

const defaultButtonProps: ComboBoxButtonProps = { variant: "solid", radius: "md", padding: "4xs", className: "" };

function ComboBox<T extends object>({
  variant = "stacked",
  popoverVariant = "solid",
  tone = "default",
  status = "default",
  width = "full",
  radius = "md",
  popoverRadius = "md",
  padding = 0,
  popoverPadding = "3xs",
  gap = "3xs",
  labelGap = "3xs",
  messageGap = "4xs",
  listBoxGap = "4xs",
  textSize = "sm",
  labelTextSize = "sm",
  messageTextSize = "xs",
  doesStatusEffectInput = false,
  doesStatusEffectLabel = false,
  doesStatusEffectDescription = false,
  popoverClassName = "",
  listBoxClassName = "",
  labelClassName = "",
  descriptionClassName = "",
  messageClassName = "",
  label,
  description,
  errorMessage,
  children,
  inputProps,
  buttonProps,
  className,
  ...rest
}: ComboBoxProps<T>) {
  const {
    isInvalid: comboIsInvalid,
    isDisabled: comboIsDisabled,
    isReadOnly: comboIsReadOnly,
    isRequired: comboIsRequired,
    inputValue,
    defaultInputValue,
    selectedKey,
    defaultSelectedKey,
    onInputChange,
    onSelectionChange,
    ...restComboProps
  } = rest;
  const deriveHasValue = (maybeValue: unknown) => maybeValue !== null && maybeValue !== undefined && `${maybeValue}` !== "";
  const [hasValue, setHasValue] = React.useState(() => deriveHasValue(inputValue ?? defaultInputValue ?? selectedKey ?? defaultSelectedKey));
  const [measuredTriggerWidth, setMeasuredTriggerWidth] = React.useState<string | null>(null);
  const selectionRef = React.useRef<Key | null>(selectedKey ?? defaultSelectedKey ?? null);
  const triggerRef = React.useRef<HTMLDivElement | null>(null);

  const measureTriggerWidth = React.useCallback(() => {
    if (!triggerRef.current) return;

    const width = triggerRef.current.offsetWidth;

    if (width > 0) setMeasuredTriggerWidth(`${width}px`);
  }, []);

  React.useEffect(() => {
    selectionRef.current = selectedKey ?? null;
  }, [selectedKey]);

  React.useEffect(() => {
    measureTriggerWidth();
    if (typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(measureTriggerWidth);
    if (triggerRef.current) ro.observe(triggerRef.current);
    return () => ro.disconnect();
  }, [measureTriggerWidth]);

  const allowsCustomValue = restComboProps.allowsCustomValue ?? false;
  const isFloatingVariant = variant === "floating" || variant === "nested_floating";
  const isNestedFloatingVariant = variant === "nested_floating";
  const derivedStatusBase = comboIsInvalid ? "error" : status;
  const toneForState = doesStatusEffectInput ? statusToTone(derivedStatusBase, tone) : tone;
  const baseRecipe = toneRecepies(variant, tone, popoverVariant);
  const statusRecipe = toneRecepies(variant, toneForState, popoverVariant);
  const labelRecipe = doesStatusEffectLabel ? statusRecipe.label : baseRecipe.label;
  const descriptionRecipe = doesStatusEffectDescription ? statusRecipe.description : baseRecipe.description;

  const mergedInputProps = { ...defaultInputProps, ...inputProps };
  const mergedButtonProps = { ...defaultButtonProps, ...buttonProps };

  const resolvedInputProps = {
    ...mergedInputProps,
    wrapperClassName: clsx(statusRecipe.inputWrapper, mergedInputProps?.wrapperClassName),
    inputClassName: clsx(statusRecipe.input, mergedInputProps?.inputClassName),
    style: isNestedFloatingVariant
      ? { marginTop: `var(--text-${textSize})`, marginBottom: `var(--text-${textSize})`, ...mergedInputProps.style }
      : isFloatingVariant
        ? { marginTop: `calc(var(--text-${textSize}) * 1/4)`, marginBottom: `calc(var(--text-${textSize}) * 1/4)`, ...mergedInputProps.style }
        : { ...mergedInputProps.style },
  };
  const restButtonProps = {
    ...mergedButtonProps,
    className: clsx(statusRecipe.button, mergedButtonProps?.className),
  };

  const yPaddingToken = getYPaddingToken(resolvedInputProps.padding, "4xs");
  const spacingToVar = (token: Spacing | 0 | undefined) => (token === 0 ? "0px" : `var(--spacing-${token ?? "0"})`);
  const popoverInlineStyle: React.CSSProperties = {
    ["--trigger-width" as any]: measuredTriggerWidth ?? undefined,
    width: "var(--trigger-width)",
    minWidth: "var(--trigger-width)",
    maxWidth: "min(28rem, calc(100vw - 2rem))",
    maxHeight: "min(20rem, calc(100vh - 6rem))",
    overflowY: "auto",
    transformOrigin: "var(--trigger-anchor-point, center top)",
  };

  React.useEffect(() => {
    if (inputValue !== undefined) setHasValue(deriveHasValue(inputValue));
  }, [inputValue]);

  React.useEffect(() => {
    if (inputValue !== undefined) return;
    if (selectedKey !== undefined) setHasValue(deriveHasValue(selectedKey));
  }, [inputValue, selectedKey]);

  const handleInputChange: ComboBoxProps<T>["onInputChange"] = (value) => {
    setHasValue(deriveHasValue(value));
    if (!deriveHasValue(value)) selectionRef.current = null;
    onInputChange?.(value);
  };

  const handleSelectionChange: ComboBoxProps<T>["onSelectionChange"] = (key) => {
    selectionRef.current = key ?? null;
    setHasValue(deriveHasValue(key));
    onSelectionChange?.(key);
  };

  const handleInputBlur: React.FocusEventHandler<HTMLInputElement> = (event) => {
    const currentValue = event.currentTarget.value;
    if (!allowsCustomValue && !selectionRef.current) {
      if (currentValue !== "") {
        onInputChange?.("");
        event.currentTarget.value = "";
      }
      setHasValue(false);
    } else {
      setHasValue(deriveHasValue(currentValue));
    }
    mergedInputProps?.onBlur?.(event);
  };

  return (
    <RaComboBox
      data-tone={toneForState}
      data-variant={variant}
      data-has-value={hasValue ? "true" : "false"}
      onInputChange={handleInputChange}
      onSelectionChange={handleSelectionChange}
      {...{ ...restComboProps }}
      isInvalid={comboIsInvalid}
      isDisabled={comboIsDisabled}
      isReadOnly={comboIsReadOnly}
      isRequired={comboIsRequired}
      allowsEmptyCollection
      className={clsx("group/combobox", `gap-${messageGap}`, baseRecipe.wrapper, className)}
    >
      <div className={clsx(statusRecipe.wrapper, `gap-${labelGap}`)}>
        {label && !isFloatingVariant && (
          <Label data-variant={variant} data-tone={tone} className={clsx(`leading-heading text-${labelTextSize}`, labelRecipe, labelClassName)}>
            {label}
            <span className="text-error">{` ${comboIsRequired ? "*" : ""}`}</span>
          </Label>
        )}

        <div ref={triggerRef} className={clsx("relative flex flex-row items-center justify-start", statusRecipe.controlWrapper, `gap-${gap}`, radiusToClass(radius))}>
          <Input
            {...{
              ...resolvedInputProps,
              tone: toneForState,
              width: "full",
              textSize,
              status,
              radius,
              disabled: comboIsDisabled,
              readOnly: comboIsReadOnly,
              required: comboIsRequired,
              onBlur: handleInputBlur,
            }}
            overlayContent={
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
                    <span className="text-error">{` ${rest.isRequired ? "*" : ""}`}</span>
                  </Label>
                )}
                <span
                  className={clsx("absolute inset-y-0 right-0 flex min-h-0 min-w-0 items-center justify-center", statusRecipe.buttonWrapper)}
                  style={{ transform: `translateX(calc(${spacingToVar(yPaddingToken)} * -1))` }}
                >
                  <Button
                    {...{
                      ...restButtonProps,
                      mode: "button",
                      tone: toneForState,
                      width: "icon",
                      textSize,
                      disabled: comboIsDisabled,
                    }}
                    iconOnly
                    aria-label={(restButtonProps as any)["aria-label"] ?? "Toggle options"}
                  >
                    <ChevronsUpDown className="aspect-square" style={{ width: `var(--text-${textSize})`, height: `var(--text-${textSize})` }} />
                  </Button>
                </span>
                {mergedInputProps.overlayContent ? mergedInputProps.overlayContent : undefined}
              </>
            }
          />
        </div>
      </div>

      <span className={clsx("flex flex-col items-start justify-start", `gap-${messageGap}`)}>
        {description && (
          <Text slot="description" className={clsx("leading-body", `text-${messageTextSize}`, descriptionRecipe, descriptionClassName)}>
            {description}
          </Text>
        )}
        <FieldError className={clsx("leading-body", `text-${messageTextSize}`, statusRecipe.fieldError, messageClassName)}>{errorMessage}</FieldError>
      </span>

      <Popover
        data-tone={toneForState}
        data-variant={variant}
        className={clsx("mt-4xs", radiusToClass(popoverRadius), paddingToClass(popoverPadding, "xs"), statusRecipe.popover, popoverClassName)}
        style={{
          ...popoverInlineStyle,
        }}
      >
        <ListBox
          data-tone={toneForState}
          data-variant={variant}
          className={clsx("flex w-full flex-col overflow-y-auto outline-none focus-visible:outline-none", `gap-${listBoxGap}`, statusRecipe.listBox, listBoxClassName)}
          renderEmptyState={() => <div className={"w-full text-center align-middle"}>No results found</div>}
        >
          {children}
        </ListBox>
      </Popover>
    </RaComboBox>
  );
}

export { ComboBox, ListBoxItem };
