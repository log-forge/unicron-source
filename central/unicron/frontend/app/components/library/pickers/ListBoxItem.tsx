import clsx from "clsx";
import { ListBoxItem as RaListBoxItem, type ListBoxItemProps } from "react-aria-components";
import { listBoxItemClassNames, type ListBoxItemTone, type ListBoxItemVariant } from "./list-box-item.styles";
import { statusToTone, type BaseStatus, type PaddingFormat, type RadiusFormat } from "../components.styles";

export type UiListBoxItemProps = ListBoxItemProps & {
  variant?: ListBoxItemVariant;
  tone?: ListBoxItemTone;
  status?: BaseStatus;
  textSize?: FontSize;
  padding?: PaddingFormat;
  radius?: RadiusFormat;
  doesStatusEffectItem?: boolean;
  className?: string;
};

export default function ListBoxItem({
  variant = "solid",
  tone = "default",
  status = "default",
  textSize = "sm",
  padding = ["xs", "4xs"],
  radius = "md",
  doesStatusEffectItem = false,
  className,
  ...rest
}: UiListBoxItemProps) {
  const resolvedTone = doesStatusEffectItem ? statusToTone(status, tone) : tone;

  return (
    <RaListBoxItem
      {...rest}
      className={clsx(
        "leading-body cursor-pointer transition-colors duration-150 select-none",
        `text-${textSize}`,
        listBoxItemClassNames({ variant, tone: resolvedTone, padding, radius }),
        className,
      )}
    />
  );
}

export { ListBoxLoadMoreItem } from "react-aria-components";
