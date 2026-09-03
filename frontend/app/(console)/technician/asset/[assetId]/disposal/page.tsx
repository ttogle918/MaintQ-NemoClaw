"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { AssetHeader } from "@/components/asset/AssetHeader";
import { DisposalPanel } from "@/components/asset/DisposalPanel";
import { DisposalDraftForm } from "@/components/asset/DisposalDraftForm";
import { ConsoleFrame, ScreenStack } from "@/components/layout/ConsoleFrame";
import { StatusBanner } from "@/components/layout/StatusBanner";
import { StateBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Mono } from "@/components/ui/Mono";
import {
  ApiError,
  extractDetail,
  getAsset,
  getDecisions,
  submitDecision,
  type ApiAsset,
  type ApiDecision,
} from "@/lib/api";
import { detailHref, isDraftState } from "@/lib/queueState";
import { sx } from "@/lib/sx";

/**
 * `/technician/asset/{assetId}/disposal` — 처분 사전판정 화면 (S9 → S10 진입).
 *
 * 이 라우트가 하는 일은 셋이다.
 *   ⓐ 자산 사실을 헤더로 보여 준다 (`GET /api/assets/{id}`)
 *   ⓑ 사전판정 패널을 건다 (`DisposalPanel` — 무저장, D71)
 *   ⓒ **이 자산으로 이미 만들어진 처분서 초안**을 보여 주고, 정비사의 명시적 액션으로
 *      승인 큐에 올린다 (`POST /api/decisions/{id}/submit` — 정비사 전용)
 *
 * ⓒ 를 여기 두는 이유는 **관통이 여기서 끊기기 때문**이다. 초안은 에이전트가
 * `generate_disposal_document` 로 만들지만 상태는 `draft` 이고, 승인 큐(`GET /api/approvals`)
 * 는 `pending` 부터 본다. `draft → pending` 은 **사람 전용 API**이고 그 사람은 정비사다
 * (팀장이 부르면 403). 발주에서 그 액션이 채팅 카드의 "팀장 승인 요청" 버튼이었던 것처럼,
 * 처분에는 아직 카드가 없으므로 자산 화면이 그 자리를 맡는다.
 * ⛔ 이 화면은 서명·반려를 하지 않는다 — 그건 승인 큐(팀장)의 일이다 (D18·D10).
 */
export default function AssetDisposalPage({ params }: { params: { assetId: string } }) {
  const assetId = decodeURIComponent(params.assetId);

  const [asset, setAsset] = useState<ApiAsset | null>(null);
  // 초안을 만들면 아래 목록을 다시 그린다(생성 직후 안 보이면 만든 줄 모른다)
  const [draftsKey, setDraftsKey] = useState(0);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    getAsset("technician", assetId)
      .then((a) => {
        if (alive) {
          setAsset(a);
          setError(null);
        }
      })
      .catch((e: unknown) => {
        if (!alive) return;
        setAsset(null);
        setError(
          e instanceof ApiError && e.status === 404
            ? `자산 등록부에 없는 식별자입니다 — ${assetId}`
            : "백엔드에 연결하지 못했습니다 — 자산을 불러오지 못했습니다. 목업으로 대체하지 않습니다."
        );
      });
    return () => {
      alive = false;
    };
  }, [assetId]);

  if (error) {
    return (
      <ScreenStack>
        <StatusBanner tone="error">⚠ {error}</StatusBanner>
        <Link
          href="/technician/asset"
          style={sx("font:12.5px 'Pretendard';color:var(--blue-tx);text-decoration:none")}
        >
          ← 자산 목록으로
        </Link>
      </ScreenStack>
    );
  }

  if (!asset) {
    return (
      <ScreenStack>
        <div style={sx("font:12.5px 'Pretendard';color:var(--dim);padding:24px")}>
          자산을 불러오는 중… <Mono>{assetId}</Mono>
        </div>
      </ScreenStack>
    );
  }

  return (
    <ScreenStack>
      <ConsoleFrame>
        {/*
          S18 실사 화면(MQ-710)으로 가는 **유일한 진입 경로**다 (reviewer W6).
          `AssetHeader.right` 가 정확히 이 자리로 만들어졌는데 비어 있었고, 그러면
          `/…/ownership` 은 URL 을 아는 사람만 볼 수 있다 — 화면이 있는데 없는 것과 같다.
        */}
        <AssetHeader
          asset={asset}
          right={
            <div style={sx("display:flex;align-items:center;gap:12px")}>
              <Link
                href={`/technician/asset/${encodeURIComponent(asset.asset_id)}/evidence`}
                style={sx(
                  "font:12px 'Pretendard';color:var(--blue-tx);text-decoration:none;white-space:nowrap"
                )}
              >
                근거 번들 보기 →
              </Link>
              <Link
                href={`/technician/asset/${encodeURIComponent(asset.asset_id)}/ownership`}
                style={sx(
                  "font:12px 'Pretendard';color:var(--blue-br);text-decoration:underline;white-space:nowrap"
                )}
              >
                실사 체크리스트 →
              </Link>
            </div>
          }
        />
        <DisposalPanel asset={asset} />
        <NewDraftSection assetId={asset.asset_id} onCreated={() => setDraftsKey((k) => k + 1)} />
        <DraftsForAsset assetId={asset.asset_id} key={draftsKey} />
      </ConsoleFrame>
    </ScreenStack>
  );
}

/* -------------------------------------------------------------------------- */

/**
 * 이 자산의 처분서 초안 목록.
 *
 * 목록이 비어 있으면 **비어 있다고 말한다** — "만들 것이 없다"가 아니다.
 * 조회는 `GET /api/decisions`(정비사도 200)를 쓰고 `asset_id` 로 걸러 낸다.
 */
function DraftsForAsset({ assetId }: { assetId: string }) {
  const [items, setItems] = useState<ApiDecision[] | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  const load = useCallback(async () => {
    try {
      const all = await getDecisions("technician");
      setItems(all.filter((d) => d.asset_id === assetId));
      setFailed(false);
    } catch {
      setItems(null);
      setFailed(true);
    }
  }, [assetId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function submit(id: string) {
    try {
      const updated = await submitDecision(id);
      setNotice(`${updated.decision_id} 승인 큐로 전달되었습니다 — ${updated.state}`);
      await load();
    } catch (e) {
      // 403(권한)·409(순서)를 구분해 보여 준다 (D38)
      setNotice(e instanceof ApiError ? `${e.status} — ${extractDetail(e.body)}` : String(e));
    }
  }

  return (
    <section
      style={sx(
        "border-top:1px solid var(--line);background:var(--head);padding:14px 18px;" +
          "display:flex;flex-direction:column;gap:9px"
      )}
    >
      <div style={sx("display:flex;align-items:baseline;gap:9px")}>
        <span style={sx("font:700 12.5px 'Pretendard';color:var(--ink)")}>
          이 자산의 처분서 초안
        </span>
        <span style={sx("font:11.5px 'Pretendard';color:var(--dim2)")}>
          에이전트가 <Mono size={11}>generate_disposal_document</Mono> 로 만든 것만 나옵니다 —
          이 화면은 초안을 만들지 않습니다
        </span>
      </div>

      {notice && <StatusBanner tone="info">{notice}</StatusBanner>}

      {failed ? (
        <Empty>처분서 목록을 불러오지 못했습니다 — 없는 것이 아니라 조회가 실패한 것입니다.</Empty>
      ) : items === null ? (
        <Empty>불러오는 중…</Empty>
      ) : items.length === 0 ? (
        <Empty>
          아직 초안이 없습니다. 위의 <b>진단 콘솔에서 초안 요청</b>으로 에이전트에게 요청하세요.
        </Empty>
      ) : (
        items.map((d) => (
          <DecisionRow key={d.decision_id} d={d} onSubmit={() => void submit(d.decision_id)} />
        ))
      )}
    </section>
  );
}

function DecisionRow({ d, onSubmit }: { d: ApiDecision; onSubmit: () => void }) {
  const href = detailHref("disposal", d.decision_id);
  return (
    <div
      style={sx(
        "border:1px solid var(--line);border-radius:7px;background:var(--panel);padding:9px 12px;" +
          "display:flex;align-items:center;gap:10px;flex-wrap:wrap"
      )}
    >
      <Mono size={11.5}>{d.decision_id}</Mono>
      <StateBadge kind="disposal" state={d.state} size={9.5} />
      {d.disposal_mode && <Mono size={11}>{d.disposal_mode}</Mono>}
      <span style={sx("font:11.5px 'Pretendard';color:var(--dim)")}>
        처분일 {d.disposal_date ?? "미입력"}
      </span>
      {/* 판정이 없으면 판정 영역을 만들지 않는다 — "정상"으로 채우지 않는다 */}
      {d.verdict_at_signing && (
        <span style={sx("font:11px 'JetBrains Mono',monospace;color:var(--dim)")}>
          판정 {d.verdict_at_signing}
        </span>
      )}
      {d.requires_override && (
        <span
          style={sx(
            "font:700 9.5px 'JetBrains Mono',monospace;border:1px dashed var(--error-tx);" +
              "border-radius:3px;padding:2px 6px;color:var(--error-tx)"
          )}
        >
          우회 없이는 서명 불가
        </span>
      )}

      <div style={sx("flex:1")} />

      {isDraftState(d.state) && (
        <Button size="sm" onClick={onSubmit}>
          팀장 승인 요청
        </Button>
      )}
      {href && (
        <Link
          href={href}
          style={sx(
            "font:11.5px 'Pretendard';color:var(--blue-tx);text-decoration:none;white-space:nowrap"
          )}
        >
          승인 큐에서 보기 →
        </Link>
      )}
    </div>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return (
    <div
      style={sx(
        "border:1px dashed var(--line2);border-radius:7px;padding:11px 13px;" +
          "font:12px/1.7 'Pretendard';color:var(--dim)"
      )}
    >
      {children}
    </div>
  );
}

/**
 * 처분서 초안 **생성** 자리 (P39, 2026-09-03).
 *
 * 이 화면 docstring 이 *"초안은 에이전트가 `generate_disposal_document` 로 만든다"* 고
 * 적어둔 그 구멍을 메운다 — 채팅 없이도 화면에서 직접 만들 수 있게 한다(D111 이 발주서에
 * 연 경로의 마지막 확장). 사전판정(`DisposalPanel`) 바로 **아래**에 두는 이유는 순서가
 * 그대로 판단 흐름이기 때문이다: 무엇이 막혀 있는지 보고 → 그 상태로 초안을 만든다.
 */
function NewDraftSection({
  assetId,
  onCreated,
}: {
  assetId: string;
  onCreated: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [made, setMade] = useState<ApiDecision | null>(null);

  if (made) {
    return (
      <div style={sx("padding:14px 18px;border-top:1px solid var(--line)")}>
        <StatusBanner tone="info">
          처분서 초안 {made.decision_id} 을 만들었습니다 — 아래 목록에서 승인 큐에 올릴 수
          있습니다. 판정: {made.verdict_at_signing ?? "확인되지 않음"}
        </StatusBanner>
      </div>
    );
  }

  return (
    <div style={sx("padding:14px 18px;border-top:1px solid var(--line)")}>
      {!open ? (
        <Button onClick={() => setOpen(true)}>처분서 초안 만들기</Button>
      ) : (
        <DisposalDraftForm
          assetId={assetId}
          onDone={(d) => {
            setMade(d);
            onCreated(); // 아래 목록을 다시 그린다
          }}
        />
      )}
    </div>
  );
}
