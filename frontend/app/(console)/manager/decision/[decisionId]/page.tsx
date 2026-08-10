"use client";

import { useCallback, useEffect, useState } from "react";
import { ConsoleFrame, ConsoleHeader, ScreenStack, Spacer } from "@/components/layout/ConsoleFrame";
import { StatusBanner } from "@/components/layout/StatusBanner";
import { DecisionDetail } from "@/components/queue/DecisionDetail";
import { Avatar, Divider, Logo } from "@/components/ui/Chip";
import { ApiError, extractDetail, getDecision, type ApiDecision } from "@/lib/api";
import { ROLE_USER_NAME } from "@/lib/role";
import { sx } from "@/lib/sx";
import Link from "next/link";

/**
 * `/manager/decision/{decisionId}` — 처분 상세·서명 (S10 계층 3, D18: 승인은 채팅 밖).
 *
 * Stage 5(MQ-709a)가 놓아 둔 스텁(`ApprovalQueueScreen` 위임)을 **교체한 것**이다.
 * 스텁이 있었던 이유는 `queueState.detailHref()` 가 처분서를 이 경로로 보내는데 라우트가
 * 없어 404 였기 때문이고, 이제 실제 화면이 그 자리에 선다.
 *
 * ⛔ **목업 폴백을 두지 않는다.** 승인 큐(`ApprovalQueueScreen`)는 배너를 달고 목업으로
 *   떨어지지만, 여기는 *서명*하는 화면이다. 연결이 없는데 그럴듯한 처분서를 그리면
 *   "서명했다"는 오해를 만들 수 있다 — 못 읽었으면 못 읽었다고 말한다 (D65·D87).
 */
export default function DecisionDetailPage({ params }: { params: { decisionId: string } }) {
  const id = decodeURIComponent(params.decisionId);
  const [decision, setDecision] = useState<ApiDecision | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setDecision(await getDecision("manager", id));
      setError(null);
    } catch (e) {
      // 404(없는 결정)와 연결 실패를 구분해 보여 준다 — 둘은 사람이 할 일이 다르다 (D38)
      setDecision(null);
      setError(
        e instanceof ApiError
          ? `${e.status} — ${extractDetail(e.body)}`
          : `백엔드에 연결하지 못했습니다 — ${String(e)}`
      );
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <ScreenStack>
      {error && (
        <StatusBanner tone="warn">
          ⚠ 처분 결정을 불러오지 못했습니다 — {error} (
          <code>uv run uvicorn backend.main:app --port 8003</code>)
        </StatusBanner>
      )}
      {notice && <StatusBanner tone="info">{notice}</StatusBanner>}

      <ConsoleFrame>
        <ConsoleHeader>
          <Logo />
          <span style={sx("font:600 13px 'Pretendard';color:var(--ink)")}>MaintQ</span>
          <Divider />
          <span style={sx("font:700 13px 'Pretendard';color:var(--ink)")}>처분 결정 상세</span>
          <Link
            href="/manager"
            style={sx("font:11px 'Pretendard';color:var(--blue-br);text-decoration:underline")}
          >
            ← 승인 큐
          </Link>
          <Spacer />
          <span style={sx("font:12px 'Pretendard';color:var(--dim)")}>
            팀장 {ROLE_USER_NAME.manager}
          </span>
          <Avatar />
        </ConsoleHeader>

        {decision ? (
          <DecisionDetail
            decision={decision}
            onUpdated={(updated) => {
              // 상세를 갱신된 결정으로 교체한다 — `signed` 로 전환되면 서명 버튼이 사라진다
              setDecision(updated);
              setNotice(`${updated.decision_id} — 상태 ${updated.state}`);
            }}
            onReload={() => void load()}
          />
        ) : (
          <div style={sx("padding:34px 20px;font:12.5px/1.7 'Pretendard';color:var(--dim)")}>
            {loading ? (
              "불러오는 중…"
            ) : (
              <>
                <b style={sx("color:var(--ink2)")}>
                  {id} 의 처분 결정을 표시할 수 없습니다.
                </b>
                <br />
                목업으로 대신 그리지 않습니다 — 서명 화면이 실제 근거 없이 뜨면 안 됩니다.
              </>
            )}
          </div>
        )}
      </ConsoleFrame>
    </ScreenStack>
  );
}
