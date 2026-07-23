import type { CSSProperties } from "react";

/**
 * Parse an inline CSS declaration string into a React style object.
 * Lets JSX mirror the design prototype 1:1 (kebab-case, CSS custom
 * properties, and `var(--x)` all pass through untouched).
 *
 *   style={sx("padding:9px 13px;background:var(--blue);color:#fff")}
 */
export function sx(str: string): CSSProperties {
  const out: Record<string, string> = {};
  for (const decl of str.split(";")) {
    const i = decl.indexOf(":");
    if (i === -1) continue;
    const rawProp = decl.slice(0, i).trim();
    const val = decl.slice(i + 1).trim();
    if (!rawProp || !val) continue;
    // keep custom properties (--foo) verbatim; camelCase everything else
    const prop = rawProp.startsWith("--")
      ? rawProp
      : rawProp.replace(/-([a-z])/g, (_m, c: string) => c.toUpperCase());
    out[prop] = val;
  }
  return out as CSSProperties;
}
