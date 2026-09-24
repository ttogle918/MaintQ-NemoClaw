"use client";

import { useEffect, useState } from "react";
import {
  ApiError,
  errorBody,
  extractDetail,
  getA2aHistory,
  type ApiA2aHistoryItem,
} from "@/lib/api";
import { a2aStatusLabel, a2aStatusTone, skillView, type Tone } from "@/lib/a2a";
import { ConsoleFrame, ConsoleHeader, ScreenStack, Spacer } from "@/components/layout/ConsoleFrame";
import { Divider, Logo } from "@/components/ui/Chip";
import { sx } from "@/lib/sx";

/**
 * `/manager/a2a` — 통합 A2A 이력 화면 (`GET /api/a2a/history`, D114, MQ-1610).
 *
 * request-withdrawal(FinAllQ 출금요청)·lookup-clause(InsuQ 약관조회)·assess-loan(FinAllQ 담보대출
 * 사전판정) 3종을 필터 없이 한 화면에 모아 보여준다 — 맥락별 예쁜 렌더(채팅 카드·PO 상세 패널·
 * 위험등급 이력 패널)는 각각 다른 화면(MQ-1607/1608/1609)이 이미 담당하고, 이 화면은 "원문을 볼
 * 수 있다"는 감사(audit) 용도에 집중한다.
 *
 * ⛔ 이 화면은 `read_trace` 를 부르지 않는다 — 여는 원문은 전부 `GET /api/a2a/history`
 *   (D114, D76-2) 를 통해서만 온다. 새 백엔드 로직을 이 태스크가 추가하지 않는다.
 * ⛔ 상태색·스킬 라벨은 `a2aStatusTone`/`skillView`(`lib/a2a.ts`) 를 거쳐서만 정한다 — 이 파일에
 *   `status`/`skill` 문자열 직접 비교가 없다 (D87).
 */
export function A2aHistoryScreen() {
  const [items, setItems] = useState<ApiA2aHistoryItem[] | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setFailure(null);
    setItems(null);
    getA2aHistory("manager", { limit: 100 })
      .then((res) => {
        if (!alive) return;
        setItems(Array.isArray(res.items) ? res.items : []);
      })
      .catch((e: unknown) => {
        if (!alive) return;
        if (e instanceof ApiError) {
          const body = errorBody(e);
          const reason = typeof body?.reason === "string" ? body.reason : "";
          const message = extractDetail(e.body);
          setFailure(reason ? `${reason} — ${message}` : message);
        } else {
          setFailure("백엔드에 연결하지 못했습니다 — A2A 이력을 불러오지 못했습니다.");
        }
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, []);

  return (
    <ScreenStack>
      <ConsoleFrame>
        <ConsoleHeader>
          <Logo />
          <span style={sx("font:600 13px 'Pretendard';color:var(--ink)")}>MaintQ</span>
          <Divider />
          <span style={sx("font:700 12.5px 'Pretendard';color:var(--ink2)")}>A2A 이력</span>
          <Spacer />
          <span style={sx("font:11px 'Pretendard';color:var(--dim2)")}>
            request-withdrawal · lookup-clause · assess-loan 통합 (D114)
          </span>
        </ConsoleHeader>

        <div style={sx("padding:16px 18px;display:flex;flex-direction:column;gap:12px")}>
          {loading && (
            <div style={sx("font:12px 'Pretendard';color:var(--dim)")}>불러오는 중…</div>
          )}

          {failure && !loading && (
            <div
              style={sx(
                "border:1.5px dashed var(--error-tx);border-radius:6px;padding:8px 10px;" +
                  "font:11px/1.6 'Pretendard';color:var(--error-tx)"
              )}
            >
              <b>A2A 이력을 불러오지 못했습니다</b>
              <br />
              {failure}
            </div>
          )}

          {items !== null && !loading && !failure && items.length === 0 && (
            <div style={sx("font:11.5px/1.6 'Pretendard';color:var(--dim)")}>
              아직 A2A 호출 이력이 없습니다.
            </div>
          )}

          {items !== null && !loading && !failure && items.length > 0 && (
            <div style={sx("display:flex;flex-direction:column;gap:8px")}>
              {items.map((item) => (
                <A2aHistoryRow key={item.request_chain_id} item={item} />
              ))}
            </div>
          )}
        </div>
      </ConsoleFrame>
    </ScreenStack>
  );
}

/**
 * 톤 → 글자색. `a2aStatusTone` 이 정한 톤만 색으로 옮긴다(D87) — `ok` 는 정보색(`--blue-tx`)을
 * 쓴다(`RiskGradeGrid`/`DeadlinesPanel` 의 `HashVerified` 선례와 동일한 이유 — L2 가 컴포넌트의
 * `--green`·`--ok` 색 토큰을 전부 금지한다). `a2aStatusTone` 은 현재 `warn` 을 만들어 내지 않지만
 * `Record<Tone,…>` 는 total 이어야 하므로 항목을 둔다.
 */
const TONE_COLOR: Record<Tone, string> = {
  ok: "var(--blue-tx)",
  warn: "var(--orange-tx)",
  error: "var(--error-tx)",
  unknown: "var(--dim)",
};

function A2aHistoryRow({ item }: { item: ApiA2aHistoryItem }) {
  const skill = skillView(item.skill);
  const tone = a2aStatusTone(item.status);
  return (
    <details
      style={sx(
        "border:1px solid var(--line);border-radius:8px;background:var(--panel);padding:9px 12px"
      )}
    >
      <summary
        style={sx("cursor:pointer;display:flex;align-items:center;gap:10px;flex-wrap:wrap")}
      >
        <span style={sx("font:700 12px 'Pretendard';color:var(--ink)")}>{skill.label}</span>
        <span style={sx(`font:700 11px 'Pretendard';color:${TONE_COLOR[tone]}`)}>
          {a2aStatusLabel(item.status)}
        </span>
        {/* 원 어휘도 함께 — 감사 화면이라 라벨만 두면 원문이 사라진다 (MQ-1911) */}
        {item.status != null && (
          <span style={sx(`font:10.5px 'JetBrains Mono',monospace;color:${TONE_COLOR[tone]}`)}>
            {item.status}
          </span>
        )}
        <span style={sx("font:10.5px 'JetBrains Mono',monospace;color:var(--dim2)")}>
          {item.request_chain_id}
        </span>
        <div style={sx("flex:1")} />
        <span style={sx("font:10.5px 'Pretendard';color:var(--dim2)")}>{item.ts}</span>
      </summary>

      <div style={sx("margin-top:8px;display:flex;flex-direction:column;gap:8px")}>
        <div style={sx("font:10.5px 'Pretendard';color:var(--dim2)")}>
          세션 <span style={sx("font:10.5px 'JetBrains Mono',monospace")}>{item.session_id}</span>
        </div>

        <A2aPayloadBlock label="request" value={item.request} />
        <A2aPayloadBlock label="response" value={item.response} />
      </div>
    </details>
  );
}

function A2aPayloadBlock({
  label,
  value,
}: {
  label: string;
  value: Record<string, unknown> | null;
}) {
  return (
    <div style={sx("display:flex;flex-direction:column;gap:3px")}>
      <span style={sx("font:10px 'Pretendard';color:var(--dim2)")}>{label}</span>
      <pre
        style={sx(
          "margin:0;border:1px solid var(--line2);border-radius:6px;background:var(--raise);" +
            "padding:8px 10px;font:10.5px/1.5 'JetBrains Mono',monospace;color:var(--ink2);" +
            "white-space:pre-wrap;word-break:break-all;max-height:280px;overflow:auto"
        )}
      >
        {value === null ? "(없음)" : JSON.stringify(value, null, 2)}
      </pre>
    </div>
  );
}
