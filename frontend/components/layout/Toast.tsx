"use client";

import { sx } from "@/lib/sx";

export function Toast({ children }: { children: React.ReactNode }) {
  return (
    <div
      style={sx(
        "position:fixed;left:50%;bottom:34px;z-index:40;display:flex;align-items:center;gap:9px;" +
          "padding:12px 18px;border-radius:10px;background:var(--surface);border:1px solid var(--line2);" +
          "box-shadow:0 10px 30px rgba(0,0,0,.35);animation:mq-toast 2.6s ease forwards"
      )}
    >
      <span
        style={sx(
          "width:20px;height:20px;border-radius:50%;background:var(--cite-bg);border:1px solid var(--cite-bd);" +
            "display:flex;align-items:center;justify-content:center;font-size:11px;color:var(--blue-tx)"
        )}
      >
        →
      </span>
      <span style={sx("font:600 13px 'Pretendard';color:var(--ink)")}>{children}</span>
    </div>
  );
}
