"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { countHotspotColors, EquipmentCard } from "@/components/asset/EquipmentCard";
import { ConsoleFrame, ConsoleHeader, ScreenStack, Spacer } from "@/components/layout/ConsoleFrame";
import { StatusBanner } from "@/components/layout/StatusBanner";
import { Avatar, Divider, Logo } from "@/components/ui/Chip";
import { Mono } from "@/components/ui/Mono";
import { getAssets, getHotspotStatus, type ApiAsset, type ApiHotspotStatus } from "@/lib/api";
import { ROLE_USER_NAME } from "@/lib/role";
import { sx } from "@/lib/sx";

/** 한 페이지에 보여줄 카드 수 — 가로 3 × 세로 3 그리드(사용자 요청, 2026-08-24 4×3에서 축소). */
const PAGE_SIZE = 9;
const GRID_COLS = 3;

/**
 * `/technician/equipment-status` — 설비 하이라이트 대시보드 목록 (Sprint 10 브레인스토밍 C).
 *
 * 독립된 신규 화면이다(`asset` 목록과 별개, spec §4-1 "독립된 새 대시보드 화면"). 자산마다
 * `hotspot-status`를 조회해 배지(🔴N 🟠N 🔵N)를 붙인다 — 9개뿐이라 병렬 호출로 충분하다.
 * 카드는 3×3 그리드로 페이지네이션된다(한 페이지 9개). 오른쪽 사이드바는 다른 메뉴·
 * 워크플로우를 위해 비워 둔 자리다(2026-08-24 사용자 요청 — 무엇을 넣을지는 미정, 지금은
 * 구조만 잡아 둔다. 없는 기능을 있는 것처럼 채우지 않는다, D87과 같은 태도).
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

        <div style={sx("padding:14px 16px;display:grid;grid-template-columns:1fr 240px;gap:16px")}>
          <div style={sx("display:flex;flex-direction:column;gap:14px;min-width:0")}>
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

          <WorkflowSidebar />
        </div>
      </ConsoleFrame>
    </ScreenStack>
  );
}

/**
 * 오른쪽 사이드바 — 다른 메뉴·워크플로우 자리(2026-08-24 사용자 요청). 이 화면(설비
 * 하이라이트)에서 자연스럽게 이어지는 정비사 워크플로우 진입점 2개만 둔다 — 특정
 * asset_id·po_id가 필요한 화면(발주 상세·처분 사전판정 하위 화면 등)은 단독 메뉴로
 * 부적합해 제외했다(사용자 확인, 2026-08-24). 진단 챗봇은 이미 우하단 `ChatFab`이
 * 커버하므로 중복으로 안 올린다.
 */
function WorkflowSidebar() {
  return (
    <aside
      style={sx(
        "border-left:1px solid var(--line);padding-left:16px;display:flex;" +
          "flex-direction:column;gap:8px"
      )}
    >
      <span style={sx("font:700 11.5px 'Pretendard';color:var(--dim)")}>빠른 메뉴</span>
      {/* D158(MQ-1914) — 사업장 평면도: 설비를 위치로 골라 진단 콘솔로 들어간다(S1) */}
      <SidebarLink href="/technician/site" icon="🗺" label="사업장 평면도" />
      <SidebarLink href="/technician/po/new" icon="📝" label="발주 신규 작성" />
      <SidebarLink href="/technician/asset" icon="🗂" label="자산 목록 · 처분 사전판정" />
    </aside>
  );
}

function SidebarLink({ href, icon, label }: { href: string; icon: string; label: string }) {
  return (
    <Link
      href={href}
      style={sx(
        "border:1px solid var(--line);border-radius:8px;background:var(--panel);" +
          "padding:10px 12px;display:flex;align-items:center;gap:8px;text-decoration:none;" +
          "font:600 12px 'Pretendard';color:var(--ink)"
      )}
    >
      <span style={sx("font-size:14px")}>{icon}</span>
      {label}
    </Link>
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
