import * as React from "react";
import { useLocation, useNavigate } from "react-router";
import clsx from "clsx";
import { Tabs as RaTabs, TabList as RaTabList, Tab as RaTab, TabPanel as RaTabPanel, SelectionIndicator, composeRenderProps, type Key } from "react-aria-components";
import { indicatorVariantClasses, tabVariantClasses, type TabsTone, type TabsVariant } from "./tabs.styles";
import { paddingToClass, radiusToClass, widthToClass, type BaseWidthMode, type PaddingFormat, type RadiusFormat } from "../components.styles";

type TabsContextValue = {
  orientation: "horizontal" | "vertical";
  justify: "start" | "end";
  domIdPrefix: string | null;
  animated: boolean;
};

type TabsStyleContextValue = {
  variant: TabsVariant;
  tone: TabsTone;
};

const TabsContext = React.createContext<TabsContextValue | null>(null);
const TabsStyleContext = React.createContext<TabsStyleContextValue | null>(null);

function useTabsContext(): TabsContextValue {
  const context = React.useContext(TabsContext);
  if (!context) throw new Error("Tabs components must be used within a <Tabs> provider.");
  return context;
}

function useTabsStyleContext(): TabsStyleContextValue {
  return React.useContext(TabsStyleContext) ?? { variant: "underline", tone: "default" };
}

type TabsProps = React.ComponentProps<typeof RaTabs> & {
  domIdPrefix?: string;
  persistKey?: string;
  justify?: "start" | "end";
  animated?: boolean;
};

export default function Tabs({
  children,
  className,
  orientation = "horizontal",
  domIdPrefix,
  persistKey,
  justify = "start",
  animated = true,
  onSelectionChange,
  ...rest
}: TabsProps) {
  const navigate = useNavigate();
  const location = useLocation();
  const locationState = (location.state as Record<string, unknown> | null) ?? null;
  const rawPersisted = persistKey && locationState ? locationState[persistKey] : undefined;
  const persistedSelected: Key | undefined = typeof rawPersisted === "string" || typeof rawPersisted === "number" ? (rawPersisted as Key) : undefined;

  const handleSelectionChange = (key: Key) => {
    onSelectionChange?.(key);

    if (persistKey) {
      const nextState = { ...(locationState ?? {}), [persistKey]: String(key) };
      navigate(".", { replace: true, state: nextState });
    }
  };

  const selectedKey: Key | null | undefined = persistedSelected ?? rest.selectedKey;
  const controlledProps = selectedKey !== undefined ? { selectedKey } : {};

  return (
    <TabsContext.Provider value={{ orientation, justify, domIdPrefix: domIdPrefix ?? null, animated }}>
      <RaTabs {...rest} {...controlledProps} onSelectionChange={handleSelectionChange} orientation={orientation} className={clsx("group/tabs flex max-w-full min-w-0 items-start", className)}>
        {children}
      </RaTabs>
    </TabsContext.Provider>
  );
}

type TabListProps = React.ComponentProps<typeof RaTabList> & {
  disableBorder?: boolean;
  scrollable?: boolean;
  width?: BaseWidthMode;
  gap?: Spacing;
  padding?: PaddingFormat;
  variant?: TabsVariant;
  tone?: TabsTone;
  textSize?: FontSize;
};

export function TabList({
  children,
  className,
  disableBorder = false,
  scrollable = false,
  width = "full",
  gap = "sm",
  padding = 0,
  variant = "underline",
  tone = "default",
  textSize = "base",
  ...rest
}: TabListProps) {
  const { orientation, justify } = useTabsContext();

  const sizeClass = width === "full" ? (orientation === "vertical" ? "h-full w-fit" : "w-full") : "w-fit";
  const directionClass = orientation === "vertical" ? "flex-col" : "flex-row";
  const alignClass = orientation === "vertical" ? (justify === "end" ? "items-end" : "items-start") : "items-center";
  const borderClass = disableBorder
    ? ""
    : orientation === "vertical"
      ? `${justify === "end" ? "border-l" : "border-r"} border-divider`
      : `${justify === "end" ? "border-t" : "border-b"} border-divider`;
  const gapClass = gap ? `gap-${gap}` : "";
  const paddingClass = paddingToClass(padding, "0");
  const scrollClass =
    scrollable && orientation === "horizontal"
      ? "max-w-full overflow-x-auto overflow-y-hidden whitespace-nowrap [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
      : "";

  return (
    <TabsStyleContext.Provider value={{ variant, tone }}>
      <RaTabList
        {...rest}
        className={clsx("group/tab-list relative isolate flex", directionClass, alignClass, sizeClass, gapClass, `text-${textSize}`, paddingClass, borderClass, scrollClass, className)}
      >
        {children}
      </RaTabList>
    </TabsStyleContext.Provider>
  );
}

type TabProps = React.ComponentProps<typeof RaTab> & {
  selectionIndicatorClassName?: string;
  width?: BaseWidthMode;
  radius?: RadiusFormat;
  padding?: PaddingFormat;
  textSize?: FontSize;
};

export function Tab({ children, id, className, selectionIndicatorClassName, width = "content", radius = "md", padding = ["2xs", "4xs"], textSize, ...rest }: TabProps) {
  const { variant, tone } = useTabsStyleContext();
  const { domIdPrefix, animated, orientation, justify } = useTabsContext();

  const domId = React.useMemo(() => {
    if (!id) return undefined;
    return domIdPrefix ? `${domIdPrefix}-${id}` : id;
  }, [domIdPrefix, id]);

  const variantClasses = tabVariantClasses(tone, variant);
  const indicatorClasses = indicatorVariantClasses(tone, variant, animated);
  const widthClass = widthToClass(width);
  const radiusClass = radiusToClass(radius);
  const paddingClass = paddingToClass(padding, "xs");
  const textClass = textSize ? `text-${textSize}` : "";
  const indicatorPositionClass =
    variant === "underline"
      ? orientation === "vertical"
        ? justify === "end"
          ? "right-0 top-0 h-full w-[2px]"
          : "left-0 top-0 h-full w-[2px]"
        : "left-0 bottom-0 h-[2px] w-full"
      : "inset-0";

  return (
    <RaTab
      {...rest}
      id={domId}
      className={clsx(
        "relative z-10 inline-flex items-center justify-center outline-none select-none cursor-pointer",
        "shrink-0 whitespace-nowrap",
        "transition-[background,color,border,box-shadow,transform,opacity] duration-150 ease-out",
        "data-[disabled]:pointer-events-none data-[disabled]:opacity-50 data-[pressed]:scale-[0.98]",
        widthClass,
        radiusClass,
        paddingClass,
        textClass,
        variantClasses,
        className,
      )}
    >
      {composeRenderProps(children, (child) => (
        <>
          <span className="relative z-20 inline-flex items-center">{child}</span>
          <SelectionIndicator
            className={clsx(indicatorClasses, indicatorPositionClass, variant === "underline" ? "rounded-none" : "rounded-[inherit]", selectionIndicatorClassName)}
          />
        </>
      ))}
    </RaTab>
  );
}

export function TabPanel({ className, id, ...rest }: React.ComponentProps<typeof RaTabPanel>) {
  const { domIdPrefix } = useTabsContext();
  const domId = React.useMemo(() => {
    if (!id) return undefined;
    return domIdPrefix ? `${domIdPrefix}-${id}` : id;
  }, [domIdPrefix, id]);

  return <RaTabPanel {...rest} id={domId} className={clsx("outline-none focus-visible:outline-none", className)} />;
}
