import { Outlet } from "react-router";

export function shouldRevalidate({ formMethod }: { formMethod?: string | null }) {
  return Boolean(formMethod && formMethod.toLowerCase() !== "get");
}

export default function DeploymentOrgRequiredLayout() {
  return <Outlet />;
}
