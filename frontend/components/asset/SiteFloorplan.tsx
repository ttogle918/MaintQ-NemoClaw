"use client";

import { type ApiFloorplan, type ApiFloorplanEquipment } from "@/lib/api";
import {
  type EquipmentStatusKey,
  isHotspotColorKey,
  type OnboardingRing,
  plainStatusView,
} from "@/lib/floorplan";
import { hotspotColorView } from "@/lib/mappers";

/**
 * 사업장 평면도 SVG (D158, MQ-1914). **자체 생성 SVG** — 외부 이미지·지도 타일·CDN 없음
 * (D158 ⓑⓒ: egress 정책 무변경 · 저작권 도면 재배포 없음). 좌표는 API 가 준 SVG 사용자 단위 그대로.
 *
 * 이 컴포넌트는 **그리기만** 한다 — 점의 채움(설비 상태)·테두리(기종 온보딩)는 호출자가
 * `lib/floorplan` 으로 정한 값을 넘긴다. 상태 문자열을 여기서 비교하지 않는다 (D87).
 * 색은 CSS 변수라 라이트·다크 테마를 그대로 따른다.
 */

export interface DotStyle {
  key: EquipmentStatusKey;
  ring: OnboardingRing | null;
  /** 마우스 오버 설명 (상태·온보딩 라벨) */
  title: string;
}

export function dotFill(key: EquipmentStatusKey): { fill: string; hollow: boolean; label: string } {
  if (isHotspotColorKey(key)) {
    const v = hotspotColorView(key);
    return { fill: v.dotColor ?? "var(--error-tx)", hollow: false, label: v.text };
  }
  const p = plainStatusView(key);
  return { fill: p.fill, hollow: p.hollow, label: p.label };
}

/** 범례·목록에서 쓰는 작은 점 — 평면도 점과 같은 그리기 규칙 */
export function MiniDot({ style, size = 16 }: { style: DotStyle; size?: number }) {
  const f = dotFill(style.key);
  return (
    <svg width={size} height={size} viewBox="-8 -8 16 16" aria-hidden style={{ flex: "none" }}>
      {style.ring && (
        <circle r={7} fill="none" stroke={style.ring.stroke} strokeWidth={1.6} strokeDasharray={style.ring.dash || undefined} />
      )}
      <circle
        r={4.2}
        fill={f.hollow ? "var(--panel)" : f.fill}
        stroke={f.fill}
        strokeWidth={f.hollow ? 1.6 : 0}
      />
    </svg>
  );
}

export function SiteFloorplan({
  plan,
  dotStyle,
  hoverId,
  onHover,
  onSelect,
}: {
  plan: ApiFloorplan;
  dotStyle: (eq: ApiFloorplanEquipment) => DotStyle;
  hoverId: string | null;
  onHover: (id: string | null) => void;
  onSelect: (eq: ApiFloorplanEquipment) => void;
}) {
  const { site, zones, equipment } = plan;
  return (
    <svg
      viewBox={`0 0 ${site.width} ${site.height}`}
      role="img"
      aria-label={`${site.name} 평면도 — 구역 ${zones.length}개 · 설비 ${equipment.length}대`}
      style={{ width: "100%", height: "auto", display: "block", background: "var(--sw)", borderRadius: 6 }}
    >
      {/* 사업장 외곽 */}
      <rect
        x={8}
        y={8}
        width={site.width - 16}
        height={site.height - 16}
        rx={6}
        fill="none"
        stroke="var(--line2)"
        strokeWidth={1.5}
        strokeDasharray="6 4"
      />
      {zones.map((z) => (
        <g key={z.zone_id}>
          <rect x={z.x} y={z.y} width={z.w} height={z.h} rx={6} fill="var(--panel)" stroke="var(--line2)" strokeWidth={1.2} />
          <text x={z.x + 12} y={z.y + 22} fill="var(--ink2)" style={{ font: "700 14px 'Pretendard'" }}>
            {z.name}
          </text>
          <text
            x={z.x + z.w - 12}
            y={z.y + 22}
            textAnchor="end"
            fill="var(--dim2)"
            style={{ font: "11px 'JetBrains Mono', monospace" }}
          >
            {z.zone_id}
          </text>
        </g>
      ))}
      {equipment.map((eq) => {
        const s = dotStyle(eq);
        const f = dotFill(s.key);
        const hot = hoverId === eq.equipment_id;
        return (
          <g
            key={eq.equipment_id}
            transform={`translate(${eq.x} ${eq.y})`}
            role="link"
            tabIndex={0}
            aria-label={`${eq.equipment_id} ${eq.model} — 진단 콘솔에서 열기`}
            onClick={() => onSelect(eq)}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onSelect(eq);
              }
            }}
            onMouseEnter={() => onHover(eq.equipment_id)}
            onMouseLeave={() => onHover(null)}
            onFocus={() => onHover(eq.equipment_id)}
            onBlur={() => onHover(null)}
            style={{ cursor: "pointer", outline: "none" }}
          >
            <title>{s.title}</title>
            {/* 클릭 영역 — 점보다 넉넉하게 */}
            <rect x={-46} y={-22} width={92} height={62} fill="transparent" />
            {hot && <circle r={24} fill="var(--sel)" stroke="var(--blue-br)" strokeWidth={1} />}
            {s.ring && (
              <circle r={16} fill="none" stroke={s.ring.stroke} strokeWidth={3} strokeDasharray={s.ring.dash || undefined} />
            )}
            <circle r={10} fill={f.hollow ? "var(--panel)" : f.fill} stroke={f.fill} strokeWidth={f.hollow ? 2.5 : 0} />
            <text
              y={32}
              textAnchor="middle"
              fill="var(--ink)"
              style={{ font: "600 11px 'JetBrains Mono', monospace" }}
            >
              {eq.equipment_id}
            </text>
            <text y={46} textAnchor="middle" fill="var(--dim)" style={{ font: "10.5px 'JetBrains Mono', monospace" }}>
              {eq.model}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
