"use client";

import { sx } from "@/lib/sx";

export type ButtonVariant = "primary" | "outline" | "danger";

const VARIANT: Record<ButtonVariant, string> = {
  primary: "border:none;background:var(--blue);color:#fff",
  outline: "border:1px solid var(--line2);background:transparent;color:var(--ink2)",
  danger: "border:1.5px solid var(--orange);background:transparent;color:var(--orange-tx)",
};

export function Button({
  children,
  variant = "primary",
  size = "md",
  onClick,
  title,
  style = "",
}: {
  children: React.ReactNode;
  variant?: ButtonVariant;
  size?: "sm" | "md" | "lg";
  onClick?: () => void;
  title?: string;
  /** 여백·너비 같은 배치 전용 오버라이드 */
  style?: string;
}) {
  const pad =
    size === "lg" ? "padding:11px 22px;font-size:13px" : size === "sm" ? "padding:7px 12px;font-size:11.5px" : "padding:9px 16px;font-size:12px";

  return (
    <button
      onClick={onClick}
      title={title}
      style={sx(
        `border-radius:6px;font-family:'Pretendard';font-weight:600;cursor:pointer;white-space:nowrap;` +
          `${pad};${VARIANT[variant]};${style}`
      )}
    >
      {children}
    </button>
  );
}

/** 아이콘 전용 정사각 버튼 (마이크·카메라). */
export function IconButton({
  children,
  onClick,
  title,
  active = false,
  style = "",
}: {
  children: React.ReactNode;
  onClick?: () => void;
  title?: string;
  active?: boolean;
  style?: string;
}) {
  const skin = active
    ? "border:none;background:var(--orange);color:#fff"
    : "border:1px solid var(--line2);background:var(--raise);color:var(--dim)";
  return (
    <button
      onClick={onClick}
      title={title}
      style={sx(
        `width:40px;height:40px;flex-shrink:0;border-radius:9px;cursor:pointer;font-size:16px;` +
          `display:flex;align-items:center;justify-content:center;${skin};${style}`
      )}
    >
      {children}
    </button>
  );
}
