import Link from "next/link";
import { ConsoleHeader, Spacer } from "@/components/layout/ConsoleFrame";
import { Avatar, Divider, Logo } from "@/components/ui/Chip";
import { Mono } from "@/components/ui/Mono";
import type { ApiAsset } from "@/lib/api";
import { ROLE_USER_NAME } from "@/lib/role";
import { sx } from "@/lib/sx";

/**
 * 자산 화면 공통 헤더 (S9 · S18).
 *
 * ⚠ **MQ-710(실사 화면)은 이 컴포넌트를 쓰지 않는다** — 자체 최소 헤더를 만든다.
 *   두 태스크가 같은 파일을 건드리지 않게 한 계획이므로, 여기서 실사 쪽 요구를 미리
 *   반영하지 않는다.
 *
 * 표시 규칙 — **없는 값을 채우지 않는다** (D62 · `frontend/README §설계 계약`)
 *   - `category`·`status` 가 `null` 이면 **배지를 만들지 않는다**. `"일반"`·`"정상"` 으로
 *     채우면 없는 사실이 화면에 생긴다.
 *   - 금액·날짜가 `null` 이면 `"미상"` 이라고 **명시**한다. 빈 칸으로 두면 0원·오늘로 읽힌다.
 *   - `status` 는 백엔드 원 어휘 그대로 찍는다 — 한국어 라벨 맵을 여기서 만들지 않는다.
 *     맵을 두면 모르는 값이 조용히 빈 배지가 되고, 그게 D87 이 막으려는 형태다.
 */

const str = (v: unknown): string => (typeof v === "string" ? v : "");

/** 금액 — `null` 은 0 이 아니다. 모르면 모른다고 쓴다. */
function won(v: number | null | undefined): string {
  return typeof v === "number" ? `${v.toLocaleString("ko-KR")}원` : "미상";
}

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <span style={sx("display:inline-flex;gap:5px;align-items:baseline")}>
      <span style={sx("font:11px 'Pretendard';color:var(--dim2)")}>{label}</span>
      <span style={sx("font:11.5px 'Pretendard';color:var(--ink2)")}>{children}</span>
    </span>
  );
}

function TagBadge({ children }: { children: React.ReactNode }) {
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

/**
 * 헤더 바 + 사실 스트립 두 줄을 함께 낸다. `ConsoleFrame` 안에 바로 넣는다.
 * `right` 는 헤더 우측 여분 자리(예: 다른 화면으로 가는 링크).
 */
export function AssetHeader({ asset, right }: { asset: ApiAsset; right?: React.ReactNode }) {
  const equipment = Array.isArray(asset.equipment) ? asset.equipment : [];
  const count = typeof asset.equipment_count === "number" ? asset.equipment_count : equipment.length;

  return (
    <>
      <ConsoleHeader>
        <Logo />
        <span style={sx("font:600 13px 'Pretendard';color:var(--ink)")}>MaintQ</span>
        <Divider />
        <Link
          href="/technician/asset"
          style={sx("font:12px 'Pretendard';color:var(--blue-tx);text-decoration:none")}
        >
          ← 자산 목록
        </Link>
        <Divider />
        <Mono size={12.5}>{asset.asset_id}</Mono>
        <span style={sx("font:700 13px 'Pretendard';color:var(--ink)")}>{asset.name}</span>
        {/* null 이면 배지 자체가 없다 — "미분류"로 채우지 않는다 */}
        {asset.category && <TagBadge>{asset.category}</TagBadge>}
        {asset.status && <TagBadge>{asset.status}</TagBadge>}
        {right}
        <Spacer />
        <span style={sx("font:12px 'Pretendard';color:var(--dim)")}>
          정비사 {ROLE_USER_NAME.technician}
        </span>
        <Avatar />
      </ConsoleHeader>

      <div
        style={sx(
          "display:flex;align-items:center;gap:16px;flex-wrap:wrap;padding:9px 16px;" +
            "border-bottom:1px solid var(--line);background:var(--panel)"
        )}
      >
        <Fact label="라인">
          {asset.line_id === null || asset.line_id === undefined ? (
            "미배정"
          ) : (
            <Mono size={11.5}>{asset.line_id}</Mono>
          )}
        </Fact>
        <Fact label="취득일">
          {asset.acquired_at ? <Mono size={11.5}>{asset.acquired_at}</Mono> : "미상"}
        </Fact>
        <Fact label="취득가액">{won(asset.acquisition_cost)}</Fact>
        <Fact label="장부가액">{won(asset.book_value)}</Fact>
        <Fact label="하위 설비">
          <Mono size={11.5}>{count}</Mono>대
        </Fact>
        {equipment.length > 0 && (
          <span style={sx("display:inline-flex;gap:6px;flex-wrap:wrap")}>
            {equipment.map((e, i) => (
              <TagBadge key={`${str(e.equipment_id)}-${i}`}>
                {str(e.equipment_id)}
                {str(e.model) && ` · ${str(e.model)}`}
              </TagBadge>
            ))}
          </span>
        )}
      </div>
    </>
  );
}
