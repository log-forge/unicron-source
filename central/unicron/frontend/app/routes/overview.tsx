import { redirect } from "react-router";

// Redirect to canonical main page path
export function loader() {
  return redirect("/overview", 301);
}

export default function Overview() {
  return null;
}
