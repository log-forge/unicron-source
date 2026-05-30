// Checkbox.tsx (fixed)
import { Checkbox as RaCheckbox, Text, FieldError } from "react-aria-components";
import { labelPlacementToClass, toneRecepies, type CheckboxProps } from "./checkbox.styles";
import { Check, Minus } from "lucide-react";
import { Button } from "../buttons/Button";
import clsx from "clsx";
import { paddingToClass, statusToTone, widthToClass } from "../components.styles";

export default function Checkbox({
  label = "",
  variant = "solid",
  tone = "default",
  status = "default",
  size = "sm",
  width = "content",
  labelPlacement = "right",
  padding = "3xs",
  radius = "sm",
  gap = "xs",
  messageGap = "3xs",
  labelTextSize = "base",
  messageTextSize = "xs",
  doesStatusEffectLabel = true,
  doesStatusEffectDescription = true,
  description,
  errorMessage,
  className,
  controlClassName,
  inputClassName,
  labelClassName,
  descriptionClassName,
  messageClassName,
  children,
  ...rest
}: CheckboxProps) {
  const derivedStatusBase = rest.isInvalid ? "error" : status;
  const toneForState = statusToTone(derivedStatusBase, tone);
  const baseRecipe = toneRecepies(variant, tone);
  const statusRecipe = toneRecepies(variant, toneForState);

  return (
    <RaCheckbox
      {...rest}
      data-variant={variant}
      data-tone={toneForState}
      className={clsx(
        "group/checkbox relative flex flex-col items-start justify-start select-none",
        "transition-[color,background,box-shadow] duration-150 ease-out",
        "data-disabled:cursor-not-allowed data-disabled:opacity-60",
        `gap-${messageGap}`,
        widthToClass(width),
        paddingToClass(padding),
        statusRecipe.wrapper,
        className,
      )}
    >
      {({ isSelected, isIndeterminate, isDisabled, isInvalid, isRequired, isFocusVisible }) => {
        const derivedStatus = isInvalid ? "error" : derivedStatusBase;
        const labelRecipe = doesStatusEffectLabel ? statusRecipe : baseRecipe;
        const descriptionRecipe = doesStatusEffectDescription ? statusRecipe : baseRecipe;
        const resolvedLabel = label || children;

        return (
          <>
            <div className={clsx("flex", `gap-${gap}`, labelPlacementToClass(labelPlacement), controlClassName)}>
              {/* purely visual control; clicks bubble to the RaCheckbox label */}
              <Button
                iconOnly
                variant={variant}
                tone={toneForState}
                textSize={size}
                padding="4xs"
                radius={radius}
                isDisabled={isDisabled}
                className={clsx("pointer-events-none", statusRecipe.control, isFocusVisible && statusRecipe.focusRing, inputClassName)}
                aria-hidden
              >
                {isIndeterminate ? (
                  <Minus
                    style={{
                      height: `var(--text-${size})`,
                      width: `var(--text-${size})`,
                    }}
                  />
                ) : isSelected ? (
                  <Check
                    style={{
                      height: `var(--text-${size})`,
                      width: `var(--text-${size})`,
                    }}
                  />
                ) : (
                  <Minus
                    className="text-transparent"
                    style={{
                      height: `var(--text-${size})`,
                      width: `var(--text-${size})`,
                    }}
                  />
                )}
              </Button>

              {resolvedLabel && (
                <span className={clsx("flex flex-col items-start justify-start", `gap-${messageGap} text-${labelTextSize}`, labelRecipe.label, labelClassName)}>
                  {resolvedLabel}
                  {isRequired && <span className="text-error">{` *`}</span>}

                  {description && (
                    <Text
                      data-variant={variant}
                      data-tone={toneForState}
                      slot="description"
                      className={clsx(`pointer-events-none text-${messageTextSize}`, descriptionRecipe.description, descriptionClassName)}
                    >
                      {description}
                    </Text>
                  )}

                  <FieldError
                    data-variant={variant}
                    data-tone={toneForState}
                    className={clsx(`pointer-events-none text-error text-${messageTextSize}`, statusRecipe.message, messageClassName)}
                  >
                    {errorMessage}
                  </FieldError>
                </span>
              )}
            </div>

            {/* {description && (
              <Text data-variant={variant} data-tone={toneForState} slot="description" className={clsx(`pointer-events-none text-${descriptionTextSize}`, descriptionClassName)}>
                {description}
              </Text>
            )}

            <FieldError data-variant={variant} data-tone={toneForState} className={clsx(`pointer-events-none text-error text-${messageTextSize}`, messageClassName)}>
              {errorMessage}
            </FieldError> */}
          </>
        );
      }}
    </RaCheckbox>
  );
}
