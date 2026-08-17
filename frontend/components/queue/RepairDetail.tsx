"use client";

import { useEffect, useState } from "react";
import { KindBadge, StateBadge } from "@/components/ui/Badge";
import { Mono } from "@/components/ui/Mono";
import {
  ApiError,
  errorBody,
  extractDetail,
  getRepair,
  rejectRepair,
  signRepair,
  type ApiRepair,
} from "@/lib/api";
import { expenditureVerdictView, partClassView, WORK_SCOPE_OPTIONS } from "@/lib/mappers";
import { isDraftState, isPendingState } from "@/lib/queueState";
import { sx } from "@/lib/sx";
import type { EvidenceEntry } from "@/lib/types";
import { RejectPanel } from "./DecisionBar";
import { EvidenceCard } from "./EvidenceCard";

/**
 * 수리 증빙 상세 (S19, MQ-1002) — `GET /api/repairs/{id}` 를 그대로 화면에 편다.
 *
 * `SignBar`(처분 전용, `ApiDecision`·`override` 개념에 강결합)를 재사용하지 않고 이 파일
 * 안에 전용 컨트롤을 둔다 — 수리 증빙엔 우회(override) 개념 자체가 없다(D81 급 차단 없음,
 * `backend/routers/repairs.py`). 반려 입력만 `DecisionBar` 가 export 하는 `RejectPanel`
 * (사유 게이트 한 곳, D38)을 재사용한다.
 *
 * ⛔ `state` 4어휘(`pending`|`signed`|`draft`|`rejected`)를 직접 비교하지 않는다 — 컨트롤
 *   노출은 `queueState.isPendingState`/`isDraftState` 술어로, 표시는 `StateBadge` 로 위임한다
 *   (D87, `SignBar`/`DecisionDetail` 과 같은 태도).
 */
export function RepairDetail({
  repairId,
  onUpdated,
}: {
  repairId: string;
  /** 서명·반려 성공 — 갱신된 레코드로 교체된다(상세가 `signed`/`rejected` 로 전환되고 컨트롤이 사라진다) */
  onUpdated?: (updated: ApiRepair) => void;
}) {
  const [repair, setRepair] = useState<ApiRepair | null>(null);
  const [loading, setLoading] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setFailure(null);
    setRepair(null);
    getRepair("manager", repairId)
      .then((res) => {
        if (alive) setRepair(res);
      })
      .catch((e: unknown) => {
        if (!alive) return;
        if (e instanceof ApiError) {
          setFailure(extractDetail(e.body));
        } else {
          setFailure(
            "백엔드에 연결하지 못했습니다 — 조회가 실패한 것이지 증빙이 없는 것이 아닙니다."
          );
        }
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [repairId]);

  if (loading) {
    return (
      <div style={sx("padding:18px 20px;font:12px 'Pretendard';color:var(--dim)")}>
        불러오는 중…
      </div>
    );
  }

  if (failure || !repair) {
    return (
      <div style={sx("padding:18px 20px")}>
        <div
          style={sx(
            "border:1.5px dashed var(--error-tx);border-radius:7px;padding:10px 12px;" +
              "font:12px/1.7 'Pretendard';color:var(--error-tx)"
          )}
        >
          <b>수리 증빙 조회 실패</b>
          <br />
          {failure ?? "응답이 없습니다."}
        </div>
      </div>
    );
  }

  return (
    <div style={sx("display:flex;flex-direction:column;padding:18px 20px")}>
      {/* ── 헤더 ─────────────────────────────────────────────────────────── */}
      <div style={sx("display:flex;align-items:center;gap:9px;margin-bottom:14px")}>
        <span style={sx("font:700 17px 'Pretendard';color:var(--ink)")}>
          <Mono size={15}>#{repair.repair_id}</Mono> {repair.equipment_id}
        </span>
        <KindBadge kind="repair" size={10} />
        <StateBadge kind="repair" state={repair.state} size={10} />
        <div style={sx("flex:1")} />
        <span style={sx("font:11px 'JetBrains Mono',monospace;color:var(--dim2)")}>
          요청 · {repair.requested_by_name || repair.performed_by_name || "-"}
          {repair.created_at ? ` · ${repair.created_at}` : ""}
        </span>
      </div>

      <EvidenceCard title="수리 증빙 요약" entries={repairSummary(repair)} />

      {/* 서명 전에는 `record_hash` 가 없다(D84) — 값 존재로 분기하지 문자열 상태 비교로
          분기하지 않는다. `hash_verified` 는 불리언 3상태(D62) — `undefined` 와 `false` 를
          구분한다. */}
      {repair.record_hash && (
        <div
          style={sx(
            "border:1px solid var(--line2);border-radius:7px;background:var(--evi);" +
              "padding:10px 12px;margin-bottom:14px;display:flex;flex-direction:column;gap:5px"
          )}
        >
          <div style={sx("font:700 10px 'JetBrains Mono',monospace;color:var(--dim2)")}>
            서명 해시
          </div>
          <Mono size={11}>{repair.record_hash.slice(0, 12)}</Mono>
          <HashVerified value={repair.hash_verified} />
        </div>
      )}

      <RepairControls
        repair={repair}
        onUpdated={(updated) => {
          // 서명/반려 직후 이 컴포넌트 자신의 repair 상태도 갱신한다 — repairId 는 바뀌지
          // 않으므로(46행 useEffect는 repairId 로만 재조회한다) onUpdated 로 부모만 알리면
          // 부모 목록은 새로고침되지만 이 상세 패널은 다시 마운트되기 전까지 낡은 상태(state·
          // 서명 해시·컨트롤 노출 여부)로 남는다.
          setRepair(updated);
          onUpdated?.(updated);
        }}
      />
    </div>
  );
}

/* ────────────────────────────────────────────────────────────────────────── */
/* 요약 행                                                                    */

function repairSummary(repair: ApiRepair): EvidenceEntry[] {
  const rows: EvidenceEntry[] = [];

  const parts = repair.parts ?? [];
  if (parts.length > 0) {
    rows.push({
      label: "PARTS",
      value: (
        <>
          {parts.map((p, i) => (
            <span key={`${p.part_no}-${i}`}>
              {i > 0 && " · "}
              <Mono size={11}>{p.part_no}</Mono>
              {p.serial ? ` (S/N ${p.serial})` : ""} ×{p.qty}
            </span>
          ))}
        </>
      ),
    });
  }

  rows.push({ label: "WORK", value: repair.work_type ?? "미상" });

  const scopeOption = WORK_SCOPE_OPTIONS.find((o) => o.value === repair.repair_scope);
  rows.push({
    label: "SCOPE",
    value: repair.repair_scope ? (scopeOption?.label ?? repair.repair_scope) : "미상",
  });

  const pc = partClassView(repair.part_class);
  rows.push({ label: "PART CLASS", value: pc.known ? pc.text : `⚠ ${pc.text}` });

  const ec = expenditureVerdictView(repair.expenditure_class);
  rows.push({
    label: "EXPENDITURE",
    value: (
      <>
        {ec.known ? ec.text : `⚠ ${ec.text}`}
        {repair.expenditure_reason ? ` — ${repair.expenditure_reason}` : ""}
      </>
    ),
  });

  rows.push({
    label: "COST",
    value: typeof repair.cost === "number" ? `${repair.cost.toLocaleString()} 원` : "미기록",
  });

  rows.push({
    label: "DOWNTIME",
    value:
      typeof repair.downtime_hours === "number" ? `${repair.downtime_hours} 시간` : "기록 없음",
  });

  rows.push({
    label: "EQUIPMENT",
    value: (
      <>
        <Mono size={11}>{repair.equipment_id}</Mono>
        {repair.model ? ` · ${repair.model}` : ""}
        {repair.error_code ? (
          <>
            {" "}
            · <Mono size={11}>{repair.error_code}</Mono>
          </>
        ) : null}
      </>
    ),
  });

  return rows;
}

/**
 * 서명 해시 대조 결과(D84·D62). `true` → 대조 일치, `false` → 불일치(경고 톤 고정 문구),
 * `undefined` → "대조 결과 없음"(미서명 레코드). `false` 를 "결과 없음"과 뭉개지 않는다.
 */
function HashVerified({ value }: { value: boolean | undefined }) {
  // --ok-* 계열은 쓰지 않는다 — ui_honesty_contract.py L2 가 컴포넌트의 --green|--ok 색 토큰을
  // 전부 금지한다(D87, InventoryDrawer.tsx 선례). 정보 톤(--blue-tx)으로 "일치"를 표시한다.
  if (value === true) {
    return (
      <span style={sx("font:12px 'Pretendard';color:var(--blue-tx)")}>대조 일치</span>
    );
  }
  if (value === false) {
    return (
      <span style={sx("font:700 12px 'Pretendard';color:var(--error-tx)")}>
        ⚠ 저장된 해시와 재계산 결과가 다릅니다 — 확인이 필요합니다.
      </span>
    );
  }
  return <span style={sx("font:12px 'Pretendard';color:var(--dim)")}>대조 결과 없음</span>;
}

/* ────────────────────────────────────────────────────────────────────────── */
/* 서명/반려 컨트롤                                                           */

interface SignFailure {
  status: number;
  detail: string;
  /** `errorBody(e).reason === "self_sign"` — 본인 수행 수리는 본인이 서명할 수 없다 (D4).
   *  `self_sign` 은 `STATE_WORDS` 밖의 어휘라 D87 L2 스캔 대상이 아니다. */
  selfSign: boolean;
}

function RepairControls({
  repair,
  onUpdated,
}: {
  repair: ApiRepair;
  onUpdated?: (updated: ApiRepair) => void;
}) {
  const [rejecting, setRejecting] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<SignFailure | null>(null);

  const live = Boolean(onUpdated);

  if (!isPendingState(repair.state)) {
    return <NotSignable state={repair.state} />;
  }

  function fail(e: unknown) {
    const body = errorBody(e);
    const reason = typeof body?.reason === "string" ? body.reason : null;
    setFailure({
      status: e instanceof ApiError ? e.status : 0,
      detail: e instanceof ApiError ? extractDetail(e.body) : String(e),
      selfSign: reason === "self_sign",
    });
    setBusy(false);
  }

  async function doSign() {
    setBusy(true);
    try {
      const updated = await signRepair(repair.repair_id);
      setFailure(null);
      setBusy(false);
      onUpdated?.(updated);
    } catch (e) {
      fail(e);
    }
  }

  async function doReject(reason: string) {
    setBusy(true);
    try {
      const updated = await rejectRepair(repair.repair_id, reason);
      setFailure(null);
      setBusy(false);
      setRejecting(false);
      onUpdated?.(updated);
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
      {failure && (
        <div
          style={sx(
            "border:1px solid var(--saf-bd);background:var(--saf-bg);border-radius:7px;" +
              "padding:11px 13px;display:flex;flex-direction:column;gap:5px"
          )}
        >
          <span style={sx("font:700 11px 'JetBrains Mono',monospace;color:var(--orange-tx)")}>
            HTTP {failure.status}
          </span>
          <span style={sx("font:12px/1.6 'Pretendard';color:var(--saf-tx)")}>
            {failure.selfSign
              ? "본인이 수행한 수리는 본인이 서명할 수 없습니다."
              : failure.detail}
          </span>
        </div>
      )}

      {!live && (
        <div style={sx("font:11px 'Pretendard';color:var(--dim2)")}>
          목업 데이터 — 서명·반려가 저장되지 않습니다
        </div>
      )}

      {live && rejecting && (
        <RejectPanel
          label="반려 사유 (필수)"
          placeholder="예: 수리 범위 불명확 / 부품 근거 확인 필요"
          hint="사유는 요청자에게 그대로 전달되고 수리 이력에 남습니다."
          confirmLabel="반려 확정"
          onCancel={() => setRejecting(false)}
          onConfirm={(reason) => void doReject(reason)}
        />
      )}

      {live && !rejecting && (
        <div style={sx("display:flex;gap:10px;align-items:center")}>
          <span style={sx("font:11px/1.5 'Pretendard';color:var(--dim2);flex:1")}>
            서명 시 수리 증빙이 확정되고 서명자·시각이 기록됩니다. 우회(override) 개념은
            수리 증빙에 없습니다.
          </span>
          <button
            onClick={() => setRejecting(true)}
            disabled={busy}
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
            disabled={busy}
            style={sx(
              "border-radius:7px;font-family:'Pretendard';font-weight:600;padding:11px 22px;" +
                "font-size:13px;white-space:nowrap;border:none;" +
                (busy
                  ? "background:var(--line2);color:var(--dim2);cursor:not-allowed"
                  : "background:var(--blue);color:#fff;cursor:pointer")
            )}
          >
            {busy ? "처리 중…" : "서명하고 확정"}
          </button>
        </div>
      )}
    </div>
  );
}

/**
 * 서명·반려 대기(`pending`)가 아닌 레코드 — 컨트롤 대신 왜 없는지 말한다(숨기지 않는다).
 * `draft` 는 제출 전이라는 것을 알려 주고, 그 밖(`signed`·`rejected`·모르는 값)은 종착역이거나
 * 이미 서명 해시가 위에 렌더돼 있다 — 여기서 재요청 버튼을 만들지 않는다(P15 백로그, 승격 금지).
 */
function NotSignable({ state }: { state: string }) {
  if (isDraftState(state)) {
    return (
      <div style={sx("font:12px/1.6 'Pretendard';color:var(--dim)")}>
        정비사가 아직 제출하지 않았습니다 — 팀장 승인 대기 목록에 올라오기 전입니다.
      </div>
    );
  }
  return (
    <div style={sx("font:12px/1.6 'Pretendard';color:var(--dim)")}>
      이 상태(<Mono size={11}>{state}</Mono>)에서는 서명·반려할 수 없습니다.
    </div>
  );
}
