"use client";

import { Logo } from "@/components/ui/Chip";
import { sx } from "@/lib/sx";
import { ManagerIdentitySwitch } from "./ManagerIdentitySwitch";
import { RoleTabs } from "./RoleTabs";
import { ThemeSwitch } from "./ThemeSwitch";

export function AppBar({ pendingCount }: { pendingCount: number }) {
  return (
    <div
      style={sx(
        "position:sticky;top:0;z-index:20;display:flex;align-items:center;gap:12px;padding:11px 20px;" +
          "background:var(--head);border-bottom:1px solid var(--line);backdrop-filter:blur(6px)"
      )}
    >
      <Logo size={26} />
      <span style={sx("font:700 15px 'Pretendard';color:var(--ink)")}>MaintQ</span>
      <span style={sx("font:11px 'Pretendard';color:var(--dim2)")}>설비보전 AI 콘솔</span>
      <span style={sx("width:1px;height:18px;background:var(--line);margin:0 6px")} />

      <RoleTabs pendingCount={pendingCount} />
      <span style={sx("width:1px;height:18px;background:var(--line);margin:0 6px")} />
      <ManagerIdentitySwitch />

      <div style={sx("flex:1")} />
      <ThemeSwitch />
    </div>
  );
}
