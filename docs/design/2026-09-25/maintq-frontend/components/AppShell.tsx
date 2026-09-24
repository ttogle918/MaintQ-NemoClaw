"use client";

import { useEffect, useState } from "react";
import { sx } from "@/lib/sx";
import { PAGE_BG, THEME_LABELS, type Theme, type Role } from "@/lib/theme";
import ScreenA from "./ScreenA";
import ScreenB from "./ScreenB";

const PENDING_COUNT = 3;

export default function AppShell() {
  const [theme, setTheme] = useState<Theme>("dark");
  const [role, setRole] = useState<Role>("tech");
  const [toast, setToast] = useState(false);

  // keep <body> background in sync with the active theme
  useEffect(() => {
    document.body.style.background = PAGE_BG[theme];
  }, [theme]);

  function requestApproval() {
    setRole("lead");
    setToast(true);
    window.setTimeout(() => setToast(false), 2600);
  }

  const tab = (active: boolean) =>
    "display:inline-flex;align-items:center;gap:7px;border:none;border-radius:7px;padding:8px 14px;font:600 12.5px 'Pretendard';cursor:pointer;transition:all .15s;white-space:nowrap;" +
    (active ? "background:var(--blue);color:#fff;" : "background:transparent;color:var(--dim);");

  const sw = (active: boolean) =>
    "border:none;border-radius:6px;padding:6px 12px;font:600 12px 'Pretendard';cursor:pointer;transition:all .15s;white-space:nowrap;" +
    (active ? "background:var(--blue);color:#fff;" : "background:transparent;color:var(--dim);");

  return (
    <div
      className="app-root"
      data-theme={theme}
      style={sx("min-height:100vh;background:var(--page);transition:background .2s")}
    >
      {/* 상단 앱바 */}
      <div style={sx("position:sticky;top:0;z-index:20;display:flex;align-items:center;gap:12px;padding:11px 20px;background:var(--head);border-bottom:1px solid var(--line);backdrop-filter:blur(6px)")}>
        <div style={sx("width:26px;height:26px;border-radius:6px;background:var(--blue);display:flex;align-items:center;justify-content:center;font:700 13px 'JetBrains Mono',monospace;color:#fff")}>M</div>
        <span style={sx("font:700 15px 'Pretendard';color:var(--ink)")}>MaintQ</span>
        <span style={sx("font:11px 'Pretendard';color:var(--dim2)")}>설비보전 AI 콘솔</span>
        <span style={sx("width:1px;height:18px;background:var(--line);margin:0 6px")} />

        {/* 역할 전환 */}
        <div style={sx("display:flex;gap:5px;background:var(--sw);border:1px solid var(--sw-line);border-radius:10px;padding:4px")}>
          <button onClick={() => setRole("tech")} style={sx(tab(role === "tech"))}>
            <span style={sx("font-size:14px")}>🔧</span> 정비사 · 진단 콘솔
          </button>
          <button onClick={() => setRole("lead")} style={sx(tab(role === "lead"))}>
            <span style={sx("font-size:14px")}>🗂</span> 보전팀장 · 승인 큐
            <span style={sx("display:inline-flex;align-items:center;justify-content:center;min-width:17px;height:17px;padding:0 4px;border-radius:9px;background:var(--orange);color:#fff;font:700 10px 'JetBrains Mono',monospace")}>{PENDING_COUNT}</span>
          </button>
        </div>

        <div style={sx("flex:1")} />
        <span style={sx("font:11px 'Pretendard';color:var(--dim2)")}>테마</span>
        <div style={sx("display:flex;gap:4px;background:var(--sw);border:1px solid var(--sw-line);border-radius:9px;padding:4px")}>
          {THEME_LABELS.map((t) => (
            <button key={t.value} onClick={() => setTheme(t.value)} style={sx(sw(theme === t.value))}>
              {t.label}
            </button>
          ))}
        </div>
      </div>

      {/* 화면 */}
      <div style={sx("padding:26px 24px 60px")}>
        {role === "tech" ? (
          <ScreenA theme={theme} onRequestApproval={requestApproval} />
        ) : (
          <ScreenB theme={theme} />
        )}
      </div>

      {/* 토스트 */}
      {toast && (
        <div style={sx("position:fixed;left:50%;bottom:34px;z-index:40;display:flex;align-items:center;gap:9px;padding:12px 18px;border-radius:10px;background:var(--surface);border:1px solid var(--line2);box-shadow:0 10px 30px rgba(0,0,0,.35);animation:mq-toast 2.6s ease forwards")}>
          <span style={sx("width:20px;height:20px;border-radius:50%;background:var(--cite-bg);border:1px solid var(--cite-bd);display:flex;align-items:center;justify-content:center;font-size:11px;color:var(--blue-tx)")}>→</span>
          <span style={sx("font:600 13px 'Pretendard';color:var(--ink)")}><span style={sx("font-family:'JetBrains Mono',monospace;font-size:12px")}>#PO-0117</span> 발주 요청이 팀장 승인 큐로 전달되었습니다</span>
        </div>
      )}
    </div>
  );
}
