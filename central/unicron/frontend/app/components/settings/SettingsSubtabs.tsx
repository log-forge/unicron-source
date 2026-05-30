import { useLocation, useNavigate } from "react-router";

type SettingsTab = {
  key: "account" | "agents" | "origins" | "storage";
  label: string;
  to: string;
};

const SETTINGS_TABS: SettingsTab[] = [
  { key: "account", label: "Account", to: "/settings/account" },
  { key: "agents", label: "Agents", to: "/settings/agents" },
  { key: "origins", label: "Origins", to: "/settings/origins" },
  { key: "storage", label: "Storage", to: "/settings/storage" },
];

export default function SettingsSubtabs() {
  const navigate = useNavigate();
  const location = useLocation();
  const activeTab = location.pathname.includes("/settings/origins")
    ? "origins"
    : location.pathname.includes("/settings/storage")
      ? "storage"
    : location.pathname.includes("/settings/agents")
      ? "agents"
      : "account";

  return (
    <div className="flex max-w-full w-fit items-center gap-1 overflow-x-auto rounded-lg border border-neutral/20 bg-neutral/5 p-1 whitespace-nowrap [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
      {SETTINGS_TABS.map((tab) => {
        const selected = tab.key === activeTab;
        return (
          <button
            key={tab.key}
            type="button"
            onClick={() => navigate(tab.to)}
            className={`shrink-0 rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
              selected
                ? "bg-primary text-white"
                : "cursor-pointer text-neutral hover:bg-neutral/10 hover:text-text"
            }`}
          >
            {tab.label}
          </button>
        );
      })}
    </div>
  );
}
