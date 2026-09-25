"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { MiniDot, SiteFloorplan, dotFill, type DotStyle } from "@/components/asset/SiteFloorplan";
import { ConsoleFrame, ConsoleHeader, ScreenStack, Spacer } from "@/components/layout/ConsoleFrame";
import { StatusBanner } from "@/components/layout/StatusBanner";
import { OnboardingBadge } from "@/components/onboarding/OnboardingBadge";
import { Badge } from "@/components/ui/Badge";
import { Avatar, Divider, Logo } from "@/components/ui/Chip";
import { Mono } from "@/components/ui/Mono";
import {
  getFloorplan,
  getHotspotStatus,
  getOnboardingStatusCached,
  getSites,
  type ApiFloorplan,
  type ApiFloorplanEquipment,
  type ApiHotspotStatus,
} from "@/lib/api";
import { equipmentStatusKey, onboardingRing, type EquipmentStatusKey } from "@/lib/floorplan";
import { onboardingBadgeView, type OnboardingLabel } from "@/lib/onboarding";
import { ROLE_USER_NAME } from "@/lib/role";
import { sx } from "@/lib/sx";

/**
 * `/technician/site` — 사업장 평면도 (D158, Sprint 19 MQ-1914 · S1 설비 선택 → 진단 콘솔 진입).
 *
 * 원천 3개를 **조합만** 한다 — 판정을 새로 만들지 않는다:
 *   - 배치: `GET /api/sites` · `GET /api/sites/{id}/floorplan`
 *   - 설비 상태: `GET /api/assets/{asset_id}/hotspot-status` (설비 하이라이트 대시보드와 같은 원천)
 *   - 기종 온보딩: `GET /api/onboarding/status?model=` (`OnboardingBadge` 와 같은 캐시)
 * 점 클릭 → `/technician?equipment=…` (진단 콘솔이 그 설비를 선택한 상태로 연다, MQ-711 진입 파라미터).
 */
export default function SitePage() {
  const router = useRouter();
  const [plan, setPlan] = useState<ApiFloorplan | null>(null);
  const [error, setError] = useState<string | null>(null);
  // asset_id → 하이라이트 응답 · null = 조회 실패 (없으면 조회 중)
  const [hotspot, setHotspot] = useState<Map<string, ApiHotspotStatus | null>>(new Map());
  // model → 뱃지 뷰 · null = none(기존 기종, 테두리 없음) · "failed" = 조회 실패
  const [onboarding, setOnboarding] = useState<Map<string, OnboardingLabel | null | "failed">>(new Map());
  const [hoverId, setHoverId] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    getSites("technician")
      .then(async (sites) => {
        if (!alive) return;
        if (sites.length === 0) {
          setError("등록된 사업장이 없습니다.");
          return;
        }
        const fp = await getFloorplan("technician", sites[0].site_id);
        if (!alive) return;
        setPlan(fp);
        setError(null);

        const assetIds = Array.from(new Set(fp.equipment.map((e) => e.asset_id).filter((a): a is string => !!a)));
        void Promise.all(
          assetIds.map(async (a) => {
            try {
              return [a, await getHotspotStatus("technician", a)] as const;
            } catch {
              return [a, null] as const;
            }
          })
        ).then((entries) => {
          if (alive) setHotspot(new Map(entries));
        });

        const models = Array.from(new Set(fp.equipment.map((e) => e.model)));
        void Promise.all(
          models.map(async (m) => {
            try {
              const res = await getOnboardingStatusCached("technician", m);
              return [m, onboardingBadgeView(res.state)] as const;
            } catch {
              return [m, "failed" as const] as const;
            }
          })
        ).then((entries) => {
          if (alive) setOnboarding(new Map<string, OnboardingLabel | null | "failed">(entries));
        });
      })
      .catch(() => {
        if (alive) setError("백엔드에 연결하지 못했습니다 — 사업장 평면도를 가져오지 못했습니다.");
      });
    return () => {
      alive = false;
    };
  }, []);

  const statusKeyOf = useMemo(
    () =>
      (eq: ApiFloorplanEquipment): EquipmentStatusKey =>
        equipmentStatusKey(eq.asset_id, eq.asset_id && hotspot.has(eq.asset_id) ? hotspot.get(eq.asset_id) : undefined),
    [hotspot]
  );

  const dotStyle = useMemo(
    () =>
      (eq: ApiFloorplanEquipment): DotStyle => {
        const key = statusKeyOf(eq);
        const ob = onboarding.get(eq.model);
        // 온보딩 조회 실패는 unknown 테두리 — 「기존 기종(무표시)」으로 뭉개지 않는다
        const ring = ob === undefined ? null : onboardingRing(ob === "failed" ? "unknown" : ob?.tone);
        const obText = ob === undefined ? "확인 중" : ob === "failed" ? "조회 실패" : ob ? ob.label : "기존 기종";
        return {
          key,
          ring,
          title:
            `${eq.equipment_id} · ${eq.model} · ${eq.location ?? "위치 설명 없음"}\n` +
            `설비 상태: ${dotFill(key).label} · 기종 온보딩: ${obText}\n클릭 → 진단 콘솔`,
        };
      },
    [statusKeyOf, onboarding]
  );

  const openConsole = (eq: ApiFloorplanEquipment) =>
    router.push(`/technician?equipment=${encodeURIComponent(eq.equipment_id)}`);

  return (
    <ScreenStack>
      {error && <StatusBanner tone="error">⚠ {error}</StatusBanner>}
      <ConsoleFrame>
        <ConsoleHeader>
          <Logo />
          <span style={sx("font:600 13px 'Pretendard';color:var(--ink)")}>MaintQ</span>
          <Divider />
          <span style={sx("font:700 13px 'Pretendard';color:var(--ink)")}>사업장 평면도</span>
          {plan && (
            <>
              <span style={sx("font:600 12.5px 'Pretendard';color:var(--ink2)")}>{plan.site.name}</span>
              {plan.site.is_mock && (
                <Badge tone="neutral" size={10} title="실제 사업장이 아닌 목업 배치입니다 (D158)">
                  목업
                </Badge>
              )}
              <span style={sx("color:var(--dim)")}>
                <Mono size={11.5}>{`설비 ${plan.equipment.length}대 · 구역 ${plan.zones.length}`}</Mono>
              </span>
            </>
          )}
          <Spacer />
          <span style={sx("font:12px 'Pretendard';color:var(--dim)")}>정비사 {ROLE_USER_NAME.technician}</span>
          <Avatar />
        </ConsoleHeader>

        {plan === null ? (
          <div style={sx("font:12.5px 'Pretendard';color:var(--dim);padding:20px 16px")}>
            {error ? "평면도를 표시할 수 없습니다." : "불러오는 중…"}
          </div>
        ) : (
          <div style={sx("padding:14px 16px;display:grid;grid-template-columns:1fr 250px;gap:16px")}>
            <div style={sx("display:flex;flex-direction:column;gap:8px;min-width:0")}>
              <SiteFloorplan
                plan={plan}
                dotStyle={dotStyle}
                hoverId={hoverId}
                onHover={setHoverId}
                onSelect={openConsole}
              />
              <span style={sx("font:11px 'Pretendard';color:var(--dim2)")}>
                점을 누르면 진단 콘솔이 그 설비를 선택한 상태로 열립니다. 배치·좌표는 목업이며 실제 공장 도면이 아닙니다.
              </span>
            </div>
            <aside
              style={sx(
                "border-left:1px solid var(--line);padding-left:16px;display:flex;flex-direction:column;gap:12px;min-width:0"
              )}
            >
              <Legend />
              <EquipmentList plan={plan} dotStyle={dotStyle} hoverId={hoverId} onHover={setHoverId} />
            </aside>
          </div>
        )}
      </ConsoleFrame>
    </ScreenStack>
  );
}

/** 범례 — 두 축(채움 = 설비 상태 · 테두리 = 기종 온보딩)을 따로 보여 준다 */
function Legend() {
  const fills: EquipmentStatusKey[] = ["red", "orange", "blue", "normal", "no_host", "unknown"];
  const rings: { tone: string; label: string }[] = [
    { tone: "ok", label: "진단 가능 (승격·안전 문구 승인 완료)" },
    { tone: "info", label: "안전 문구 대기" },
    { tone: "neutral", label: "온보딩 중" },
  ];
  return (
    <div style={sx("display:flex;flex-direction:column;gap:6px")}>
      <span style={sx("font:700 11.5px 'Pretendard';color:var(--dim)")}>범례 · 채움 = 설비 상태</span>
      {fills.map((k) => (
        <LegendRow key={k} style={{ key: k, ring: null, title: "" }} label={dotFill(k).label} />
      ))}
      <span style={sx("font:700 11.5px 'Pretendard';color:var(--dim);margin-top:4px")}>테두리 = 기종 온보딩</span>
      {rings.map((r) => (
        <LegendRow key={r.tone} style={{ key: "normal", ring: onboardingRing(r.tone), title: "" }} label={r.label} />
      ))}
      <LegendRow style={{ key: "normal", ring: null, title: "" }} label="테두리 없음 = 기존 기종(iG5A·S100)" />
    </div>
  );
}

function LegendRow({ style, label }: { style: DotStyle; label: string }) {
  return (
    <div style={sx("display:flex;align-items:center;gap:7px;font:11px 'Pretendard';color:var(--ink2)")}>
      <MiniDot style={style} />
      <span>{label}</span>
    </div>
  );
}

/** 구역별 설비 목록 — 평면도와 같은 점 규칙 · 각 행이 진단 콘솔 링크(키보드 접근 경로이기도 하다) */
function EquipmentList({
  plan,
  dotStyle,
  hoverId,
  onHover,
}: {
  plan: ApiFloorplan;
  dotStyle: (eq: ApiFloorplanEquipment) => DotStyle;
  hoverId: string | null;
  onHover: (id: string | null) => void;
}) {
  return (
    <div style={sx("display:flex;flex-direction:column;gap:8px")}>
      <span style={sx("font:700 11.5px 'Pretendard';color:var(--dim)")}>설비 → 진단 콘솔</span>
      {plan.zones.map((z) => {
        const items = plan.equipment.filter((e) => e.zone_id === z.zone_id);
        if (items.length === 0) return null;
        return (
          <div key={z.zone_id} style={sx("display:flex;flex-direction:column;gap:3px")}>
            <span style={sx("font:600 11px 'Pretendard';color:var(--dim2)")}>{z.name}</span>
            {items.map((eq) => {
              const s = dotStyle(eq);
              return (
                <Link
                  key={eq.equipment_id}
                  href={`/technician?equipment=${encodeURIComponent(eq.equipment_id)}`}
                  title={s.title}
                  onMouseEnter={() => onHover(eq.equipment_id)}
                  onMouseLeave={() => onHover(null)}
                  style={sx(
                    "display:flex;align-items:center;gap:6px;padding:3px 6px;border-radius:5px;text-decoration:none;" +
                      "font:11px 'Pretendard';color:var(--ink);flex-wrap:wrap;" +
                      (hoverId === eq.equipment_id ? "background:var(--sel);" : "")
                  )}
                >
                  <MiniDot style={s} size={14} />
                  <Mono size={10.5}>{eq.equipment_id}</Mono>
                  <span style={sx("color:var(--dim)")}>{eq.model}</span>
                  <OnboardingBadge model={eq.model} size={8.5} />
                </Link>
              );
            })}
          </div>
        );
      })}
    </div>
  );
}
