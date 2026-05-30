import React from "react";
import type { Route } from "../../.react-router/types/app/routes/+types/sign-in";
import { ArrowRight, Bug, ExternalLink, Lock, Mail, User } from "lucide-react";
import { AuthenticityTokenInput } from "remix-utils/csrf/react";
import { data, Form, redirect, useActionData, useNavigate, useNavigation, useRouteLoaderData, useSearchParams } from "react-router";

import { Button } from "../components/library/buttons/Button";
import { TextField } from "../components/library/forms/fields/TextField";
import { SignInPasswordSchema, SignInSchema, UsernameSchema, type SignInInput } from "../schemas/auth.schemas";
import { CSRF_FORM_DATA_KEY } from "../utils/csrf/constants";
import { withCsrfValidation } from "../utils/csrf/csrfWrapper.server";
import { normalizeReturnTo } from "../utils/auth/return-to";
import { createServerHttpClient } from "../utils/http.server";
import { useZodValues } from "../utils/hooks/useZodValues";
import type { loader as authProviderLoader } from "./layouts/auth-provider";

const initialValues: SignInInput = { username: "", password: "" };
const fieldSchemas = { username: UsernameSchema, password: SignInPasswordSchema };
const sensitiveQueryKeys = new Set(["username", "password"]);
const SUPPORT_ISSUES_URL = "https://github.com/log-forge/logforge/issues";
const SUPPORT_EMAIL = "logforge@gmail.com";
const SUPPORT_MAILTO = `mailto:${SUPPORT_EMAIL}`;

type ActionData = {
  error?: string | { message?: string };
};

function getActionErrorMessage(actionData?: ActionData): string | null {
  if (!actionData?.error) return null;
  if (typeof actionData.error === "string") return actionData.error;
  return actionData.error.message ?? "Unable to sign in. Please try again.";
}

export function meta({}: Route.MetaArgs) {
  return [{ title: "Sign In | LogForge - Central" }, { name: "description", content: "Sign in to LogForge Central" }];
}

export async function loader({ request }: Route.LoaderArgs) {
  const url = new URL(request.url);
  let changed = false;

  for (const key of sensitiveQueryKeys) {
    if (url.searchParams.has(key)) {
      url.searchParams.delete(key);
      changed = true;
    }
  }

  if (changed) {
    return redirect(`/sign-in${url.search}${url.hash}`);
  }

  return null;
}

export const action = withCsrfValidation(async ({ request }: Route.ActionArgs) => {
  const form = await request.formData();
  const parsed = SignInSchema.safeParse({
    username: form.get("username"),
    password: form.get("password"),
  });

  if (!parsed.success) {
    return data<ActionData>({ error: "Enter a valid username and password." }, { status: 400 });
  }

  const safeReturnTo = normalizeReturnTo(new URL(request.url).searchParams.get("returnTo"));
  const client = createServerHttpClient({ base: "auth", request, includeCookies: false });

  try {
    const res = await client.post("/api/auth/sign-in/username", parsed.data, { validateStatus: () => true });
    if (res.status < 200 || res.status >= 300) {
      const payload = (res.data ?? {}) as any;
      return data<ActionData>(
        {
          error: payload?.message ?? payload?.error?.message ?? payload?.code ?? "Unable to sign in. Please try again.",
        },
        { status: res.status },
      );
    }

    const headers = new Headers();
    const setCookie = res.headers["set-cookie"];
    for (const cookie of Array.isArray(setCookie) ? setCookie : setCookie ? [setCookie] : []) {
      headers.append("Set-Cookie", cookie);
    }

    return redirect(safeReturnTo, { headers });
  } catch (_err) {
    return data<ActionData>({ error: "Unable to sign in. Please try again." }, { status: 502 });
  }
});

export default function SignInPage() {
  const navigate = useNavigate();
  const actionData = useActionData<typeof action>();
  const navigation = useNavigation();
  const [searchParams] = useSearchParams();
  const authRouteData = useRouteLoaderData<typeof authProviderLoader>("auth-provider")!;
  const returnToParam = searchParams.get("returnTo");
  const reason = searchParams.get("reason");
  const forceReauth = reason === "reauth" || reason === "backend-auth";
  const safeReturnTo = normalizeReturnTo(returnToParam);
  const { values, setValue, clearFieldError, validateAll, validators, validationErrors } = useZodValues<SignInInput>(initialValues, SignInSchema, fieldSchemas);
  const [submitError, setSubmitError] = React.useState<string | null>(null);
  const isSubmitting = navigation.state === "submitting";
  const actionErrorMessage = getActionErrorMessage(actionData);

  const isUserSignedIn = Boolean(authRouteData.auth.user && authRouteData.auth.session);

  React.useEffect(() => {
    if (forceReauth || !isUserSignedIn) return;
    navigate(safeReturnTo, { replace: true });
  }, [forceReauth, isUserSignedIn, navigate, safeReturnTo]);

  const handleSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    setSubmitError(null);
    if (!validateAll()) event.preventDefault();
  };

  if (isUserSignedIn && !forceReauth) {
    return null;
  }

  return (
    <div className="flex min-h-screen w-full items-center justify-center bg-background p-md">
      <div className="w-full max-w-[680px] rounded-2xl border border-divider/70 bg-background p-lg shadow-[0_12px_40px_color-mix(in_oklab,var(--color-neutral),20%)]">
        <div className="flex flex-col gap-md">
          <div className="flex flex-col gap-3xs">
            <div className="mb-xs">
              <h1 className="text-h4 font-semibold text-text">Central</h1>
              <p className="text-xs text-neutral-text/80">Remote Container Observability</p>
            </div>
            <p className="text-xs tracking-wide text-neutral-text/80 uppercase">Welcome back</p>
            <h2 className="leading-heading text-h5 font-semibold text-text">Sign in to continue</h2>
          </div>

          <Form method="post" className="flex flex-col gap-sm" onSubmit={handleSubmit}>
            <AuthenticityTokenInput name={CSRF_FORM_DATA_KEY} />
            <p className="rounded-md border border-neutral/20 bg-neutral/5 p-2xs text-xs text-neutral-text/80">
              Single-admin deployments use the local administrator configured by <code>CENTRAL_ADMIN_USERNAME</code>. If no first-boot password was provided, check the first-boot auth log.
            </p>
            {forceReauth ? (
              <p className="rounded-md border border-warning/80 bg-warning/20 p-2xs text-xs text-warning-text" role="status" aria-live="polite">
                Session refresh required. Please sign in again.
              </p>
            ) : null}
            {submitError || actionErrorMessage ? (
              <p className="flex w-full flex-col items-start justify-start rounded-md border border-error/80 bg-error/20 p-2xs text-xs text-error" role="alert" aria-live="polite">
                {submitError ?? actionErrorMessage}
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

          <div className="flex flex-col gap-xs border-t border-divider/60 pt-sm text-xs text-neutral-text/80 sm:flex-row sm:items-center sm:justify-between">
            <span className="select-text font-medium text-text">
              Contact us: {SUPPORT_EMAIL}
            </span>
            <div className="flex flex-wrap items-center gap-sm">
              <a
                href={SUPPORT_ISSUES_URL}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-2xs rounded-md px-2xs py-3xs text-neutral-text/80 hover:bg-neutral/5 hover:text-text"
              >
                <Bug className="h-3.5 w-3.5" aria-hidden="true" />
                Report an issue
                <ExternalLink className="h-3 w-3" aria-hidden="true" />
              </a>
              <a href={SUPPORT_MAILTO} className="inline-flex items-center gap-2xs rounded-md px-2xs py-3xs text-neutral-text/80 hover:bg-neutral/5 hover:text-text">
                <Mail className="h-3.5 w-3.5" aria-hidden="true" />
                Contact us
              </a>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
