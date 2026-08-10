"use client";

import { useEffect, useState } from "react";
import { ScreenStack } from "@/components/layout/ConsoleFrame";
import { StatusBanner } from "@/components/layout/StatusBanner";
import { ResidualRiskCard } from "@/components/asset/ResidualRiskCard";
import { VerificationMatrix } from "@/components/asset/VerificationMatrix";
import { Mono } from "@/components/ui/Mono";
import { ApiError, errorBody, getOwnership } from "@/lib/api";
import {
  auditRows,
  reasonView,
  toRows,
  verdictView,
  type OwnershipApi,
  type Tone,
} from "@/lib/ownership";
import { sx } from "@/lib/sx";

/**
 * /technician/asset/{assetId}/ownership — S18 중고 거래 실사 검증 화면.
 *
 * 이 화면이 지키는 원칙은 하나다: **확인 안 된 항목을 확인된 것처럼 보여주지 않는다** (D87).
 * 그래서 판단은 전부 `lib/ownership.ts` 에 있고 이 파일은 데이터를 가져와 넘길 뿐이다.
 *
 * 4가지 실패를 각각 다르게 렌더한다 — 뭉치면 전부 "결과 없음"으로 보이고,
 * "결과 없음"은 화면에서 "문제 없음"과 구별되지 않는다:
 *   ⓐ `no_host_asset`(분전반) → 판정 **대상이 아니다**. ⛔ "문제 없음" 아님
 *   ⓑ 도구 오류(`internal_error` 등) → 오류 배너. ⛔ 빈 매트릭스를 "확인 결과 없음"으로 렌더 금지
 *   ⓒ 백엔드 미기동 → 목업 폴백 + 경고 배너 (화면 B 선례)
 *   ⓓ 미지 `verdict` → warn + 원문 (`verdictView`)
 *
 * ⛔ 자산 헤더는 이 파일이 **자체로** 최소한만 만든다. 같은 스테이지의 다른 태스크가
 *   만드는 컴포넌트에 의존하지 않는다.
 */

type Source = "loading" | "live" | "mock" | "blocked";

export default function OwnershipPage({ params }: { params: { assetId: string } }) {
  const assetId = decodeURIComponent(params.assetId);
  const [source, setSource] = useState<Source>("loading");
  const [data, setData] = useState<OwnershipApi | null>(null);
  /** 판정이 성립하지 않은 경우의 사유. 값이 있으면 매트릭스를 렌더하지 않는다 */
  const [failure, setFailure] = useState<{ text: string; tone: Tone; reason: string } | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;

    (async () => {
      try {
        const res = await getOwnership("technician", assetId);
        if (!alive) return;
        if (res.status === "ok") {
          setData(res as unknown as OwnershipApi);
          setFailure(null);
          setSource("live");
        } else {
          // 200 인데 status 가 ok 가 아닌 경우까지 방어한다 — 빈 매트릭스로 흘리지 않는다
          const reason = typeof res.reason === "string" ? res.reason : "";
          setFailure({ ...reasonView(reason), reason: reason || "(사유 없음)" });
          setData(null);
          setSource("blocked");
        }
      } catch (e) {
        if (!alive) return;
        if (e instanceof ApiError) {
          // 백엔드는 살아 있다 — 404/5xx 는 **판정이 성립하지 않았다**는 사실이다.
          const body = errorBody(e);
          const reason = typeof body?.reason === "string" ? body.reason : "";
          const message = typeof body?.message === "string" ? body.message : "";
          const view = reasonView(reason);
          setFailure({
            text: message || view.text,
            tone: view.tone,
            reason: reason || `HTTP ${e.status}`,
          });
          setData(null);
          setSource("blocked");
        } else {
          // 백엔드 미기동 — 목업으로 떨어지되 **배너로 명시**한다.
          setData(MOCK);
          setFailure(null);
          setNotice(
            "백엔드에 연결하지 못했습니다 — 아래는 실제 실사 결과가 아니라 목업 예시입니다."
          );
          setSource("mock");
        }
      }
    })();

    return () => {
      alive = false;
    };
  }, [assetId]);

  const rows = data ? toRows(data) : [];
  const verdict = typeof data?.verdict === "string" ? data.verdict : "";
  const banner = verdict ? verdictView(verdict) : null;
  // ⛔ 키가 없을 때 `0` 으로 메우지 않는다 — `PARTIAL` 배너 옆에 "미확인 0건" 이 찍히면
  //    헤드라인("확인되지 않은 항목이 남아 있습니다")과 정면으로 모순된다 (D62·D87).
  const unverified: number | null = Array.isArray(data?.unverified)
    ? data.unverified.length
    : null;
  const violations = auditRows(rows);

  // 각 카드가 이미 1020px 자기 테두리를 갖는다 — `ConsoleFrame`(1020px 고정 박스)으로 한 번 더
  // 감싸면 내용이 1px 잘린다. 세로 스택만 쓴다.
  return (
    <ScreenStack>
        <Header assetId={data?.asset_id ?? assetId} source={source} />

        {/* 목업일 때는 판정 배너보다 "이건 실데이터가 아니다"가 먼저다 */}
        {notice && <StatusBanner tone="warn">⚠ {notice}</StatusBanner>}

        {source === "loading" && (
          <StatusBanner tone="info">실사 결과를 불러오는 중입니다…</StatusBanner>
        )}

        {/* ⓐⓑ 판정이 성립하지 않은 경우 — 매트릭스를 렌더하지 않는다 */}
        {failure && (
          <>
            <StatusBanner tone="error">
              <span>
                <strong>실사 판정 없음</strong> — {failure.text}
              </span>
            </StatusBanner>
            <p style={sx("width:1020px;max-width:100%;margin:0;font:12px/1.7 'Pretendard';color:var(--dim)")}>
              사유 코드 <Mono>{failure.reason}</Mono> · 이 결과는 &ldquo;확인해 보니 문제가
              없었다&rdquo;가 아니라 <strong>판정 자체를 하지 않았다</strong>는 뜻입니다.
              체크리스트를 표시하지 않는 이유도 같습니다 — 빈 표는 확인 결과처럼 보입니다.
            </p>
          </>
        )}

        {/* ⓓ 판정 배너 — PARTIAL 이면 최상단 warn. 미지 판정도 초록이 되지 않는다 */}
        {banner && (
          <div
            style={sx(
              "width:1020px;max-width:100%;border:1px solid;border-radius:8px;padding:11px 14px;" +
                `display:flex;align-items:baseline;gap:10px;${TONE_BANNER[banner.tone]}`
            )}
          >
            <Mono>{verdict}</Mono>
            <span style={sx("font:600 12.5px/1.6 'Pretendard'")}>{banner.headline}</span>
            <span style={sx("margin-left:auto;font:11px 'JetBrains Mono',monospace;opacity:.85")}>
              미확인 {unverified === null ? "미상" : `${unverified}건`}
            </span>
          </div>
        )}

        {data && <VerificationMatrix rows={rows} />}

        {data && (
          <ResidualRiskCard
            residualRisk={data.residual_risk}
            mitigation={data.mitigation}
            notConsidered={data.not_considered}
            disclaimer={data.disclaimer}
          />
        )}

        {data && violations.length === 0 && (
          <p style={sx("width:1020px;max-width:100%;margin:0;font:11px/1.7 'Pretendard';color:var(--dim2)")}>
            표시 검사(`auditRows`) 위반 0건 — 미확인 항목이 확인된 것처럼 보이지 않는지,
            미확인마다 사유가 있는지, 카테고리 9종이 전부 있는지를 렌더 직전에 확인했습니다.
          </p>
        )}
    </ScreenStack>
  );
}

/** 판정 배너 톤 → 색. 매트릭스와 달리 이 배너는 화면 셸의 일부라 여기서 색을 잡는다. */
const TONE_BANNER: Record<Tone, string> = {
  ok: "border-color:var(--ok-bd);background:var(--ok-bg);color:var(--ok-tx)",
  warn: "border-color:var(--saf-cite-bd);background:var(--saf-cite-bg);color:var(--orange-tx)",
  danger: "border-color:var(--error-tx);background:transparent;color:var(--error-tx)",
  muted: "border-color:var(--line2);background:transparent;color:var(--dim)",
  // 모르는 어휘 전용 (D87) — `lib/ownership.TONE_STYLE.unknown` 과 같은 규약.
  unknown:
    "border-color:var(--error-tx);border-style:dashed;background:transparent;color:var(--error-tx)",
};

const SOURCE_TEXT: Record<Source, string> = {
  loading: "불러오는 중",
  live: "라이브 (GET /api/assets/{id}/ownership)",
  mock: "목업 폴백 — 실 데이터 아님",
  blocked: "판정 없음",
};

/**
 * 최소 헤더. 자산 이름·취득가 같은 값은 **여기서 조회하지 않는다** — 이 화면이 책임지는
 * 것은 실사 판정이고, 조회하지 않은 값을 헤더에 채우면 그것부터가 미확인의 확인 표시다.
 */
function Header({ assetId, source }: { assetId: string; source: Source }) {
  return (
    <div
      style={sx(
        "width:1020px;max-width:100%;display:flex;align-items:baseline;gap:10px;" +
          "padding-bottom:2px;border-bottom:1px solid var(--line)"
      )}
    >
      <span style={sx("font:700 15px 'Pretendard';color:var(--ink)")}>중고 거래 실사</span>
      <Mono>{assetId}</Mono>
      <span style={sx("margin-left:auto;font:11px 'Pretendard';color:var(--dim2)")}>
        {SOURCE_TEXT[source]}
      </span>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* 백엔드 미기동 폴백 픽스처                                                    */

/**
 * ⛔ 데모용 "잘 나온 결과"가 아니다. 실제 응답과 같은 구조 + 같은 정직성 규칙을 지킨다 —
 *   9카테고리 전부, `VERIFIED` 엔 근거, `UNVERIFIED` 엔 사유. 목업에서만 전부 초록이면
 *   백엔드가 꺼진 데모에서 정확히 우리가 막으려는 오해가 생긴다.
 */
const MOCK: OwnershipApi = {
  status: "ok",
  asset_id: "(목업)",
  verdict: "PARTIAL",
  categories: [
    {
      category: "물리적 상태",
      items: [
        { item: "정밀도 검사", state: "UNVERIFIED", evidence: null, limit: "현장 실사 원천 없음" },
        { item: "진동·소음 측정", state: "UNVERIFIED", evidence: null, limit: "현장 실사 원천 없음" },
      ],
    },
    {
      category: "가동 이력",
      items: [
        { item: "누적 가동시간", state: "UNVERIFIED", evidence: null, limit: "가동시간 원천 없음 (D70)" },
      ],
    },
    {
      category: "정비 이력",
      items: [
        {
          item: "수리 이력 (사내 기록)",
          state: "VERIFIED",
          evidence: "repair_records 서명분 조회 결과 (목업)",
          limit: null,
        },
      ],
    },
    {
      category: "기술적 진부화",
      items: [
        { item: "부품 단종 여부", state: "VERIFIED", evidence: "parts.discontinued 조회 (목업)", limit: null },
      ],
    },
    {
      category: "권리관계",
      items: [
        { item: "담보 설정 (사내 기록)", state: "VERIFIED", evidence: "assets.has_lien=0 (목업)", limit: null },
        {
          item: "리스 여부",
          state: "UNVERIFIED",
          evidence: null,
          limit: "원천 없음 — 외부 기관을 런타임에 조회하지 않는다",
        },
      ],
    },
    {
      category: "법정 요건",
      items: [
        { item: "안전검사 이력", state: "UNVERIFIED", evidence: null, limit: "사전 수집 스냅샷 없음" },
      ],
    },
    {
      category: "재무·회계",
      items: [
        { item: "장부가", state: "VERIFIED", evidence: "assets.book_value 조회 (목업)", limit: null },
      ],
    },
    {
      category: "시장·가격",
      items: [
        { item: "실거래가", state: "UNVERIFIED", evidence: null, limit: "실거래 원천 없음 — 목업 잔가곡선은 추정치다 (D65)" },
      ],
    },
    {
      category: "이전 비용",
      items: [
        { item: "해체·운송 견적", state: "UNVERIFIED", evidence: null, limit: "이전 견적 원천 없음" },
      ],
    },
  ],
  unverified: ["정밀도 검사", "진동·소음 측정", "누적 가동시간", "리스 여부", "안전검사 이력", "실거래가", "해체·운송 견적"],
  residual_risk: "(목업) 제3자 담보권 존재 가능성 배제 불가 · 그 밖 미확인 항목 잔존",
  mitigation: "(목업) 매도인 진술보장 + 손해배상 특약으로 계약상 배분 권고",
  not_considered: ["외부 기관 조회 결과", "현장 실사 결과"],
  disclaimer:
    "이 화면은 백엔드에 연결하지 못해 목업을 표시하고 있습니다. 실제 자산의 실사 결과가 아닙니다.",
};
