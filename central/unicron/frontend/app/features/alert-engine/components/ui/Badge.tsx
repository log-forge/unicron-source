import React from "react";
import { getToneBadgeClasses, type ThemeTone } from "~/utils/theme";

interface BadgeProps {
  children: React.ReactNode;
  variant?: 'default' | 'success' | 'warning' | 'danger' | 'info';
  size?: 'sm' | 'md';
  title?: string;
}

const Badge: React.FC<BadgeProps> = ({ children, variant = 'default', size = 'md', title }) => {
  const variantTone: Record<NonNullable<BadgeProps["variant"]>, ThemeTone> = {
    default: "neutral",
    success: "success",
    warning: "warning",
    danger: "error",
    info: "info",
  };

  const sizes = {
    sm: 'px-2 py-0.5 text-xs',
    md: 'px-2.5 py-0.5 text-xs'
  };

  return (
    <span
      className={`inline-flex items-center rounded-full border font-medium ${getToneBadgeClasses(variantTone[variant])} ${sizes[size]}`}
      title={title}
    >
      {children}
    </span>
  );
};

export default Badge;
