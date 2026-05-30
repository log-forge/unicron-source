import React from "react";
import { PADDING, RADIUS } from "./Modal";
import clsx from "clsx";
import { paddingToClass, type PaddingFormat } from "../components.styles";

export type ModalHeaderProps = {
  title: string;
  // Optional styling overrides
  padding?: PaddingFormat;
  backgroundColor?: Colors;
  borderColor?: Colors;
  customClasses?: string;
};

const paddingToMargin: Record<string, string> = {
  "px-md": "-mx-md",
  "py-md": "-mt-md",
};
const radiusToClass: Record<string, string> = {
  "rounded-md": "rounded-t-md",
  "rounded-lg": "rounded-t-lg",
  "rounded-xl": "rounded-t-xl",
  "rounded-2xl": "rounded-t-2xl",
  "rounded-3xl": "rounded-t-3xl",
  "rounded-full": "rounded-t-full",
};

export default function ModalHeader({ title, padding = "sm", backgroundColor, borderColor, customClasses }: ModalHeaderProps) {
  return (
    <header
      className={clsx(
        `border-b`,
        `${paddingToMargin[PADDING.x]} ${paddingToMargin[PADDING.y]}`,
        `${radiusToClass[RADIUS]}`,
        `${paddingToClass(padding)}`,
        `border-${borderColor ?? "divider"} bg-${backgroundColor ?? "alt-foreground"}`,
        customClasses,
      )}
    >
      <h3 className="text-h3 font-bold">{title}</h3>
    </header>
  );
}
