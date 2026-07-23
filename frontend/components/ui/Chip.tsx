import { sx } from "@/lib/sx";

/** 헤더의 라인/장비 선택 칩. 데이터는 GET /api/equipment 에서 온다. */
export function SelectChip({ children }: { children: React.ReactNode }) {
  return (
    <span
      style={sx(
        "border:1px solid var(--line2);border-radius:14px;padding:4px 11px;font:12px 'Pretendard';color:var(--ink2);background:var(--raise)"
      )}
    >
      {children} <span style={sx("color:var(--dim2)")}>▾</span>
    </span>
  );
}

export function Divider() {
  return <span style={sx("width:1px;height:16px;background:var(--line);margin:0 4px")} />;
}

export function Avatar() {
  return (
    <div
      style={sx(
        "width:26px;height:26px;border-radius:50%;background:var(--raise);border:1px solid var(--line)"
      )}
    />
  );
}

export function Logo({ size = 24 }: { size?: number }) {
  return (
    <div
      style={sx(
        `width:${size}px;height:${size}px;border-radius:5px;background:var(--blue);display:flex;` +
          `align-items:center;justify-content:center;font:700 ${size / 2}px 'JetBrains Mono',monospace;color:#fff`
      )}
    >
      M
    </div>
  );
}
