import type { Route } from "../../../.react-router/types/app/routes/showcases/+types/tabs-showcase";
import { useMemo, useState, type ReactNode } from "react";
import clsx from "clsx";
import Tabs, { Tab, TabList, TabPanel } from "../../components/library/Tabs/Tabs";
import type { TabsTone, TabsVariant } from "../../components/library/Tabs/tabs.styles";
import type { BaseWidthMode, PaddingFormat, RadiusFormat } from "../../components/library/components.styles";
import Checkbox from "../../components/library/forms/Checkbox";

export function meta({}: Route.MetaArgs) {
  return [{ title: "Tabs Showcase | Unicron" }];
}

const TAB_ITEMS = [
  {
    id: "overview",
    label: "Overview",
    description: "High-level metrics and a quick read on the current selection.",
  },
  {
    id: "analytics",
    label: "Analytics",
    description: "Trends, comparisons, and anomaly signals to investigate further.",
  },
  {
    id: "reports",
    label: "Reports",
    description: "Download summaries or schedule exports for downstream teams.",
  },
  {
    id: "settings",
    label: "Settings",
    description: "Tune thresholds, alerting preferences, and personalization.",
  },
];

const VARIANT_OPTIONS: TabsVariant[] = ["underline", "text", "pill", "subtle", "solid"];
const TONE_OPTIONS: TabsTone[] = ["default", "primary", "secondary", "success", "warning", "error", "neutral"];
const ORIENTATION_OPTIONS: Array<"horizontal" | "vertical"> = ["horizontal", "vertical"];
const JUSTIFY_OPTIONS: Array<"start" | "end"> = ["start", "end"];
const WIDTH_OPTIONS: BaseWidthMode[] = ["full", "content"];
const RADIUS_OPTIONS: Radius[] = ["none", "sm", "md", "lg", "full"];
const SPACING_OPTIONS: Spacing[] = ["0", "4xs", "3xs", "2xs", "xs", "sm", "md", "lg"];
const OPTIONAL_SPACING_OPTIONS: Spacing[] = ["0", "4xs", "3xs", "2xs", "xs", "sm", "md", "lg"];
const FONT_SIZE_OPTIONS: FontSize[] = ["xs", "sm", "base", "h5", "h4", "h3"];
const controlInputClass =
  "w-full rounded-md border border-divider bg-background px-sm py-2xs text-sm text-text shadow-sm focus-visible:border-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500";

const VARIANT_COPY: Record<TabsVariant, { title: string; description: string }> = {
  underline: {
    title: "Underline",
    description: "Classic navigation styling with a sliding bar that follows focus and selection.",
  },
  text: {
    title: "Text",
    description: "Minimal, low-ink tabs that emphasize typography over chrome.",
  },
  pill: {
    title: "Pill",
    description: "Rounded pills with filled or outlined states for high-emphasis navigation.",
  },
  subtle: {
    title: "Subtle",
    description: "Gentle hover and active treatments for quiet surfaces.",
  },
  solid: {
    title: "Solid",
    description: "Bold, high-contrast buttons with elevation cues for the active tab.",
  },
};

export default function TabsShowcase() {
  return (
    <div className="flex w-full flex-col gap-lg pb-4xl">
      <header className="space-y-3 text-center">
        <h1 className="text-gradient bg-linear-to-r from-primary-500 to-secondary-500 bg-clip-text text-5xl font-bold text-transparent">Tabs Showcase</h1>
        <p className="text-base text-neutral-text">Preview every Tabs variant, tone, and layout with live controls for spacing, alignment, and behavior.</p>
      </header>

      <VariantGallery />

      <TabsPlayground />
    </div>
  );
}

function VariantGallery() {
  return (
    <section className="grid w-full gap-md rounded-lg border border-divider bg-foreground/20 p-lg">
      <div className="space-y-2">
        <h2 className="text-h4 font-semibold text-text">Variant gallery</h2>
        <p className="text-sm text-neutral-text">See how each variant looks across the full tone palette.</p>
      </div>

      <div className="space-y-md">
        {VARIANT_OPTIONS.map((variant) => (
          <div key={variant} className="space-y-sm rounded-lg border border-divider/70 bg-background/80 p-md">
            <div className="flex items-start justify-between gap-sm">
              <div>
                <h3 className="text-base font-semibold text-text">{VARIANT_COPY[variant].title}</h3>
                <p className="text-xs text-neutral-text">{VARIANT_COPY[variant].description}</p>
              </div>
              <span className="rounded-full bg-foreground/20 px-sm py-2xs text-2xs font-semibold tracking-wide text-neutral uppercase">{variant}</span>
            </div>
            <div className="grid gap-sm md:grid-cols-2">
              {TONE_OPTIONS.map((tone) => (
                <VariantTonePreview key={`${variant}-${tone}`} variant={variant} tone={tone} />
              ))}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function VariantTonePreview({ variant, tone }: { variant: TabsVariant; tone: TabsTone }) {
  const [selectedKey, setSelectedKey] = useState<string>(TAB_ITEMS[0].id);

  return (
    <div className="flex flex-col gap-3 rounded-lg border border-divider/70 bg-alt-background p-md">
      <div className="flex items-center justify-between text-sm text-neutral-text">
        <span className="font-semibold text-text capitalize">{tone}</span>
        <span className="text-2xs tracking-wide text-neutral uppercase">{variant}</span>
      </div>
      <Tabs selectedKey={selectedKey} onSelectionChange={(key) => setSelectedKey(String(key))} className="flex-col gap-sm">
        <TabList variant={variant} tone={tone} gap="xs" padding={["xs", "4xs"]} textSize="sm" disableBorder width="full">
          {TAB_ITEMS.map((tab) => (
            <Tab key={tab.id} id={tab.id} radius="md" padding={["2xs", "4xs"]} textSize="sm">
              {tab.label}
            </Tab>
          ))}
        </TabList>
        {TAB_ITEMS.map((tab) => (
          <TabPanel key={tab.id} className="rounded-md border border-divider bg-foreground/10 p-sm text-sm text-neutral-text">
            {tab.description}
          </TabPanel>
        ))}
      </Tabs>
    </div>
  );
}

function TabsPlayground() {
  const [selectedKey, setSelectedKey] = useState<string>(TAB_ITEMS[0].id);
  const [orientation, setOrientation] = useState<"horizontal" | "vertical">("horizontal");
  const [justify, setJustify] = useState<"start" | "end">("start");
  const [variant, setVariant] = useState<TabsVariant>("underline");
  const [tone, setTone] = useState<TabsTone>("default");
  const [listGap, setListGap] = useState<Spacing>("sm");
  const [listPaddingX, setListPaddingX] = useState<Spacing>("sm");
  const [listPaddingY, setListPaddingY] = useState<Spacing>("4xs");
  const [tabPaddingX, setTabPaddingX] = useState<Spacing>("xs");
  const [tabPaddingY, setTabPaddingY] = useState<Spacing>("4xs");
  const [tabRadius, setTabRadius] = useState<RadiusFormat>("md");
  const [textSize, setTextSize] = useState<FontSize>("base");
  const [listWidth, setListWidth] = useState<BaseWidthMode>("full");
  const [disableBorder, setDisableBorder] = useState(false);
  const [animated, setAnimated] = useState(true);
  const [persistSelection, setPersistSelection] = useState(false);
  const [domIdPrefix, setDomIdPrefix] = useState("tabs-demo");

  const listPadding = useMemo<PaddingFormat>(() => (listPaddingX === listPaddingY ? listPaddingX : [listPaddingX, listPaddingY]), [listPaddingX, listPaddingY]);
  const tabPadding = useMemo<PaddingFormat>(() => (tabPaddingX === tabPaddingY ? tabPaddingX : [tabPaddingX, tabPaddingY]), [tabPaddingX, tabPaddingY]);

  const tabsLayoutClass = orientation === "vertical" ? (justify === "end" ? "flex-row-reverse" : "flex-row") : justify === "end" ? "flex-col-reverse" : "flex-col";

  const domPreviewIds = useMemo(() => {
    const prefix = domIdPrefix.trim();
    return TAB_ITEMS.map((tab) => (prefix ? `${prefix}-${tab.id}` : tab.id)).join(", ");
  }, [domIdPrefix]);

  return (
    <section className="grid w-full gap-md rounded-lg border border-divider bg-foreground/20 p-lg">
      <div className="space-y-2">
        <h2 className="text-h4 font-semibold text-text">Playground controls</h2>
        <p className="text-sm text-neutral-text">Dial in alignment, spacing, tone, and animation to match your layout.</p>
      </div>

      <div className="grid w-full gap-md lg:grid-cols-[320px_minmax(0,1fr)]">
        <div className="space-y-sm rounded-lg border border-divider/70 bg-background/80 p-md">
          <div>
            <h3 className="text-base font-semibold text-text">Layout</h3>
            <p className="text-xs text-neutral-text">Control orientation, placement, and sizing.</p>
          </div>
          <div className="grid gap-sm">
            <ControlGroup label="Orientation">
              <select className={controlInputClass} value={orientation} onChange={(event) => setOrientation(event.target.value as "horizontal" | "vertical")}>
                {ORIENTATION_OPTIONS.map((option) => (
                  <option key={option} value={option}>
                    {humanize(option)}
                  </option>
                ))}
              </select>
            </ControlGroup>
            <ControlGroup label="Tab placement">
              <select className={controlInputClass} value={justify} onChange={(event) => setJustify(event.target.value as "start" | "end")}>
                {JUSTIFY_OPTIONS.map((option) => (
                  <option key={option} value={option}>
                    {option === "start" ? "Start (top/left)" : "End (bottom/right)"}
                  </option>
                ))}
              </select>
            </ControlGroup>
            <ControlGroup label="List width">
              <select className={controlInputClass} value={listWidth} onChange={(event) => setListWidth(event.target.value as BaseWidthMode)}>
                {WIDTH_OPTIONS.map((option) => (
                  <option key={option} value={option}>
                    {humanize(option)}
                  </option>
                ))}
              </select>
            </ControlGroup>
          </div>
        </div>

        <div className="space-y-sm rounded-lg border border-divider/70 bg-background/80 p-md">
          <div>
            <h3 className="text-base font-semibold text-text">Styling</h3>
            <p className="text-xs text-neutral-text">Mix variants, tones, spacing, and typography.</p>
          </div>
          <div className="grid gap-sm sm:grid-cols-2">
            <ControlGroup label="Variant">
              <select className={controlInputClass} value={variant} onChange={(event) => setVariant(event.target.value as TabsVariant)}>
                {VARIANT_OPTIONS.map((option) => (
                  <option key={option} value={option}>
                    {humanize(option)}
                  </option>
                ))}
              </select>
            </ControlGroup>
            <ControlGroup label="Tone">
              <select className={controlInputClass} value={tone} onChange={(event) => setTone(event.target.value as TabsTone)}>
                {TONE_OPTIONS.map((option) => (
                  <option key={option} value={option}>
                    {humanize(option)}
                  </option>
                ))}
              </select>
            </ControlGroup>
            <ControlGroup label="List gap">
              <select className={controlInputClass} value={listGap} onChange={(event) => setListGap(event.target.value as Spacing)}>
                {SPACING_OPTIONS.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </ControlGroup>
            <ControlGroup label="Text size">
              <select className={controlInputClass} value={textSize} onChange={(event) => setTextSize(event.target.value as FontSize)}>
                {FONT_SIZE_OPTIONS.map((option) => (
                  <option key={option} value={option}>
                    {option.toUpperCase()}
                  </option>
                ))}
              </select>
            </ControlGroup>
            <ControlGroup label="Tab radius">
              <select
                className={controlInputClass}
                value={Array.isArray(tabRadius) ? tabRadius.join(",") : (tabRadius as Radius)}
                onChange={(event) => setTabRadius(event.target.value as RadiusFormat)}
              >
                {RADIUS_OPTIONS.map((option) => (
                  <option key={option} value={option}>
                    {humanize(option)}
                  </option>
                ))}
              </select>
            </ControlGroup>
            <ControlGroup label="List padding X / Y">
              <div className="grid grid-cols-2 gap-2">
                <select className={controlInputClass} value={listPaddingX} onChange={(event) => setListPaddingX(event.target.value as Spacing)}>
                  {OPTIONAL_SPACING_OPTIONS.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </select>
                <select className={controlInputClass} value={listPaddingY} onChange={(event) => setListPaddingY(event.target.value as Spacing)}>
                  {OPTIONAL_SPACING_OPTIONS.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </select>
              </div>
            </ControlGroup>
            <ControlGroup label="Tab padding X / Y">
              <div className="grid grid-cols-2 gap-2">
                <select className={controlInputClass} value={tabPaddingX} onChange={(event) => setTabPaddingX(event.target.value as Spacing)}>
                  {OPTIONAL_SPACING_OPTIONS.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </select>
                <select className={controlInputClass} value={tabPaddingY} onChange={(event) => setTabPaddingY(event.target.value as Spacing)}>
                  {OPTIONAL_SPACING_OPTIONS.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </select>
              </div>
            </ControlGroup>
          </div>
        </div>

        <div className="space-y-sm rounded-lg border border-divider/70 bg-background/80 p-md">
          <div>
            <h3 className="text-base font-semibold text-text">Behavior</h3>
            <p className="text-xs text-neutral-text">Toggle borders, animation, and persistence.</p>
          </div>
          <div className="grid gap-2xs">
            <CheckboxControl label="Hide tab list border" checked={disableBorder} onChange={setDisableBorder} />
            <CheckboxControl label="Animate selection indicator" checked={animated} onChange={setAnimated} />
            <CheckboxControl label="Persist selection in history state" checked={persistSelection} onChange={setPersistSelection} />
          </div>
          <ControlGroup label="DOM id prefix">
            <input className={controlInputClass} value={domIdPrefix} onChange={(event) => setDomIdPrefix(event.target.value)} placeholder="Optional prefix applied to ids" />
          </ControlGroup>
          <p className="text-xs text-neutral-text">
            Previewed ids: <span className="font-mono text-text">{domPreviewIds}</span>
          </p>
        </div>
      </div>

      <div className="space-y-sm rounded-lg border border-divider/70 bg-background/80 p-lg">
        <Tabs
          selectedKey={selectedKey}
          onSelectionChange={(key) => setSelectedKey(String(key))}
          orientation={orientation}
          justify={justify}
          animated={animated}
          domIdPrefix={domIdPrefix.trim() ? domIdPrefix.trim() : undefined}
          persistKey={persistSelection ? "tabs-showcase" : undefined}
          className={clsx("gap-md", tabsLayoutClass)}
        >
          <TabList variant={variant} tone={tone} gap={listGap} padding={listPadding} textSize={textSize} width={listWidth} disableBorder={disableBorder}>
            {TAB_ITEMS.map((tab) => (
              <Tab key={tab.id} id={tab.id} radius={tabRadius} padding={tabPadding} textSize={textSize}>
                {tab.label}
              </Tab>
            ))}
          </TabList>
          {TAB_ITEMS.map((tab) => (
            <TabPanel
              key={tab.id}
              className={clsx("w-full rounded-lg border border-divider bg-foreground/15 p-md text-sm text-neutral-text", orientation === "vertical" && "md:min-h-[160px]")}
            >
              <div className="space-y-2">
                <div className="text-xs font-semibold tracking-wide text-neutral uppercase">Tab content</div>
                <p className="text-text">{tab.description}</p>
                <p className="text-xs text-neutral-text">DOM id: {domIdPrefix.trim() ? `${domIdPrefix.trim()}-${tab.id}` : tab.id}</p>
              </div>
            </TabPanel>
          ))}
        </Tabs>

        <dl className="grid gap-sm rounded-lg border border-divider/70 bg-alt-background p-sm text-sm text-neutral-text sm:grid-cols-3">
          <div className="space-y-1">
            <dt className="text-2xs font-semibold tracking-wide text-neutral uppercase">Selected key</dt>
            <dd className="font-mono text-text">{selectedKey}</dd>
          </div>
          <div className="space-y-1">
            <dt className="text-2xs font-semibold tracking-wide text-neutral uppercase">Layout</dt>
            <dd className="text-text">
              {orientation} · {justify === "start" ? "leading" : "trailing"}
            </dd>
          </div>
          <div className="space-y-1">
            <dt className="text-2xs font-semibold tracking-wide text-neutral uppercase">Variant & tone</dt>
            <dd className="text-text">
              {variant} · {tone}
            </dd>
          </div>
          <div className="space-y-1">
            <dt className="text-2xs font-semibold tracking-wide text-neutral uppercase">Spacing</dt>
            <dd className="text-text">
              gap {listGap} · px {tabPaddingX} · py {tabPaddingY}
            </dd>
          </div>
          <div className="space-y-1">
            <dt className="text-2xs font-semibold tracking-wide text-neutral uppercase">Borders</dt>
            <dd className="text-text">{disableBorder ? "Hidden" : "Visible"}</dd>
          </div>
          <div className="space-y-1">
            <dt className="text-2xs font-semibold tracking-wide text-neutral uppercase">Animation</dt>
            <dd className="text-text">{animated ? "Enabled" : "Off"}</dd>
          </div>
        </dl>
      </div>
    </section>
  );
}

function ControlGroup({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="space-y-1 text-sm text-text">
      <span className="text-2xs font-semibold tracking-wide text-neutral uppercase">{label}</span>
      {children}
    </label>
  );
}

function CheckboxControl({ label, checked, onChange }: { label: string; checked: boolean; onChange: (checked: boolean) => void }) {
  return (
    <Checkbox width="full" isSelected={checked} onChange={onChange}>
      {label}
    </Checkbox>
  );
}

function humanize(value: string) {
  return value
    .replace(/_/g, " ")
    .replace(/-/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}
