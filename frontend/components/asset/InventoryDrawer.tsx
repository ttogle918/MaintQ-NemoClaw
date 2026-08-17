"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Mono } from "@/components/ui/Mono";
import {
  ApiError,
  errorBody,
  extractDetail,
  getInventory,
  type ApiInventory,
} from "@/lib/api";
import { sx } from "@/lib/sx";

/**
 * 재고 조회 드로어 (`search_inventory`, `04 §4`, Sprint 10 브레인스토밍 A).
 *
 * `CriticalityDrawer` 와 완전히 같은 오버레이 패턴 — `RepairValuePanel` 의 "재고 보기"
 * 칩을 눌렀을 때 옆에서 펼쳐진다. 라우트를 옮기지 않고 `open`/`onClose` 로만 제어된다.
 *
 * ⛔ 발주는 이 컴포넌트가 직접 만들지 않는다 — "발주하러 가기" 는 기존 채팅 prefill
 *   경로(`/technician?prefill=...`)로 이동만 한다. `create_po_draft` 호출은 여전히
 *   에이전트가 채팅에서 한다(P39 완성 전까지의 의도적 설계 — docs/07_BACKLOG.md P39).
 */
export function InventoryDrawer({
  open,
  partNo,
  equipmentId,
  onClose,
}: {
  open: boolean;
  partNo: string | null;
  equipmentId: string | null;
  onClose: () => void;
}) {
  const [data, setData] = useState<ApiInventory | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open || !partNo) return;
    let alive = true;
    setLoading(true);
    setFailure(null);
    setData(null);
    getInventory("technician", { part_no: partNo })
      .then((res) => {
        if (!alive) return;
        setData(res);
      })
      .catch((e: unknown) => {
        if (!alive) return;
        if (e instanceof ApiError) {
          const body = errorBody(e);
          const reason = typeof body?.reason === "string" ? body.reason : "";
          const message = extractDetail(e.body);
          setFailure(reason ? `${reason} — ${message}` : message);
        } else {
          setFailure("백엔드에 연결하지 못했습니다 — 조회가 실패한 것이지 재고가 없는 것이 아닙니다.");
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

  const item = data?.status === "ok" ? data.items?.[0] : undefined;
  const notFound = data?.status === "not_found";
  // ok 인데 items 가 비어 있는 방어적 케이스 — "재고 없음"으로 지어내지 않고 조회
  // 계약이 어긋났다는 사실 그대로 알린다 (D9 의 정신을 렌더링 층에서도 지킨다)
  const malformed = data?.status === "ok" && !item;

  const prefillText = `${equipmentId ?? "해당 설비"}의 ${partNo} 재고 부족, 발주해줘`;
  const prefillHref =
    `/technician?prefill=${encodeURIComponent(prefillText)}` +
    (equipmentId ? `&equipment=${encodeURIComponent(equipmentId)}` : "");

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
          <span style={sx("font:700 12.5px 'Pretendard';color:var(--ink)")}>재고 조회</span>
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

          {notFound && !loading && (
            <div
              style={sx(
                "border:1.5px dashed var(--line2);border-radius:7px;padding:10px 12px;" +
                  "font:12px/1.7 'Pretendard';color:var(--dim)"
              )}
            >
              등록된 재고 정보가 없습니다.
            </div>
          )}

          {malformed && !loading && (
            <div
              style={sx(
                "border:1.5px dashed var(--error-tx);border-radius:7px;padding:10px 12px;" +
                  "font:12px/1.7 'Pretendard';color:var(--error-tx)"
              )}
            >
              <b>조회 실패</b>
              <br />
              응답 형식이 계약과 다릅니다 — 재고 항목을 읽을 수 없습니다.
            </div>
          )}

          {item && !loading && (
            <>
              <div
                style={sx(
                  `${
                    item.qty > 0
                      ? "border:1px solid var(--ok-bd);background:var(--ok-bg);color:var(--ok-tx)"
                      : "border:1.5px dashed var(--error-tx);background:transparent;color:var(--error-tx)"
                  };` + "border-radius:8px;padding:11px 13px;display:flex;flex-direction:column;gap:5px"
                )}
              >
                <span style={sx("font:700 14px 'Pretendard'")}>
                  {item.qty > 0 ? `재고 있음 · ${item.qty}개` : "재고 없음"}
                </span>
                <span style={sx("font:11.5px/1.6 'Pretendard'")}>
                  안전재고 {item.safety_stock}개 · 보관위치{" "}
                  {/* location 은 DB 상 nullable (`05_DB_SCHEMA.md §6`) — null 을 그대로
                      찍지 않고 "미기재"로 정직하게 알린다 (D62) */}
                  {item.location || "미기재"}
                  {item.discontinued ? " · 단종" : ""}
                </span>
              </div>

              {item.qty <= item.safety_stock && (
                <Link
                  href={prefillHref}
                  style={sx(
                    "display:inline-flex;align-items:center;justify-content:center;gap:6px;" +
                      "border:1px solid var(--cite-bd);background:var(--cite-bg);border-radius:8px;" +
                      "padding:9px 12px;text-decoration:none;font:700 12.5px 'Pretendard';color:var(--blue-tx)"
                  )}
                >
                  발주하러 가기 →
                </Link>
              )}
            </>
          )}
        </div>
      </aside>
    </>
  );
}
