"use client";

import { sx } from "@/lib/sx";
import { useTheme } from "@/lib/theme-context";
import { THEME_LABELS } from "@/lib/theme";

export function ThemeSwitch() {
  const { theme, setTheme } = useTheme();

  return (
    <>
      <span style={sx("font:11px 'Pretendard';color:var(--dim2)")}>테마</span>
      <div
        style={sx(
          "display:flex;gap:4px;background:var(--sw);border:1px solid var(--sw-line);border-radius:9px;padding:4px"
        )}
      >
        {THEME_LABELS.map((t) => (
          <button
            key={t.value}
            onClick={() => setTheme(t.value)}
            style={sx(
              "border:none;border-radius:6px;padding:6px 12px;font:600 12px 'Pretendard';cursor:pointer;" +
                "transition:all .15s;white-space:nowrap;" +
                (theme === t.value
                  ? "background:var(--blue);color:#fff;"
                  : "background:transparent;color:var(--dim);")
            )}
          >
            {t.label}
          </button>
        ))}
      </div>
    </>
  );
}
