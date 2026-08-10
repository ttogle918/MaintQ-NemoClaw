"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import {
  ConsoleFrame,
  ConsoleHeader,
  ScreenStack,
  Spacer,
} from "@/components/layout/ConsoleFrame";
import { StatusBanner } from "@/components/layout/StatusBanner";
import { Avatar, Divider, Logo } from "@/components/ui/Chip";
import { Mono } from "@/components/ui/Mono";
import { getAssets, type ApiAsset } from "@/lib/api";
import { ROLE_USER_NAME } from "@/lib/role";
import { sx } from "@/lib/sx";

/**
 * `/technician/asset` — 설비 자산 목록 (S9 진입).
 *
 * **`asset_id` 가 없는 설비는 여기 나오지 않는다.** `GET /api/assets` 는 `assets` 테이블만
 * 읽는다 — 분전반 인버터(`INV-L1-01`)처럼 호스트 자산이 없는 설비는 **자산이 아니므로**
 * 목록에 없는 것이고, 그건 "처분 가능"도 "문제 없음"도 아니다 (D68). 그 사실을 화면에
 * 한 줄로 적어 둔다 — 목록의 부재를 사용자가 스스로 해석하게 두지 않는다.
 *
 * 백엔드가 없으면 **목업으로 떨어지지 않는다.** 자산 목업을 만들면 존재하지 않는 자산이
 * 처분 판정 화면까지 흘러 들어가고, 그 화면은 "저장하지 않는다"는 말을 지킬 수 없다.
 * 대신 연결 실패를 배너로 말한다.
 */
export default function AssetListPage() {
  const [assets, setAssets] = useState<ApiAsset[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [line, setLine] = useState<number | null>(null);

  useEffect(() => {
    let alive = true;
    getAssets("technician")
      .then((items) => {
        if (alive) {
          setAssets(items);
          setError(null);
        }
      })
      .catch(() => {
        if (alive) {
          setAssets([]);
          setError(
            "백엔드에 연결하지 못했습니다 — 자산 목록을 가져오지 못했습니다. 목업으로 대체하지 않습니다."
          );
        }
      });
    return () => {
      alive = false;
    };
  }, []);

  /** 라인 필터 후보는 **응답이 정한다** — 1~4 를 코드에 박아 두면 라인이 늘 때 조용히 빠진다 */
  const lines = useMemo(() => {
    const set = new Set<number>();
    for (const a of assets ?? []) if (typeof a.line_id === "number") set.add(a.line_id);
    return [...set].sort((x, y) => x - y);
  }, [assets]);

  const shown = (assets ?? []).filter((a) => line === null || a.line_id === line);

  return (
    <ScreenStack>
      {error && <StatusBanner tone="error">⚠ {error}</StatusBanner>}

      <ConsoleFrame>
        <ConsoleHeader>
          <Logo />
          <span style={sx("font:600 13px 'Pretendard';color:var(--ink)")}>MaintQ</span>
          <Divider />
          <span style={sx("font:700 13px 'Pretendard';color:var(--ink)")}>설비 자산</span>
          <Mono size={11.5}>{assets === null ? "…" : `${shown.length}/${assets.length}`}</Mono>
          <Divider />
          <LineFilter lines={lines} value={line} onChange={setLine} />
          <Spacer />
          <span style={sx("font:12px 'Pretendard';color:var(--dim)")}>
            정비사 {ROLE_USER_NAME.technician}
          </span>
          <Avatar />
        </ConsoleHeader>

        <div style={sx("padding:14px 16px;display:flex;flex-direction:column;gap:10px")}>
          {assets === null ? (
            <div style={sx("font:12.5px 'Pretendard';color:var(--dim);padding:20px 0")}>
              자산 목록을 불러오는 중…
            </div>
          ) : shown.length === 0 ? (
            <div
              style={sx(
                "border:1px dashed var(--line2);border-radius:7px;padding:16px;" +
                  "font:12.5px/1.7 'Pretendard';color:var(--dim)"
              )}
            >
              조건에 맞는 자산이 없습니다. 목록이 비어 있다는 것이지 &ldquo;처분할 것이
              없다&rdquo;는 뜻은 아닙니다.
            </div>
          ) : (
            shown.map((a) => <AssetRow key={a.asset_id} asset={a} />)
          )}

          <div style={sx("font:11.5px/1.7 'Pretendard';color:var(--dim2);margin-top:4px")}>
            ※ 호스트 자산이 없는 설비(예: 분전반 인버터 <Mono size={11}>INV-L1-01</Mono>)는{" "}
            <b style={sx("color:var(--dim)")}>자산이 아니므로 이 목록에 없습니다</b> — 처분
            판정의 대상이 아니라는 뜻이며, &ldquo;문제 없음&rdquo;이 아닙니다 (D68).
          </div>
        </div>
      </ConsoleFrame>
    </ScreenStack>
  );
}

function LineFilter({
  lines,
  value,
  onChange,
}: {
  lines: number[];
  value: number | null;
  onChange: (v: number | null) => void;
}) {
  const chip = (on: boolean) =>
    "border-radius:13px;padding:4px 11px;cursor:pointer;font:11.5px 'Pretendard';" +
    (on
      ? "border:1px solid var(--blue-br);background:var(--cite-bg);color:var(--blue-tx)"
      : "border:1px solid var(--line2);background:var(--raise);color:var(--dim)");

  return (
    <div style={sx("display:flex;gap:6px;flex-wrap:wrap")}>
      <button onClick={() => onChange(null)} style={sx(chip(value === null))}>
        전체
      </button>
      {lines.map((l) => (
        <button key={l} onClick={() => onChange(l)} style={sx(chip(value === l))}>
          {l}번 라인
        </button>
      ))}
    </div>
  );
}

/** 금액 — `null` 은 0 이 아니다 (D62). */
function won(v: number | null | undefined): string {
  return typeof v === "number" ? `${v.toLocaleString("ko-KR")}원` : "미상";
}

function AssetRow({ asset }: { asset: ApiAsset }) {
  const count = typeof asset.equipment_count === "number" ? asset.equipment_count : null;

  return (
    <div
      style={sx(
        "border:1px solid var(--line);border-radius:8px;background:var(--panel);padding:11px 14px;" +
          "display:flex;align-items:center;gap:12px;flex-wrap:wrap"
      )}
    >
      <Mono size={12}>{asset.asset_id}</Mono>
      <span style={sx("font:700 13px 'Pretendard';color:var(--ink);min-width:180px")}>
        {asset.name}
      </span>

      {/* null 이면 배지를 만들지 않는다 — 없는 분류를 지어내지 않는다 */}
      {asset.category && <Tag>{asset.category}</Tag>}
      {asset.status && <Tag>{asset.status}</Tag>}

      <span style={sx("font:11.5px 'Pretendard';color:var(--dim)")}>
        라인 {asset.line_id ?? "미배정"}
      </span>
      <span style={sx("font:11.5px 'Pretendard';color:var(--dim)")}>
        설비 {count === null ? "미상" : `${count}대`}
      </span>
      <span style={sx("font:11.5px 'Pretendard';color:var(--dim)")}>
        취득 {asset.acquired_at ?? "미상"}
      </span>
      <span style={sx("font:11.5px 'Pretendard';color:var(--dim)")}>
        장부가 {won(asset.book_value)}
      </span>

      <div style={sx("flex:1")} />
      <Link
        href={`/technician/asset/${encodeURIComponent(asset.asset_id)}/disposal`}
        style={sx(
          "font:12px 'Pretendard';color:var(--blue-tx);text-decoration:none;white-space:nowrap"
        )}
      >
        처분 사전판정 →
      </Link>
    </div>
  );
}

function Tag({ children }: { children: React.ReactNode }) {
  return (
    <span
      style={sx(
        "font:700 9.5px 'JetBrains Mono',monospace;border:1px solid var(--line2);" +
          "border-radius:3px;padding:2px 6px;color:var(--dim);white-space:nowrap"
      )}
    >
      {children}
    </span>
  );
}
