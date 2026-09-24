import Link from "next/link";
import { OnboardingBadge } from "@/components/onboarding/OnboardingBadge";
import { Mono } from "@/components/ui/Mono";
import { type ApiAsset, type ApiHotspotStatus } from "@/lib/api";
import { MODEL_BASE_IMAGE, MODEL_CITATION } from "@/lib/hotspots";
import { hotspotColorView } from "@/lib/mappers";
import { sx } from "@/lib/sx";

/**
 * `/technician/equipment-status`의 그리드 셀 1칸(세로 카드) — `page.tsx`에서 분리했다
 * (2026-08-24, 사용자 요청). 배치 순서(품번명·명칭 → 큰 이미지 → 위치·설명 → 이상탐지
 * 배지)는 사용자가 그려 준 와이어프레임 그대로다. `countHotspotColors`는 이 카드의
 * 배지뿐 아니라 `page.tsx`의 정렬 로직(`rankAsset`)도 같이 쓰므로 함께 export한다.
 */

export function countHotspotColors(
  status: ApiHotspotStatus | undefined
): { red: number; orange: number; blue: number } {
  const parts = status?.parts ?? [];
  const counts = { red: 0, orange: 0, blue: 0 };
  for (const p of parts) {
    if (p.color === "red") counts.red += 1;
    else if (p.color === "orange") counts.orange += 1;
    else if (p.color === "blue") counts.blue += 1;
  }
  return counts;
}

export function EquipmentCard({
  asset,
  status,
}: {
  asset: ApiAsset;
  status: ApiHotspotStatus | undefined;
}) {
  const counts = countHotspotColors(status);
  const model = status?.model;
  const baseImage = model ? MODEL_BASE_IMAGE[model] : undefined;
  const citation = model ? MODEL_CITATION[model] : undefined;

  return (
    <Link
      href={`/technician/equipment-status/${encodeURIComponent(asset.asset_id)}`}
      style={sx(
        "border:1px solid var(--line);border-radius:8px;background:var(--panel);padding:12px;" +
          "display:flex;flex-direction:column;gap:8px;text-decoration:none"
      )}
    >
      <div style={sx("display:flex;flex-direction:column;gap:2px;min-width:0")}>
        <Mono size={11}>{asset.asset_id}</Mono>
        <span
          style={sx(
            "font:700 13px 'Pretendard';color:var(--ink);white-space:nowrap;" +
              "overflow:hidden;text-overflow:ellipsis"
          )}
        >
          {asset.name}
        </span>
      </div>

      {model === undefined ? (
        // 로딩 중 또는 조회 실패 — 지어내지 않는다(D87), 빈 스켈레톤만 둔다.
        <div
          style={sx(
            "width:100%;aspect-ratio:4/3;background:var(--sw);border-radius:6px"
          )}
        />
      ) : baseImage ? (
        // eslint-disable-next-line @next/next/no-img-element -- 크롭된 정적 자산, 최적화 불필요
        <img
          src={baseImage}
          alt={`${model} 도면`}
          style={sx(
            "width:100%;aspect-ratio:4/3;object-fit:cover;border-radius:6px;" +
              "border:1px solid var(--line)"
          )}
        />
      ) : (
        // model 은 있지만 도면 좌표 미보유(IE5, D109) — 안전 문구·RAG 청킹과 같은 이유로 이
        // 하이라이트 좌표도 iG5A·S100만 커버한다. 현재 시드에 model='IE5' 인스턴스가 없어
        // (equipment.model CHECK 2종 유지) 실사용에서 도달하지 않는 방어적 분기.
        <div
          style={sx(
            "width:100%;aspect-ratio:4/3;background:var(--sw);border-radius:6px;" +
              "display:flex;align-items:center;justify-content:center;color:var(--dim2);" +
              "font-size:32px"
          )}
        >
          ⚙
        </div>
      )}

      <div style={sx("font:11px 'Pretendard';color:var(--dim);display:flex;align-items:center;gap:6px;flex-wrap:wrap")}>
        <span>
          라인 {asset.line_id ?? "미배정"}
          {status?.model && ` · ${status.model}`}
        </span>
        {/* 기종 온보딩 뱃지(MQ-1911) — iG5A·S100 은 `none` 이라 아무것도 그리지 않는다(기존 화면 무변화) */}
        {model && <OnboardingBadge model={model} />}
      </div>

      {citation && (
        <span style={sx("font:8.5px 'Pretendard';color:var(--dim2);line-height:1.3")}>
          {citation}
        </span>
      )}

      {status === undefined ? (
        <span style={sx("font:11px 'Pretendard';color:var(--dim2)")}>확인 중…</span>
      ) : status.status !== "ok" ? (
        <span style={sx("font:11px 'Pretendard';color:var(--dim2)")}>상태 미상</span>
      ) : (
        <div style={sx("display:flex;gap:8px;flex-wrap:wrap")}>
          {counts.red > 0 && (
            <Badge color={hotspotColorView("red").dotColor ?? "var(--ink)"}>🔴 {counts.red}</Badge>
          )}
          {counts.orange > 0 && (
            <Badge color={hotspotColorView("orange").dotColor ?? "var(--ink)"}>
              🟠 {counts.orange}
            </Badge>
          )}
          {counts.blue > 0 && (
            <Badge color={hotspotColorView("blue").dotColor ?? "var(--ink)"}>
              🔵 {counts.blue}
            </Badge>
          )}
          {counts.red + counts.orange + counts.blue === 0 && (
            <span style={sx("font:11px 'Pretendard';color:var(--dim2)")}>정상</span>
          )}
        </div>
      )}
    </Link>
  );
}

function Badge({ color, children }: { color: string; children: React.ReactNode }) {
  return (
    <span style={sx(`font:700 11.5px 'Pretendard';color:${color}`)}>{children}</span>
  );
}
