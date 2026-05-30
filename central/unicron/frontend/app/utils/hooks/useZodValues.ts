import React from "react";
import { flattenError, type z } from "zod";

type Validators<T> = Partial<Record<keyof T, (value: unknown) => string | null>>;
type ValidationErrorMap = Record<string, string[]>;
type AnyZod = z.ZodType<any, any, any>;

export function useZodValues<T extends Record<string, unknown>>(initialValues: T, formSchema: z.ZodType<T>, fieldSchemas: Partial<Record<keyof T, AnyZod>> = {}) {
  const [values, setValues] = React.useState<T>(initialValues);
  const [validationErrors, setValidationErrors] = React.useState<ValidationErrorMap>({});

  const clearFieldError = React.useCallback((field: keyof T) => {
    setValidationErrors((prev) => {
      const next = { ...prev };
      delete next[field as string];
      return next;
    });
  }, []);

  const validators = React.useMemo(() => {
    const normalize = (val: unknown) => (typeof val === "string" ? val : val == null ? "" : String(val));

    return Object.fromEntries(
      Object.entries(fieldSchemas).map(([key, schema]) => [
        key,
        (value: unknown) => {
          const result = (schema as AnyZod).safeParse(normalize(value));
          return result.success ? null : (result.error.issues[0]?.message ?? "Invalid");
        },
      ]),
    ) as Validators<T>;
  }, [fieldSchemas]);

  const setValue = React.useCallback(
    (field: keyof T) => (value: string) => {
      setValues((prev) => ({ ...prev, [field]: value }));

      const validator = validators[field];
      if (!validator) return;

      const message = validator(value);
      setValidationErrors((prev) => {
        const next = { ...prev };
        if (message) next[field as string] = [message];
        else delete next[field as string];

        return next;
      });
    },
    [validators],
  );

  const validateAll = React.useCallback(() => {
    const parsed = formSchema.safeParse(values);
    if (!parsed.success) {
      setValidationErrors(flattenError(parsed.error).fieldErrors as ValidationErrorMap);
      return false;
    }

    setValidationErrors({});
    return true;
  }, [formSchema, values]);

  const formValidationErrors = React.useMemo(
    () => Object.fromEntries(Object.entries(validationErrors).filter(([, msgs]) => Array.isArray(msgs) && msgs.length > 0)) as ValidationErrorMap,
    [validationErrors],
  );

  return { values, setValue, clearFieldError, validateAll, validators, validationErrors, formValidationErrors, setValidationErrors };
}
