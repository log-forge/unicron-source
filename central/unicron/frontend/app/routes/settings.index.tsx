import { redirect, type LoaderFunctionArgs } from "react-router";

export async function loader(_args: LoaderFunctionArgs) {
  throw redirect("/settings/account");
}

export default function SettingsIndexRoute() {
  return null;
}
