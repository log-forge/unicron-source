import { Clock3, Database, HardDrive } from "lucide-react";

import SettingsSubtabs from "../components/settings/SettingsSubtabs";
import { buildTelemetryStorageSettings } from "../utils/telemetryStorageSettings";

export function meta() {
  return [{ title: "Storage - Settings - Unicron" }, { name: "description", content: "View telemetry retention and storage controls" }];
}

export default function StorageSettingsPage() {
  const settings = buildTelemetryStorageSettings();

  return (
    <div className="flex w-full flex-col gap-lg">
      <div className="flex flex-col gap-sm">
        <div className="flex items-center gap-xs">
          <HardDrive className="h-5 w-5 text-primary" />
          <h1 className="text-2xl font-bold text-text">Storage</h1>
        </div>
        <p className="text-sm text-neutral">Telemetry retention and storage limits for this appliance.</p>
      </div>

      <SettingsSubtabs />

      <section className="rounded-xl border border-neutral/20 bg-background p-md">
        <div className="flex flex-col gap-xs sm:flex-row sm:items-center sm:justify-between">
          <div className="flex min-w-0 items-center gap-xs">
            <Clock3 className="h-5 w-5 text-primary" />
            <h2 className="text-sm font-semibold text-text">Retention</h2>
          </div>
        </div>
        <div className="mt-sm grid gap-sm sm:grid-cols-2">
          {settings.retention.map((row) => (
            <div key={row.key} className="border-l-2 border-primary/40 pl-sm">
              <p className="text-xs font-medium text-neutral uppercase">{row.label}</p>
              <p className="mt-1 text-lg font-semibold text-text">{row.value}</p>
            </div>
          ))}
        </div>
        <p className="mt-sm text-xs text-neutral">
          Retention is rolling and asynchronous; aged-out data is removed after it falls outside the window.
        </p>
      </section>

      <section className="rounded-xl border border-neutral/20 bg-background p-md">
        <div className="flex flex-col gap-xs sm:flex-row sm:items-center sm:justify-between">
          <div className="flex min-w-0 items-center gap-xs">
            <Database className="h-5 w-5 text-primary" />
            <h2 className="text-sm font-semibold text-text">Storage Limits</h2>
          </div>
        </div>
        <div className="mt-sm grid gap-sm lg:grid-cols-2">
          {settings.storageLimits.map((control) => (
            <div key={control.key} className="grid gap-xs">
              <label htmlFor={control.key} className="text-sm font-medium text-text">
                {control.label}
              </label>
              <div className="grid grid-cols-[minmax(0,1fr)_96px] gap-xs">
                <input
                  id={control.key}
                  type="text"
                  value={control.value}
                  readOnly
                  disabled={control.disabled}
                  className="min-w-0 rounded-md border border-neutral/20 bg-neutral/5 px-sm py-xs text-sm text-neutral outline-none disabled:cursor-not-allowed disabled:opacity-70"
                />
                <select
                  aria-label={`${control.label} unit`}
                  defaultValue={control.unit}
                  disabled={control.disabled}
                  className="rounded-md border border-neutral/20 bg-neutral/5 px-sm py-xs text-sm text-neutral outline-none disabled:cursor-not-allowed disabled:opacity-70"
                >
                  <option value="bytes">bytes</option>
                  <option value="gb">GB</option>
                </select>
              </div>
              <p className="text-xs text-neutral">No size cap is configured.</p>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
