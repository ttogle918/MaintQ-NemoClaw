"use client";

import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { PAGE_BG, type Theme } from "./theme";

interface ThemeCtx {
  theme: Theme;
  setTheme: (t: Theme) => void;
}

const Ctx = createContext<ThemeCtx | null>(null);

/**
 * 테마를 콘솔 레이아웃 한 곳에서 관리한다.
 * 라우트를 오가도 레이아웃은 리마운트되지 않으므로 선택한 테마가 유지된다.
 */
export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setTheme] = useState<Theme>("dark");

  useEffect(() => {
    document.body.style.background = PAGE_BG[theme];
  }, [theme]);

  const value = useMemo(() => ({ theme, setTheme }), [theme]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useTheme(): ThemeCtx {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useTheme 은 ThemeProvider 안에서만 쓸 수 있습니다");
  return ctx;
}
