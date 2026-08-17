"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ConsoleFrame, ConsoleHeader, ScreenStack, Spacer } from "@/components/layout/ConsoleFrame";
import { StatusBanner } from "@/components/layout/StatusBanner";
import { Avatar, Divider, Logo } from "@/components/ui/Chip";
import { Mono } from "@/components/ui/Mono";
import { getAssets, getHotspotStatus, type ApiAsset, type ApiHotspotStatus } from "@/lib/api";
import { ROLE_USER_NAME } from "@/lib/role";
import { sx } from "@/lib/sx";

/**
 * `/technician/equipment-status` — 설비 하이라이트 대시보드 목록 (Sprint 10 브레인스토밍 C).
 *
 * 독립된 신규 화면이다(`asset` 목록과 별개, spec §4-1 "독립된 새 대시보드 화면"). 자산마다
 * `hotspot-status`를 조회해 배지(🔴N 🟠N 🔵N)를 붙인다 — 9개뿐이라 병렬 호출로 충분하다.
 */
export default function EquipmentStatusListPage() {
  const [assets, setAssets] = useState<ApiAsset[] | null>(null);
  const [statusByAsset, setStatusByAsset] = useState<Map<string, ApiHotspotStatus>>(new Map());
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    getAssets("technician")
      .then(async (items) => {
        if (!alive) return;
        setAssets(items);
        setError(null);
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

        <div style={sx("padding:14px 16px;display:flex;flex-direction:column;gap:10px")}>
          {assets === null ? (
            <div style={sx("font:12.5px 'Pretendard';color:var(--dim);padding:20px 0")}>
              불러오는 중…
            </div>
          ) : (
            assets.map((a) => (
              <EquipmentRow key={a.asset_id} asset={a} status={statusByAsset.get(a.asset_id)} />
            ))
          )}
        </div>
      </ConsoleFrame>
    </ScreenStack>
  );
}

function EquipmentRow({
  asset,
  status,
}: {
  asset: ApiAsset;
  status: ApiHotspotStatus | undefined;
}) {
  const parts = status?.parts ?? [];
  const counts = { red: 0, orange: 0, blue: 0 };
  for (const p of parts) {
    if (p.color === "red") counts.red += 1;
    else if (p.color === "orange") counts.orange += 1;
    else if (p.color === "blue") counts.blue += 1;
  }

  return (
    <Link
      href={`/technician/equipment-status/${encodeURIComponent(asset.asset_id)}`}
      style={sx(
        "border:1px solid var(--line);border-radius:8px;background:var(--panel);padding:11px 14px;" +
          "display:flex;align-items:center;gap:12px;flex-wrap:wrap;text-decoration:none"
      )}
    >
      <Mono size={12}>{asset.asset_id}</Mono>
      <span style={sx("font:700 13px 'Pretendard';color:var(--ink);min-width:180px")}>
        {asset.name}
      </span>
      <span style={sx("font:11.5px 'Pretendard';color:var(--dim)")}>
        라인 {asset.line_id ?? "미배정"}
      </span>
      <div style={sx("flex:1")} />
      {status === undefined ? (
        <span style={sx("font:11px 'Pretendard';color:var(--dim2)")}>확인 중…</span>
      ) : status.status !== "ok" ? (
        <span style={sx("font:11px 'Pretendard';color:var(--dim2)")}>상태 미상</span>
      ) : (
        <div style={sx("display:flex;gap:8px")}>
          {counts.red > 0 && <Badge color="var(--error-tx)">🔴 {counts.red}</Badge>}
          {counts.orange > 0 && <Badge color="var(--orange-tx)">🟠 {counts.orange}</Badge>}
          {counts.blue > 0 && <Badge color="var(--blue-tx)">🔵 {counts.blue}</Badge>}
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
