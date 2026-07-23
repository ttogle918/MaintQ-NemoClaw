"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { sx } from "@/lib/sx";
import { ROLE_HOME, ROLE_ICON, ROLE_LABEL, roleFromPath, type Role } from "@/lib/role";

const ROLES: Role[] = ["technician", "manager"];

/**
 * 역할 전환 — 상태 토글이 아니라 **라우트 이동**이다.
 * 라우트가 역할을 결정해야 X-Role 이 고정되고 "정비사 approve → 403" 을 시연할 수 있다.
 */
export function RoleTabs({ pendingCount }: { pendingCount: number }) {
  const active = roleFromPath(usePathname());

  return (
    <div
      style={sx(
        "display:flex;gap:5px;background:var(--sw);border:1px solid var(--sw-line);border-radius:10px;padding:4px"
      )}
    >
      {ROLES.map((role) => {
        const on = role === active;
        return (
          <Link
            key={role}
            href={ROLE_HOME[role]}
            style={sx(
              "display:inline-flex;align-items:center;gap:7px;border-radius:7px;padding:8px 14px;" +
                "font:600 12.5px 'Pretendard';text-decoration:none;transition:all .15s;white-space:nowrap;" +
                (on ? "background:var(--blue);color:#fff;" : "background:transparent;color:var(--dim);")
            )}
          >
            <span style={sx("font-size:14px")}>{ROLE_ICON[role]}</span> {ROLE_LABEL[role]}
            {role === "manager" && pendingCount > 0 && (
              <span
                style={sx(
                  "display:inline-flex;align-items:center;justify-content:center;min-width:17px;height:17px;" +
                    "padding:0 4px;border-radius:9px;background:var(--orange);color:#fff;" +
                    "font:700 10px 'JetBrains Mono',monospace"
                )}
              >
                {pendingCount}
              </span>
            )}
          </Link>
        );
      })}
    </div>
  );
}
