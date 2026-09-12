import type { ButtonHTMLAttributes, ReactNode } from "react";
import "./Button.css";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md";

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  icon?: ReactNode;
  iconOnly?: boolean;
}

export function Button({
  variant = "secondary",
  size = "md",
  icon,
  iconOnly = false,
  className,
  children,
  ...rest
}: Props) {
  const classes = ["ds-button", `ds-button--${variant}`, `ds-button--${size}`, className]
    .filter(Boolean)
    .join(" ");
  return (
    <button className={classes} {...rest}>
      {icon}
      {!iconOnly && children}
    </button>
  );
}
