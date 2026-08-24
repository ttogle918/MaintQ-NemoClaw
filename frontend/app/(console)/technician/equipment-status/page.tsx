"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { ConsoleFrame, ConsoleHeader, ScreenStack, Spacer } from "@/components/layout/ConsoleFrame";
import { StatusBanner } from "@/components/layout/StatusBanner";
import { Avatar, Divider, Logo } from "@/components/ui/Chip";
import { Mono } from "@/components/ui/Mono";
import { getAssets, getHotspotStatus, type ApiAsset, type ApiHotspotStatus } from "@/lib/api";
import { MODEL_BASE_IMAGE, MODEL_CITATION } from "@/lib/hotspots";
import { hotspotColorView } from "@/lib/mappers";
import { ROLE_USER_NAME } from "@/lib/role";
import { sx } from "@/lib/sx";

/** 한 페이지에 보여줄 카드 수 — 가로 4 × 세로 3 그리드 (Sprint 18 후속 요청). */
const PAGE_SIZE = 12;
const GRID_COLS = 4;

/**
 * `/technician/equipment-status` — 설비 하이라이트 대시보드 목록 (Sprint 10 브레인스토밍 C).
 *
 * 독립된 신규 화면이다(`asset` 목록과 별개, spec §4-1 "독립된 새 대시보드 화면"). 자산마다
 * `hotspot-status`를 조회해 배지(🔴N 🟠N 🔵N)를 붙인다 — 9개뿐이라 병렬 호출로 충분하다.
 * 카드는 4×3 그리드로 페이지네이션된다(한 페이지 12개) — 세로로 길게 늘어지지 않게.
 */
export default function EquipmentStatusListPage() {
  const [assets, setAssets] = useState<ApiAsset[] | null>(null);
  const [statusByAsset, setStatusByAsset] = useState<Map<string, ApiHotspotStatus>>(new Map());
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(0);

  useEffect(() => {
    let alive = true;
    getAssets("technician")
      .then(async (items) => {
        if (!alive) return;
        setAssets(items);
        setError(null);
        setPage(0);
        const entries = await Promise.all(
          items.map(async (a) => {
            try {
              return [a.asset_id, await getHotspotStatus("technician", a.asset_id)] as const;
            } catch {
              return [a.asset_id, { status: "error" } as ApiHotspotStatus] as const;
            }
          })
        );
        if (alive) setStatusByAsset(new Map(entries));
      })
      .catch(() => {
        if (alive) {
          setAssets([]);
          setError("백엔드에 연결하지 못했습니다 — 설비 목록을 가져오지 못했습니다.");
        }
      });
    return () => {
      alive = false;
    };
  }, []);

  const sortedAssets = useMemo(
    () => (assets ? [...assets].sort((a, b) => compareAssets(a, b, statusByAsset)) : []),
    [assets, statusByAsset]
  );

  const pageCount = Math.max(1, Math.ceil(sortedAssets.length / PAGE_SIZE));
  // 정렬 재계산(하이라이트 상태가 늦게 도착)으로 총 개수가 줄어 현재 페이지가 범위를
  // 벗어날 수 있다 — 지어낸 페이지를 보여주지 않고 마지막 유효 페이지로 자동 보정한다.
  const clampedPage = Math.min(page, pageCount - 1);
  const pagedAssets = useMemo(
    () => sortedAssets.slice(clampedPage * PAGE_SIZE, clampedPage * PAGE_SIZE + PAGE_SIZE),
    [sortedAssets, clampedPage]
  );

  return (
    <ScreenStack>
      {error && <StatusBanner tone="error">⚠ {error}</StatusBanner>}
      <ConsoleFrame>
        <ConsoleHeader>
          <Logo />
          <span style={sx("font:600 13px 'Pretendard';color:var(--ink)")}>MaintQ</span>
          <Divider />
          <span style={sx("font:700 13px 'Pretendard';color:var(--ink)")}>설비 하이라이트</span>
          <Mono size={11.5}>{assets === null ? "…" : `${assets.length}대`}</Mono>
          <Spacer />
          <span style={sx("font:12px 'Pretendard';color:var(--dim)")}>
            정비사 {ROLE_USER_NAME.technician}
          </span>
          <Avatar />
        </ConsoleHeader>

        <div style={sx("padding:14px 16px;display:flex;flex-direction:column;gap:14px")}>
          {assets === null ? (
            <div style={sx("font:12.5px 'Pretendard';color:var(--dim);padding:20px 0")}>
              불러오는 중…
            </div>
          ) : assets.length === 0 ? (
            <div style={sx("font:12.5px 'Pretendard';color:var(--dim);padding:20px 0")}>
              설비가 없습니다.
            </div>
          ) : (
            <>
              <div
                style={sx(
                  `display:grid;grid-template-columns:repeat(${GRID_COLS},1fr);gap:12px`
                )}
              >
                {pagedAssets.map((a) => (
                  <EquipmentCard key={a.asset_id} asset={a} status={statusByAsset.get(a.asset_id)} />
                ))}
              </div>
              {pageCount > 1 && (
                <Pagination page={clampedPage} pageCount={pageCount} onChange={setPage} />
              )}
            </>
          )}
        </div>
      </ConsoleFrame>
    </ScreenStack>
  );
}

function Pagination({
  page,
  pageCount,
  onChange,
}: {
  page: number;
  pageCount: number;
  onChange: (page: number) => void;
}) {
  return (
    <div style={sx("display:flex;align-items:center;justify-content:center;gap:6px;padding:4px 0")}>
      <button
        type="button"
        disabled={page === 0}
        onClick={() => onChange(page - 1)}
        style={sx(
          "border:1px solid var(--line);border-radius:6px;background:var(--panel);" +
            "padding:5px 10px;font:600 12px 'Pretendard';cursor:pointer;" +
            (page === 0 ? "color:var(--dim2);cursor:not-allowed;" : "color:var(--ink);")
        )}
      >
        이전
      </button>
      <span style={sx("font:12px 'Pretendard';color:var(--dim);padding:0 6px")}>
        {page + 1} / {pageCount}
      </span>
      <button
        type="button"
        disabled={page >= pageCount - 1}
        onClick={() => onChange(page + 1)}
        style={sx(
          "border:1px solid var(--line);border-radius:6px;background:var(--panel);" +
            "padding:5px 10px;font:600 12px 'Pretendard';cursor:pointer;" +
            (page >= pageCount - 1 ? "color:var(--dim2);cursor:not-allowed;" : "color:var(--ink);")
        )}
      >
        다음
      </button>
    </div>
  );
}

/** `EquipmentRow`의 배지 카운팅 루프 + `rankAsset`/`compareAssets`가 함께 쓰는 순수 함수. */
function countHotspotColors(
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

/**
 * 정렬 우선순위 등급. tier 0=🔴 있음 → 1=🟠만 → 2=🔵만 → 3=정상 → 4=상태 미상/로딩 중/조회 실패.
 * 등급 판단은 하이라이트 상태(`status.status`) 기준이지 모델 정보 유무 기준이 아니다.
 */
function rankAsset(
  asset: ApiAsset,
  status: ApiHotspotStatus | undefined
): { tier: number; tierCount: number; totalCount: number } {
  if (status?.status !== "ok") return { tier: 4, tierCount: 0, totalCount: 0 };
  const c = countHotspotColors(status);
  const total = c.red + c.orange + c.blue;
  if (c.red > 0) return { tier: 0, tierCount: c.red, totalCount: total };
  if (c.orange > 0) return { tier: 1, tierCount: c.orange, totalCount: total };
  if (c.blue > 0) return { tier: 2, tierCount: c.blue, totalCount: total };
  return { tier: 3, tierCount: 0, totalCount: 0 }; // 정상
}

/**
 * tier 오름차순 → (tier 0~2 한정) 해당 색 개수 내림차순 → 총 개수 내림차순 →
 * 최종 타이브레이크 `asset_id.localeCompare()` 오름차순(항상 결정적 순서 보장).
 */
function compareAssets(
  a: ApiAsset,
  b: ApiAsset,
  statusByAsset: Map<string, ApiHotspotStatus>
): number {
  const ra = rankAsset(a, statusByAsset.get(a.asset_id));
  const rb = rankAsset(b, statusByAsset.get(b.asset_id));
  if (ra.tier !== rb.tier) return ra.tier - rb.tier;
  if (ra.tier <= 2) {
    if (rb.tierCount !== ra.tierCount) return rb.tierCount - ra.tierCount;
    if (rb.totalCount !== ra.totalCount) return rb.totalCount - ra.totalCount;
  }
  return a.asset_id.localeCompare(b.asset_id);
}

/**
 * 그리드 셀 1칸(세로 카드) — 기존 가로 1행(`EquipmentRow`)을 4열 그리드에 맞게 세로
 * 레이아웃으로 재구성했다(Sprint 18 후속 요청, 목록을 가로로 늘어뜨리지 않고 4×3으로).
 * 순서(품번명·명칭 → 큰 이미지 → 위치·설명 → 이상탐지 배지)는 사용자가 그려 준 와이어프레임
 * 그대로다. 배지·정직성 분기(D87) 로직은 그대로, 배치만 바뀐다.
 */
function EquipmentCard({
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

      <div style={sx("font:11px 'Pretendard';color:var(--dim)")}>
        라인 {asset.line_id ?? "미배정"}
        {status?.model && ` · ${status.model}`}
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
