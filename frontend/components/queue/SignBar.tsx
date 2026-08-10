"use client";

import { useState } from "react";
import {
  ApiError,
  errorBody,
  extractDetail,
  rejectDecision,
  signDecision,
  type ApiDecision,
} from "@/lib/api";
import { signability, signErrorView, type SignErrorLabel } from "@/lib/decisionView";
import { Mono } from "@/components/ui/Mono";
import { sx } from "@/lib/sx";
import { RejectPanel } from "./DecisionBar";

/**
 * 처분 서명 바 — 팀장 전용 (`POST /api/decisions/{id}/sign`).
 *
 * 발주의 `DecisionBar`(승인/반려)와 **다른 컴포넌트**인 이유: 서명은 승인이 아니다.
 * 책임 귀속(누가·언제·무엇을 뚫고)이 함께 남아야 하고, 차단 판정에는 우회 게이트가 붙는다 (D63).
 *
 * ★ 이 컴포넌트가 지키는 것
 *   ① **사유 없이 제출 자체가 불가능하다** — `requiresOverride` 면 체크박스 + 사유가
 *      둘 다 채워지기 전까지 버튼이 `disabled` 다. ⛔ 자동 체크·기본 사유 문구 금지.
 *      (백엔드도 422 로 막지만, 거기까지 가기 전에 UI 에서 받는다.)
 *   ② **`evidence_changed` 를 무시하고 재시도하는 경로를 만들지 않는다** — 근거가 바뀌면
 *      서명 컨트롤 자체가 사라지고 재조회만 남는다. 사람이 본 것과 다른 근거에 서명하는
 *      것이 이 화면에서 가장 비싼 실패다 (D84 가 서비스에서 막는 것과 같은 이유).
 *   ③ **모르는 상태에는 쓰기 경로를 열지 않는다** — 판단은 `lib/decisionView.signability()`
 *      의 total 맵이 하고, 여기에는 `state === "pending"` 같은 비교가 없다 (D87).
 *
 * 실패 표시는 상태코드 + `reason` 을 **구분해서** 보여 준다 (D38) —
 * 403(권한)·409(전이·근거·우회)·422(사유 공백)·503(카탈로그)은 사람이 할 일이 전부 다르다.
 */
export function SignBar({
  decisionId,
  state,
  requiresOverride,
  onSigned,
  onRejected,
  onReload,
}: {
  decisionId: string;
  /** 원 어휘 그대로 — 해석은 `signability()` 한 곳이 한다 */
  state: string;
  /**
   * 서명 시점 판정이 차단 어휘인가 (`requires_override`).
   * draft 시점 값이므로 **서명 시 재산출 결과와 다를 수 있다** — 그때는 409
   * `override_required` 가 오고, 아래에서 게이트를 연다.
   */
  requiresOverride: boolean;
  /** 미지정이면 읽기 전용 — 목업/백엔드 미연결에서 버튼이 아무것도 저장하지 않게 한다 */
  onSigned?: (updated: ApiDecision) => void;
  onRejected?: (updated: ApiDecision) => void;
  /** 409 뒤 재조회 */
  onReload?: () => void;
}) {
  const [override, setOverride] = useState(false);
  const [reason, setReason] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [rejecting, setRejecting] = useState(false);
  /** 서버가 "우회가 필요하다"고 답한 경우 — draft 시점 판정과 다를 때 여기서 게이트를 연다 */
  const [serverWantsOverride, setServerWantsOverride] = useState(false);
  const [failure, setFailure] = useState<Failure | null>(null);
  /**
   * **근거 불일치는 재조회로 풀리지 않는다.** `evidence_changed` 는 *저장된* `bundle_hash` 와
   * *재산출* 해시가 다르다는 뜻인데, 재조회는 둘 중 어느 쪽도 바꾸지 않는다 — 다시 누르면
   * 영원히 같은 409 다. 그래서 이 사실은 **재조회 뒤에도 지워지지 않고**, 서명 컨트롤도
   * 돌아오지 않는다. 배너만 걷히고 버튼이 살아나면 화면이 "다시 해보라"고 말하는 셈이고,
   * 그건 명세가 금지한 *"무시하고 재시도하는 경로"* 와 같다.
   */
  const [evidenceStale, setEvidenceStale] = useState(false);

  const gate = signability(state);
  const live = Boolean(onSigned);
  const needOverride = requiresOverride || serverWantsOverride;
  /** 재조회·재검토가 필요한 실패는 컨트롤을 닫는다 — 다시 누를 수 있으면 그게 우회 경로다 */
  const closed =
    evidenceStale ||
    (failure !== null &&
      (failure.label.recovery === "reload" || failure.label.recovery === "none"));
  const reasonFilled = reason.trim().length > 0;
  const canSign = gate.signable && live && !busy && !closed && (!needOverride || (override && reasonFilled));

  function fail(e: unknown) {
    const body = errorBody(e);
    const code = typeof body?.reason === "string" ? body.reason : null;
    const label = signErrorView(code);
    // 서버가 우회를 요구하면 게이트를 연다. **자동으로 체크하거나 사유를 채우지 않는다** —
    // 여는 것은 입력란이지 결정이 아니다.
    if (label.recovery === "override") setServerWantsOverride(true);
    // 근거 불일치는 **끈적하게** 남긴다 (위 `evidenceStale` 주석 참조).
    if (code === "evidence_changed") setEvidenceStale(true);
    setFailure({
      status: e instanceof ApiError ? e.status : 0,
      detail: e instanceof ApiError ? extractDetail(e.body) : String(e),
      code,
      label,
      body,
    });
    setBusy(false);
  }

  async function doSign() {
    if (!canSign) return;
    setBusy(true);
    try {
      const updated = await signDecision(decisionId, {
        // 우회가 필요 없는 결정에 `override:true` 를 보내지 않는다 —
        // 백엔드는 override 가 true 면 사유 공백을 422 로 막는다(불필요한 실패를 만들지 않는다).
        override: needOverride ? override : false,
        override_reason: needOverride && override ? reason.trim() : null,
        note: note.trim() || null,
      });
      setFailure(null);
      setBusy(false);
      onSigned?.(updated);
    } catch (e) {
      fail(e);
    }
  }

  async function doReject(why: string) {
    setBusy(true);
    try {
      const updated = await rejectDecision(decisionId, why);
      setFailure(null);
      setBusy(false);
      setRejecting(false);
      onRejected?.(updated);
    } catch (e) {
      fail(e);
    }
  }

  return (
    <div
      style={sx(
        "display:flex;flex-direction:column;gap:10px;margin-top:auto;padding-top:14px;" +
          "border-top:1px solid var(--line)"
      )}
    >
      {/* 재조회로 배너가 걷혀도 **사실은 남는다** — 이 결정은 다시 만들어야 한다 */}
      {evidenceStale && !failure && (
        <div
          style={sx(
            "border:1px solid var(--error-tx);border-radius:7px;padding:10px 12px;" +
              "font:12px/1.7 'Pretendard';color:var(--error-tx);background:var(--surface)"
          )}
        >
          ⚠ <b>근거가 변경된 결정입니다.</b> 재조회해도 저장된 근거 해시와 재산출 결과가 계속
          어긋납니다 — 다시 눌러도 같은 응답이 옵니다. 이 결정에는 서명할 수 없고,{" "}
          <b>처분서 초안을 다시 만들어야</b> 합니다.
        </div>
      )}

      {failure && (
        <FailureBox
          failure={failure}
          onReload={
            onReload
              ? () => {
                  setFailure(null);
                  onReload();
                }
              : undefined
          }
        />
      )}

      {/* 서명할 수 없는 상태 — 버튼을 만들지 않고 **왜 없는지** 말한다 (숨기지 않는다) */}
      {!gate.signable && (
        <div style={sx("font:12px/1.6 'Pretendard';color:var(--dim)")}>
          {gate.known ? gate.note : `⚠ ${gate.note}`}
          {!gate.known && (
            <>
              {" "}
              <Mono size={11}>{state}</Mono>
            </>
          )}
        </div>
      )}

      {gate.signable && !live && (
        <div style={sx("font:11px 'Pretendard';color:var(--dim2)")}>
          목업 데이터 — 서명·반려가 저장되지 않습니다
        </div>
      )}

      {gate.signable && live && rejecting && (
        <RejectPanel
          label="반려 사유 (필수)"
          placeholder="예: 매각 조건 재협의 필요 / 담보 해소 확인 후 재상신"
          hint="사유는 요청자에게 그대로 전달되고 처분 이력에 남습니다."
          confirmLabel="반려 확정"
          onCancel={() => setRejecting(false)}
          onConfirm={(why) => void doReject(why)}
        />
      )}

      {/*
        ★ 서명이 닫힌 상태에서도 **반려는 열어 둔다** (reviewer W3).
          `closed` 는 근거 불일치·카탈로그 문제처럼 *서명*이 불가능한 상태를 뜻하는데,
          반려는 근거 재산출과 무관하고 사유만 필요하다(`backend/routers/decisions.py` 의
          `reject` 는 `rebuild_bundle` 을 부르지 않는다). 둘 다 막으면 결정이 `pending` 에
          **영구 고착**되고, 사람은 시스템 밖에서 처분한 뒤 기록만 남기지 않게 된다 —
          D63 이 우회를 "막지 않고 기록한다"로 설계한 것과 정확히 반대 방향이다.
      */}
      {gate.signable && live && !rejecting && closed && (
        <div style={sx("display:flex;gap:10px;align-items:center;flex-wrap:wrap")}>
          <span style={sx("font:12px/1.6 'Pretendard';color:var(--dim);flex:1;min-width:200px")}>
            이 결정에는 서명할 수 없습니다. 종결하려면 <b>반려</b>하십시오.
          </span>
          <button
            onClick={() => setRejecting(true)}
            style={sx(
              "border-radius:7px;font-family:'Pretendard';font-weight:600;padding:11px 22px;" +
                "font-size:13px;white-space:nowrap;cursor:pointer;" +
                "border:1.5px solid var(--orange);background:transparent;color:var(--orange-tx)"
            )}
          >
            반려 (사유 입력)
          </button>
        </div>
      )}

      {gate.signable && live && !rejecting && !closed && (
        <>
          {needOverride && (
            <div
              style={sx(
                "display:flex;flex-direction:column;gap:8px;border:1px solid var(--saf-cite-bd);" +
                  "background:var(--saf-cite-bg);border-radius:7px;padding:11px 13px"
              )}
            >
              <span style={sx("font:700 11px 'JetBrains Mono',monospace;color:var(--orange-tx)")}>
                차단 판정 — 우회 서명 게이트
              </span>
              <label
                style={sx(
                  "display:flex;gap:8px;align-items:flex-start;cursor:pointer;" +
                    "font:12.5px/1.5 'Pretendard';color:var(--ink2)"
                )}
              >
                {/* ⛔ defaultChecked 를 두지 않는다 — 우회는 사람이 켠 것만 우회다 */}
                <input
                  type="checkbox"
                  checked={override}
                  onChange={(e) => setOverride(e.target.checked)}
                  style={sx("margin-top:3px;flex-shrink:0")}
                />
                <span>
                  시스템 판정을 우회해 서명합니다 (<Mono size={11}>override</Mono>)
                </span>
              </label>

              {override && (
                <div
                  style={sx(
                    "border:1px solid var(--saf-bd);background:var(--saf-bg);border-radius:6px;" +
                      "padding:9px 11px;font:12px/1.6 'Pretendard';color:var(--saf-strong)"
                  )}
                >
                  ⚠ 판정을 뚫고 확정합니다. 사유와 서명자가 기록됩니다.
                </div>
              )}

              <label style={sx("font:600 11px 'JetBrains Mono',monospace;color:var(--orange-tx)")}>
                우회 사유 (필수)
              </label>
              {/* placeholder 는 **무엇을 쓸지에 대한 지시**다 — 기본 사유 문구가 아니다 */}
              <textarea
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="무엇을 확인했고 왜 판정과 다르게 판단하는지 적으십시오"
                style={sx(
                  "width:100%;min-height:62px;resize:vertical;border:1px solid var(--line2);" +
                    "border-radius:7px;background:var(--field);color:var(--ink);padding:9px 11px;" +
                    "font:12.5px/1.5 'Pretendard'"
                )}
              />
            </div>
          )}

          <label style={sx("font:600 10px 'JetBrains Mono',monospace;color:var(--dim2)")}>
            서명 코멘트 (선택)
          </label>
          <textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="결재 이력에 함께 남길 메모"
            style={sx(
              "width:100%;min-height:38px;resize:vertical;border:1px solid var(--line2);" +
                "border-radius:7px;background:var(--field);color:var(--ink);padding:8px 11px;" +
                "font:12.5px/1.5 'Pretendard'"
            )}
          />

          <div style={sx("display:flex;gap:10px;align-items:center")}>
            <span style={sx("font:11px/1.5 'Pretendard';color:var(--dim2);flex:1")}>
              {needOverride
                ? override
                  ? reasonFilled
                    ? "우회 사유가 입력됐습니다 — 서명하면 사유와 서명자가 기록됩니다."
                    : "우회 사유를 입력해야 서명할 수 있습니다."
                  : "차단 판정입니다 — 우회 체크와 사유 없이는 서명할 수 없습니다."
                : "서명 시 처분 결정이 확정되고 서명자·시각이 기록됩니다."}
            </span>
            <button
              onClick={() => setRejecting(true)}
              style={sx(
                "border-radius:7px;font-family:'Pretendard';font-weight:600;padding:11px 22px;" +
                  "font-size:13px;white-space:nowrap;cursor:pointer;" +
                  "border:1.5px solid var(--orange);background:transparent;color:var(--orange-tx)"
              )}
            >
              반려 (사유 입력)
            </button>
            <button
              onClick={() => void doSign()}
              disabled={!canSign}
              title={
                canSign
                  ? undefined
                  : needOverride
                    ? "우회 체크와 사유를 모두 입력해야 서명할 수 있습니다"
                    : "지금은 서명할 수 없습니다"
              }
              style={sx(
                "border-radius:7px;font-family:'Pretendard';font-weight:600;padding:11px 22px;" +
                  "font-size:13px;white-space:nowrap;border:none;" +
                  (canSign
                    ? "background:var(--blue);color:#fff;cursor:pointer"
                    : "background:var(--line2);color:var(--dim2);cursor:not-allowed")
              )}
            >
              {busy ? "처리 중…" : needOverride ? "우회 서명하고 확정" : "서명하고 확정"}
            </button>
          </div>
        </>
      )}
    </div>
  );
}

interface Failure {
  status: number;
  /** 백엔드가 준 사람용 문장 (`extractDetail` — D38 재사용) */
  detail: string;
  /** 409/503 본문의 `reason`. 없으면 null (403·422 등) */
  code: string | null;
  label: SignErrorLabel;
  body: Record<string, unknown> | null;
}

/** 409 본문이 함께 싣는 재료 — 지어내지 않고 온 것만 보여 준다. */
const EXTRA_LISTS: { key: string; label: string }[] = [
  { key: "resolve_options", label: "해소 경로" },
  { key: "missing_law_refs", label: "원문 미수집 조문" },
  { key: "missing_rules", label: "카탈로그에 없는 룰" },
];

function FailureBox({ failure, onReload }: { failure: Failure; onReload?: () => void }) {
  const strings = (v: unknown): string[] =>
    Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : [];

  return (
    <div
      style={sx(
        "border:1px solid var(--saf-bd);background:var(--saf-bg);border-radius:7px;padding:11px 13px;" +
          "display:flex;flex-direction:column;gap:7px"
      )}
    >
      <div style={sx("font:700 11px 'JetBrains Mono',monospace;color:var(--orange-tx)")}>
        HTTP {failure.status}
        {failure.code && ` · ${failure.code}`}
        {failure.code && !failure.label.known && " (이 화면이 모르는 실패 어휘)"}
      </div>
      {failure.label.title && (
        <div style={sx("font:600 13px/1.6 'Pretendard';color:var(--saf-strong)")}>
          {failure.label.title}
        </div>
      )}
      {/* 백엔드 문장을 요약하지 않고 그대로 — 403/409/422 를 구분해 보여 주는 게 D38 의 요점 */}
      <div style={sx("font:12px/1.6 'Pretendard';color:var(--saf-tx)")}>{failure.detail}</div>

      {EXTRA_LISTS.map(({ key, label }) => {
        const list = strings(failure.body?.[key]);
        if (!list.length) return null;
        return (
          <div key={key} style={sx("font:12px/1.7 'Pretendard';color:var(--saf-tx)")}>
            <b>{label}</b>
            <ul style={sx("margin:3px 0 0;padding-left:18px")}>
              {list.map((v) => (
                <li key={v}>{v}</li>
              ))}
            </ul>
          </div>
        );
      })}

      {typeof failure.body?.recomputed_hash === "string" && (
        <div style={sx("font:11px/1.6 'JetBrains Mono',monospace;color:var(--dim)")}>
          저장 {String(failure.body?.bundle_hash ?? "-")}
          <br />
          재산출 {failure.body.recomputed_hash}
        </div>
      )}

      {/* ⛔ "무시하고 다시 시도" 버튼은 없다. 재조회는 다시 읽는 것이지 다시 미는 게 아니다 */}
      {failure.label.recovery === "reload" && onReload && (
        <div>
          <button
            onClick={onReload}
            style={sx(
              "border-radius:6px;font-family:'Pretendard';font-weight:600;padding:8px 14px;" +
                "font-size:12px;cursor:pointer;border:1px solid var(--line2);" +
                "background:transparent;color:var(--ink2)"
            )}
          >
            재조회 — 현재 근거로 다시 검토
          </button>
        </div>
      )}
      {failure.label.recovery === "none" && (
        <div style={sx("font:11px/1.6 'Pretendard';color:var(--dim)")}>
          재시도로 풀리지 않습니다 — 이 결정은 사람이 다시 검토해야 합니다.
        </div>
      )}
    </div>
  );
}
