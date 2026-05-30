import React from "react";
import { ArrowRight, Lock, User } from "lucide-react";
import { Form } from "react-aria-components";
import { useNavigate } from "react-router";
import { Button } from "../../library/buttons/Button";
import { TextField } from "../../library/forms/fields/TextField";
import { useAuth } from "../../../context/AuthContext";
import type { ModalInjectedProps } from "../../../context/ModalContext";
import { SignInPasswordSchema, SignInSchema, UsernameSchema, type SignInInput } from "../../../schemas/auth.schemas";
import { normalizeReturnTo } from "../../../utils/auth/return-to";
import { signInWithUsername } from "../../../utils/auth/auth-client";
import { useZodValues } from "../../../utils/hooks/useZodValues";

const initialValues: SignInInput = { username: "", password: "" };
const fieldSchemas = { username: UsernameSchema, password: SignInPasswordSchema };

type SignInModalProps = ModalInjectedProps & { returnTo?: string };

export default function SignInModal({ closeModal, returnTo }: SignInModalProps) {
  const navigate = useNavigate();
  const { refetch, isAuthenticated } = useAuth();
  const { values, setValue, clearFieldError, validateAll, validators, validationErrors, formValidationErrors } = useZodValues<SignInInput>(
    initialValues,
    SignInSchema,
    fieldSchemas,
  );
  const [isSubmitting, setIsSubmitting] = React.useState(false);
  const [submitError, setSubmitError] = React.useState<string | null>(null);

  const safeReturnTo = returnTo != null ? normalizeReturnTo(returnTo) : null;

  React.useEffect(() => {
    if (!isAuthenticated) return;

    if (safeReturnTo) navigate(safeReturnTo);
    closeModal?.();
  }, [closeModal, isAuthenticated, navigate, safeReturnTo]);

  const handleAuthSuccess = React.useCallback(async () => {
    await refetch();
    closeModal?.();
    if (safeReturnTo) navigate(safeReturnTo);
  }, [closeModal, navigate, refetch, safeReturnTo]);

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSubmitError(null);
    if (!validateAll()) return;

    setIsSubmitting(true);
    try {
      const { error } = await signInWithUsername({ username: values.username, password: values.password });

      if (error) {
        setSubmitError(error.message ?? "Unable to sign in. Please try again.");
        return;
      }

      await handleAuthSuccess();
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : "Unable to sign in. Please try again.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="flex flex-col gap-md">
      <div className="flex flex-col gap-3xs">
        <p className="text-xs tracking-wide text-neutral-text/80 uppercase">Welcome back</p>
        <h2 className="leading-heading text-h5 font-semibold text-text">Sign in to continue</h2>
      </div>

      <Form className="flex flex-col gap-sm" onSubmit={handleSubmit} validationBehavior="native" validationErrors={formValidationErrors}>
        {submitError ? (
          <p className="flex w-full flex-col items-start justify-start rounded-md border border-error/80 bg-error/20 p-2xs text-xs text-error" role="alert" aria-live="polite">
            {submitError}
          </p>
        ) : null}
        <div className="grid gap-xs">
          <TextField
            name="username"
            type="text"
            label="Username"
            textSize="sm"
            labelTextSize="sm"
            labelClassName="font-bold"
            padding={0}
            isRequired
            isDisabled={isSubmitting}
            isInvalid={Boolean(validationErrors.username?.length)}
            validate={validators.username}
            errorMessage={(validation) => validationErrors.username?.[0] ?? validation.validationErrors?.[0] ?? validators.username?.(values.username) ?? ""}
            inputProps={{
              autoComplete: "username",
              value: values.username,
              onChange: (event) => {
                clearFieldError("username");
                setValue("username")(event.currentTarget.value);
              },
              startContent: <User style={{ height: "var(--text-base)" }} aria-hidden="true" />,
              startPadding: "md",
              placeholder: "admin",
            }}
          />
          <TextField
            name="password"
            type="password"
            label="Password"
            textSize="sm"
            labelTextSize="sm"
            labelClassName="font-bold"
            padding={0}
            isRequired
            isDisabled={isSubmitting}
            isInvalid={Boolean(validationErrors.password?.length)}
            validate={validators.password}
            errorMessage={(validation) => validationErrors.password?.[0] ?? validation.validationErrors?.[0] ?? validators.password?.(values.password) ?? ""}
            inputProps={{
              autoComplete: "current-password",
              value: values.password,
              onChange: (event) => {
                clearFieldError("password");
                setValue("password")(event.currentTarget.value);
              },
              startContent: <Lock className="h-sm w-sm" aria-hidden="true" />,
              startPadding: "md",
              placeholder: "Enter password",
            }}
          />
        </div>

        <Button type="submit" width="full" tone="primary" textSize="sm" padding={["xs", "3xs"]} className="mt-2xs" isDisabled={isSubmitting} isPending={isSubmitting}>
          <span className="flex flex-row items-center justify-center gap-sm font-semibold">
            <span>Sign in</span>
            <ArrowRight className="h-xs w-xs" strokeWidth={2} aria-hidden="true" />
          </span>
        </Button>
      </Form>
    </div>
  );
}
