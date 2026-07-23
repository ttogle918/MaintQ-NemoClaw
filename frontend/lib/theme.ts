export type Theme = "dark" | "dgray" | "gray" | "light";
// Role 은 라우트가 결정하므로 lib/role.ts 가 소유한다.

/** Page background per theme — used to keep <body> in sync with .app-root. */
export const PAGE_BG: Record<Theme, string> = {
  dark: "#0a0c0f",
  dgray: "#191d23",
  gray: "#b9bec6",
  light: "#e7e9ec",
};

export const THEME_LABELS: { value: Theme; label: string }[] = [
  { value: "dark", label: "다크" },
  { value: "dgray", label: "다크 그레이" },
  { value: "gray", label: "그레이" },
  { value: "light", label: "라이트" },
];
