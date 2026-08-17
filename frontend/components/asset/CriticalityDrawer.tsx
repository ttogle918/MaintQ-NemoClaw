"use client";

import { useEffect, useState } from "react";
import { Mono } from "@/components/ui/Mono";
import { ApiError, errorBody, extractDetail, getCriticality, type ApiCriticality } from "@/lib/api";
import { partClassView } from "@/lib/mappers";
import { sx } from "@/lib/sx";

/**
 * 부품 등급 드로어 (`classify_part_criticality`, `04 §10`, MQ-914).
 *
 * **전용 페이지가 아니다** — `RepairValuePanel` 의 부품 칩을 눌렀을 때 옆에서 펼쳐지는
 * 오버레이다. 닫아도 위쪽 판단(3지 판정)은 그대로 남는다 — 이 컴포넌트는 라우트를
 * 옮기지 않고 `open`/`onClose` 로만 제어된다.
 *
 * ⛔ 등급을 추측하지 않는다 — 응답을 그대로 보여줄 뿐이고, 실패하면 `reason` 을 그대로
 *   노출한다. "일시적 오류" 같은 문구로 바꿔 쓰지 않는다(`04 §13` 하위 실패 전파와 같은 태도).
 * ⛔ 등급 어휘(`part_class`)의 색·문구는 전부 `lib/mappers.partClassView` 가 정한다 — 이
 *   파일은 등급 원문 값을 직접 비교하거나 리터럴로 들고 있지 않는다(D87).
 */
export function CriticalityDrawer({
  open,
  partNo,
  onClose,
}: {
  open: boolean;
  partNo: string | null;
  onClose: () => void;
}) {
  const [data, setData] = useState<ApiCriticality | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open || !partNo) return;
    let alive = true;
    setLoading(true);
    setFailure(null);
    setData(null);
    getCriticality("technician", partNo)
      .then((res) => {
        if (!alive) return;
        if (res.status === "ok") {
          setData(res);
        } else {
          // 200 인데 status 가 ok 가 아닌 방어 — reason 을 그대로 보여준다
          setFailure(res.reason ?? "(사유 없음)");
        }
      })
      .catch((e: unknown) => {
        if (!alive) return;
        if (e instanceof ApiError) {
          const body = errorBody(e);
          const reason = typeof body?.reason === "string" ? body.reason : "";
          const message = extractDetail(e.body);
          setFailure(reason ? `${reason} — ${message}` : message);
        } else {
          setFailure("백엔드에 연결하지 못했습니다 — 조회가 실패한 것이지 등급이 없는 것이 아닙니다.");
        }
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [open, partNo]);

  if (!open || !partNo) return null;

  return (
    <>
      {/* 배경 — 클릭하면 닫힌다. 라우트는 바뀌지 않는다 */}
      <div
        onClick={onClose}
        style={sx(
          "position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:40;cursor:pointer"
        )}
      />
      <aside
        style={sx(
          "position:fixed;top:0;right:0;bottom:0;width:360px;max-width:92vw;z-index:41;" +
            "background:var(--surface);border-left:1px solid var(--line);box-shadow:-8px 0 30px rgba(0,0,0,.35);" +
            "display:flex;flex-direction:column;overflow-y:auto"
        )}
      >
        <div
          style={sx(
            "display:flex;align-items:center;gap:9px;padding:13px 15px;" +
              "border-bottom:1px solid var(--line);background:var(--head)"
          )}
        >
          <span style={sx("font:700 12.5px 'Pretendard';color:var(--ink)")}>부품 등급 조회</span>
          <Mono size={11.5}>{partNo}</Mono>
          <div style={sx("flex:1")} />
          <button
            onClick={onClose}
            aria-label="닫기"
            style={sx(
              "border:1px solid var(--line2);background:transparent;border-radius:6px;" +
                "width:26px;height:26px;cursor:pointer;color:var(--dim);font:14px monospace"
            )}
          >
            ✕
          </button>
        </div>

        <div style={sx("padding:14px 15px;display:flex;flex-direction:column;gap:12px")}>
          {loading && (
            <div style={sx("font:12px 'Pretendard';color:var(--dim)")}>불러오는 중…</div>
          )}

          {failure && !loading && (
            <div
              style={sx(
                "border:1.5px dashed var(--error-tx);border-radius:7px;padding:10px 12px;" +
                  "font:12px/1.7 'Pretendard';color:var(--error-tx)"
              )}
            >
              <b>조회 실패</b>
              <br />
              {failure}
            </div>
          )}

          {data && !loading && <CriticalityBody data={data} />}
        </div>
      </aside>
    </>
  );
}

function CriticalityBody({ data }: { data: ApiCriticality }) {
  const view = partClassView(data.part_class);
  const notConsidered = Array.isArray(data.not_considered) ? data.not_considered : [];
  // D97 — 없는 값을 채우지 않는다. 키 자체가 응답에 없을 수 있다(계약에 없는 필드) —
  // 있을 때만 렌더하고 없으면 아예 행을 만들지 않는다(지어내지 않는다).
  const raw = data as unknown as Record<string, unknown>;
  const hasMfrPartNo = Object.prototype.hasOwnProperty.call(raw, "mfr_part_no");
  const mfrPartNo = raw.mfr_part_no;

  return (
    <>
      <div
        style={sx(`${view.skin};border-radius:8px;padding:11px 13px;display:flex;flex-direction:column;gap:5px`)}
      >
        <span style={sx("font:700 14px 'Pretendard'")}>
          {view.known ? view.text : `⚠ ${view.text}`}
        </span>
        <span style={sx("font:11.5px/1.6 'Pretendard'")}>{view.note}</span>
      </div>

      {data.name && (
        <Field label="부품명">
          <span style={sx("font:12.5px 'Pretendard';color:var(--ink)")}>{data.name}</span>
        </Field>
      )}

      {/* null 이면 배지 자체를 만들지 않는다 — "미분류"로 채우지 않는다 (AssetHeader 와 같은 태도) */}
      {data.category && (
        <Field label="분류">
          <span style={sx("font:12px 'Pretendard';color:var(--ink2)")}>{data.category}</span>
        </Field>
      )}

      <Field label="단종 여부 (D20)">
        <span style={sx(`font:700 11px 'JetBrains Mono',monospace;color:${data.discontinued ? "var(--error-tx)" : "var(--ink2)"}`)}>
          {data.discontinued ? "단종" : "생산 중"}
        </span>
      </Field>

      {hasMfrPartNo && (
        <Field label="제조사 부품번호">
          {mfrPartNo === null ? (
            <span style={sx("font:12px 'Pretendard';color:var(--dim)")}>공개되지 않음</span>
          ) : (
            <Mono size={11.5}>{String(mfrPartNo)}</Mono>
          )}
        </Field>
      )}

      {data.note && (
        <div
          style={sx(
            "border:1px dashed var(--line2);border-radius:6px;padding:8px 10px;" +
              "font:11.5px/1.6 'Pretendard';color:var(--dim)"
          )}
        >
          {data.note}
        </div>
      )}

      {notConsidered.length > 0 && (
        <Field label="보지 않은 것 (not_considered)">
          <ul style={sx("margin:0;padding-left:16px;font:11px/1.7 'Pretendard';color:var(--dim)")}>
            {notConsidered.map((n) => (
              <li key={n}>{n}</li>
            ))}
          </ul>
        </Field>
      )}

      {data.disclaimer && (
        <p
          style={sx(
            "margin:0;padding-top:9px;border-top:1px dashed var(--line2);" +
              "font:11px/1.7 'Pretendard';color:var(--dim)"
          )}
        >
          {data.disclaimer}
        </p>
      )}
    </>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div style={sx("font:700 10.5px 'Pretendard';color:var(--dim2);margin-bottom:3px")}>{label}</div>
      {children}
    </div>
  );
}
