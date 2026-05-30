import { redirect } from "react-router";

// Redirect typo path /continers -> canonical /overview
export function loader() {
  return redirect("/overview", 301);
}

export default function ContinersRedirect() {
  return null;
}
