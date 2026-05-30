import { ShieldCheck, UsersRound } from "lucide-react";

import SettingsSubtabs from "../components/settings/SettingsSubtabs";

export function meta() {
  return [
    { title: "Users & Access - Settings - Unicron" },
    { name: "description", content: "Manage users, teams, roles, and scoped access" },
  ];
}

export default function UsersAccessPage() {
  return (
    <div className="flex w-full flex-col gap-lg">
      <div className="flex flex-col gap-sm">
        <div className="flex items-center gap-xs">
          <UsersRound className="h-5 w-5 text-primary" />
          <h1 className="text-2xl font-bold text-text">Users & Access</h1>
        </div>
      </div>

      <SettingsSubtabs />

      <div className="rounded-lg border border-neutral/20 bg-background p-md">
        <div className="flex items-center gap-xs">
          <ShieldCheck className="h-5 w-5 text-primary" />
          <h2 className="text-sm font-semibold text-text">Local Administrator Access</h2>
        </div>
        <div className="mt-sm space-y-xs text-sm text-neutral">
          <p>This appliance uses one local administrator account.</p>
          <p>Container and agent actions are authorized through that signed-in local administrator session.</p>
        </div>
      </div>
    </div>
  );
}
