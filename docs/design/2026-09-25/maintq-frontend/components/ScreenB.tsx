"use client";

import { sx } from "@/lib/sx";
import type { Theme } from "@/lib/theme";

export type QueueView = "queue" | "empty";

interface ScreenBProps {
  theme: Theme;
  /** Whether the approval queue has pending items or is empty. */
  view?: QueueView;
}

export default function ScreenB({ theme, view = "queue" }: ScreenBProps) {
  const isQueue = view === "queue";
  const isEmpty = view === "empty";
  const pendingCount = isQueue ? "(3)" : "(0)";

  return (
    <div
      className="app-root"
      data-theme={theme}
      style={sx(
        "background:var(--page);display:flex;flex-direction:column;align-items:center;gap:18px;transition:background .2s"
      )}
    >
      {/* 콘솔 */}
      <div style={sx("width:1020px;max-width:100%;background:var(--surface);border:1px solid var(--line);border-radius:8px;overflow:hidden;box-shadow:0 10px 40px rgba(0,0,0,.28)")}>
        <div style={sx("display:flex;align-items:center;gap:10px;padding:11px 16px;border-bottom:1px solid var(--line);background:var(--head)")}>
          <div style={sx("width:24px;height:24px;border-radius:5px;background:var(--blue);display:flex;align-items:center;justify-content:center;font:700 12px 'JetBrains Mono',monospace;color:#fff")}>M</div>
          <span style={sx("font:600 13px 'Pretendard';color:var(--ink)")}>MaintQ</span>
          <span style={sx("width:1px;height:16px;background:var(--line);margin:0 4px")} />
          <span style={sx("font:700 13px 'Pretendard';color:var(--ink)")}>승인 대기 <span style={sx("color:var(--orange-tx)")}>{pendingCount}</span></span>
          <div style={sx("flex:1")} />
          <span style={sx("font:12px 'Pretendard';color:var(--dim)")}>팀장 박OO</span>
          <div style={sx("width:26px;height:26px;border-radius:50%;background:var(--raise);border:1px solid var(--line)")} />
        </div>

        {isQueue && (
          <div style={sx("display:grid;grid-template-columns:280px 1fr;min-height:560px")}>
            {/* 큐 리스트 */}
            <div style={sx("border-right:1px solid var(--line);display:flex;flex-direction:column;background:var(--panel)")}>
              <div style={sx("padding:13px 14px 8px;font:700 11px 'JetBrains Mono',monospace;letter-spacing:.06em;color:var(--dim2)")}>승인 대기 · 3</div>
              <div style={sx("padding:0 12px;display:flex;flex-direction:column;gap:8px")}>
                {/* selected */}
                <div style={sx("border:2px solid var(--blue);border-radius:7px;padding:10px 11px;background:var(--sel);cursor:pointer")}>
                  <div style={sx("display:flex;gap:5px;margin-bottom:6px")}>
                    <span style={sx("display:inline-flex;align-items:center;gap:3px;font:700 9px 'JetBrains Mono',monospace;color:#fff;background:var(--orange);border-radius:3px;padding:2px 6px")}>▲ 긴급</span>
                    <span style={sx("display:inline-flex;align-items:center;gap:3px;font:700 9px 'JetBrains Mono',monospace;color:var(--blue-tx);border:1px solid var(--cite-bd);background:var(--cite-bg);border-radius:3px;padding:2px 6px")}>◔ pending</span>
                  </div>
                  <div style={sx("font:700 13px 'Pretendard';color:var(--ink)")}><span style={sx("font-family:'JetBrains Mono',monospace;font-size:12px")}>#PO-0117</span> 냉각팬 ×2</div>
                  <div style={sx("font:11px 'JetBrains Mono',monospace;color:var(--dim2);margin-top:3px")}>1번 라인 · 김OO · 10분 전</div>
                </div>
                <div style={sx("border:1px solid var(--line2);border-radius:7px;padding:10px 11px;background:var(--surface);cursor:pointer")}>
                  <div style={sx("display:flex;gap:5px;margin-bottom:6px")}>
                    <span style={sx("font:700 9px 'JetBrains Mono',monospace;color:var(--dim);border:1px solid var(--line2);border-radius:3px;padding:2px 6px")}>일반</span>
                    <span style={sx("display:inline-flex;align-items:center;gap:3px;font:700 9px 'JetBrains Mono',monospace;color:var(--blue-tx);border:1px solid var(--cite-bd);background:var(--cite-bg);border-radius:3px;padding:2px 6px")}>◔ pending</span>
                  </div>
                  <div style={sx("font:700 13px 'Pretendard';color:var(--ink)")}><span style={sx("font-family:'JetBrains Mono',monospace;font-size:12px")}>#PO-0116</span> 제어보드 <span style={sx("font-size:11px;color:var(--dim)")}>(대체품)</span></div>
                  <div style={sx("font:11px 'JetBrains Mono',monospace;color:var(--dim2);margin-top:3px")}>1번 라인 · 이OO · 2시간 전</div>
                </div>
                <div style={sx("border:1px solid var(--line2);border-radius:7px;padding:10px 11px;background:var(--surface);cursor:pointer")}>
                  <div style={sx("display:flex;gap:5px;margin-bottom:6px")}>
                    <span style={sx("font:700 9px 'JetBrains Mono',monospace;color:var(--dim);border:1px solid var(--line2);border-radius:3px;padding:2px 6px")}>일반</span>
                    <span style={sx("display:inline-flex;align-items:center;gap:3px;font:700 9px 'JetBrains Mono',monospace;color:var(--blue-tx);border:1px solid var(--cite-bd);background:var(--cite-bg);border-radius:3px;padding:2px 6px")}>◔ pending</span>
                  </div>
                  <div style={sx("font:700 13px 'Pretendard';color:var(--ink)")}><span style={sx("font-family:'JetBrains Mono',monospace;font-size:12px")}>#PO-0115</span> 퓨즈 ×10</div>
                  <div style={sx("font:11px 'JetBrains Mono',monospace;color:var(--dim2);margin-top:3px")}>2번 라인 · 김OO · 어제</div>
                </div>
              </div>
              <div style={sx("height:1px;background:var(--line);margin:14px 12px 0")} />
              <div style={sx("padding:11px 14px 8px;font:700 11px 'JetBrains Mono',monospace;letter-spacing:.06em;color:var(--dim2)")}>최근 처리</div>
              <div style={sx("padding:0 12px 14px;display:flex;flex-direction:column;gap:8px")}>
                <div style={sx("border:1px solid var(--line);border-radius:7px;padding:9px 11px;background:var(--surface);opacity:.72;cursor:pointer")}>
                  <span style={sx("display:inline-flex;align-items:center;gap:3px;font:700 9px 'JetBrains Mono',monospace;color:var(--ok-tx);border:1px solid var(--ok-bd);background:var(--ok-bg);border-radius:3px;padding:2px 6px;margin-bottom:5px")}>✓ approved</span>
                  <div style={sx("font:600 12.5px 'Pretendard';color:var(--ink2)")}><span style={sx("font-family:'JetBrains Mono',monospace;font-size:11px")}>#PO-0114</span> V벨트 ×1</div>
                </div>
                <div style={sx("border:1px solid var(--line);border-radius:7px;padding:9px 11px;background:var(--surface);opacity:.72;cursor:pointer")}>
                  <span style={sx("display:inline-flex;align-items:center;gap:3px;font:700 9px 'JetBrains Mono',monospace;color:var(--orange-tx);border:1px solid var(--saf-cite-bd);background:var(--saf-cite-bg);border-radius:3px;padding:2px 6px;margin-bottom:5px")}>✕ rejected</span>
                  <div style={sx("font:600 12.5px 'Pretendard';color:var(--ink2)")}><span style={sx("font-family:'JetBrains Mono',monospace;font-size:11px")}>#PO-0113</span> 인버터 ×1 <span style={sx("font-size:11px;color:var(--dim2)")}>· 사유: 예산</span></div>
                </div>
              </div>
            </div>

            {/* 상세 */}
            <div style={sx("display:flex;flex-direction:column;padding:18px 20px")}>
              <div style={sx("display:flex;align-items:center;gap:9px;margin-bottom:14px")}>
                <span style={sx("font:700 17px 'Pretendard';color:var(--ink)")}><span style={sx("font-family:'JetBrains Mono',monospace;font-size:15px")}>#PO-0117</span> 냉각팬 ×2</span>
                <span style={sx("display:inline-flex;align-items:center;gap:3px;font:700 10px 'JetBrains Mono',monospace;color:#fff;background:var(--orange);border-radius:4px;padding:3px 8px")}>▲ 긴급</span>
                <span style={sx("display:inline-flex;align-items:center;gap:3px;font:700 10px 'JetBrains Mono',monospace;color:var(--blue-tx);border:1px solid var(--cite-bd);background:var(--cite-bg);border-radius:4px;padding:3px 8px")}>◔ pending</span>
                <div style={sx("flex:1")} />
                <span style={sx("font:11px 'JetBrains Mono',monospace;color:var(--dim2)")}>요청 · 김OO · 10분 전</span>
              </div>

              {/* 근거 요약 카드 */}
              <div style={sx("border:1px solid var(--line2);border-radius:8px;background:var(--evi);padding:15px 16px;margin-bottom:14px")}>
                <div style={sx("font:700 10px 'JetBrains Mono',monospace;letter-spacing:.08em;color:var(--dim2);margin-bottom:12px")}>근거 요약 · 대화 전체를 읽지 않아도 판단 가능</div>
                <div style={sx("display:flex;flex-direction:column;gap:11px")}>
                  <div style={sx("display:flex;gap:12px;align-items:baseline")}><span style={sx("font:700 10px 'JetBrains Mono',monospace;color:var(--dim);width:82px;flex-shrink:0")}>ERROR</span><span style={sx("font:12.5px/1.5 'Pretendard';color:var(--ink)")}>iG5A · <span style={sx("font-family:'JetBrains Mono',monospace;font-size:11px")}>OHt</span> (과열) — 1번 라인 <span style={sx("font-family:'JetBrains Mono',monospace;font-size:11px")}>INV-L1-01</span></span></div>
                  <div style={sx("display:flex;gap:12px;align-items:baseline")}><span style={sx("font:700 10px 'JetBrains Mono',monospace;color:var(--dim);width:82px;flex-shrink:0")}>DIAGNOSIS</span><span style={sx("font:12.5px/1.5 'Pretendard';color:var(--ink)")}>냉각팬 고장 유력 <span style={sx("display:inline-flex;align-items:center;gap:4px;font:500 10px 'JetBrains Mono',monospace;color:var(--blue-tx);border:1px solid var(--cite-bd);background:var(--cite-bg);border-radius:4px;padding:1px 6px")}>▤ 매뉴얼 p.208</span></span></div>
                  <div style={sx("display:flex;gap:12px;align-items:baseline")}><span style={sx("font:700 10px 'JetBrains Mono',monospace;color:var(--dim);width:82px;flex-shrink:0")}>INVENTORY</span><span style={sx("font:12.5px/1.5 'Pretendard';color:var(--ink)")}>재고 1 / 안전재고 3 — <span style={sx("color:var(--orange-tx);font-weight:600")}>부족분 2</span> · 자재창고 A-12</span></div>
                  <div style={sx("display:flex;gap:12px;align-items:baseline")}><span style={sx("font:700 10px 'JetBrains Mono',monospace;color:var(--dim);width:82px;flex-shrink:0")}>TRACE</span><a href="#" style={sx("font:12.5px/1.5 'Pretendard';color:var(--blue-br);text-decoration:underline")}>에이전트 실행 로그 전체 보기 →</a></div>
                </div>
              </div>

              {/* 공급사 비교 */}
              <div style={sx("font:700 10px 'JetBrains Mono',monospace;letter-spacing:.08em;color:var(--dim2);margin-bottom:9px")}>공급사 비교 · 선택은 사람이</div>
              <div style={sx("display:grid;grid-template-columns:1fr 1fr;gap:11px;margin-bottom:16px")}>
                <div style={sx("border:2px solid var(--blue);border-radius:8px;background:var(--surface);padding:13px 14px;position:relative")}>
                  <span style={sx("position:absolute;top:-9px;left:12px;font:700 9px 'JetBrains Mono',monospace;color:#fff;background:var(--blue);border-radius:3px;padding:2px 7px")}>추천</span>
                  <div style={sx("font:700 14px 'Pretendard';color:var(--ink);margin-bottom:8px")}>A사</div>
                  <div style={sx("display:flex;justify-content:space-between;font:12px 'Pretendard';color:var(--ink2);margin-bottom:5px")}><span style={sx("color:var(--dim2)")}>리드타임</span><span style={sx("color:var(--ink);font-weight:600")}>3일</span></div>
                  <div style={sx("display:flex;justify-content:space-between;font:12px 'Pretendard';color:var(--ink2)")}><span style={sx("color:var(--dim2)")}>단가</span><span style={sx("font-family:'JetBrains Mono',monospace")}>₩38,000</span></div>
                  <div style={sx("margin-top:9px;padding-top:9px;border-top:1px solid var(--line);font:11px/1.4 'Pretendard';color:var(--blue-tx2)")}>긴급도 高 → 최단 납기 우선</div>
                </div>
                <div style={sx("border:1px solid var(--line2);border-radius:8px;background:var(--surface);padding:13px 14px")}>
                  <div style={sx("font:700 14px 'Pretendard';color:var(--ink);margin-bottom:8px")}>B사</div>
                  <div style={sx("display:flex;justify-content:space-between;font:12px 'Pretendard';color:var(--ink2);margin-bottom:5px")}><span style={sx("color:var(--dim2)")}>리드타임</span><span style={sx("color:var(--ink)")}>14일</span></div>
                  <div style={sx("display:flex;justify-content:space-between;font:12px 'Pretendard';color:var(--ink2)")}><span style={sx("color:var(--dim2)")}>단가</span><span style={sx("font-family:'JetBrains Mono',monospace")}>₩29,000</span></div>
                  <div style={sx("margin-top:9px;padding-top:9px;border-top:1px solid var(--line);font:11px/1.4 'Pretendard';color:var(--dim2)")}>단가 최저 · MOQ 10</div>
                </div>
              </div>

              <div style={sx("display:flex;gap:10px;align-items:center;margin-top:auto;padding-top:14px;border-top:1px solid var(--line)")}>
                <span style={sx("font:11px/1.4 'Pretendard';color:var(--dim2);flex:1")}>승인 시 A사 발주서가 <b style={sx("color:var(--ink2)")}>확정</b>됩니다. 반려 시 요청자에게 사유가 전달됩니다.</span>
                <button style={sx("border:1.5px solid var(--orange);background:transparent;color:var(--orange-tx);border-radius:7px;padding:11px 18px;font:700 13px 'Pretendard';cursor:pointer")}>반려 (사유 입력)</button>
                <button style={sx("border:none;background:var(--blue);color:#fff;border-radius:7px;padding:11px 22px;font:700 13px 'Pretendard';cursor:pointer")}>승인 — 발주서 확정</button>
              </div>
            </div>
          </div>
        )}

        {/* 빈 상태 */}
        {isEmpty && (
          <div style={sx("min-height:560px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:16px;padding:40px")}>
            <div style={sx("width:66px;height:66px;border-radius:14px;border:2px solid var(--ok-bd);background:var(--ok-bg);display:flex;align-items:center;justify-content:center;font-size:28px;color:var(--ok-tx)")}>✓</div>
            <div style={sx("font:700 17px 'Pretendard';color:var(--ink)")}>승인 대기 없음</div>
            <div style={sx("font:13px/1.6 'Pretendard';color:var(--dim);text-align:center;max-width:340px")}>모든 발주 요청이 처리되었습니다. 새 발주 요청이 오면 여기에 표시됩니다.</div>
            <div style={sx("display:flex;gap:8px;margin-top:4px")}>
              <span style={sx("font:11px 'JetBrains Mono',monospace;color:var(--dim2);border:1px solid var(--line2);border-radius:14px;padding:5px 12px")}>오늘 승인 4 · 반려 1</span>
            </div>
          </div>
        )}
      </div>

      {/* 상태 뱃지 범례 */}
      <div style={sx("width:1020px;max-width:100%;display:flex;align-items:center;gap:18px;flex-wrap:wrap;font:11px 'Pretendard';color:var(--dim2)")}>
        <span style={sx("font-weight:600;color:var(--dim)")}>승인 워크플로우 상태</span>
        <span style={sx("display:inline-flex;align-items:center;gap:5px")}><span style={sx("font:700 9px 'JetBrains Mono',monospace;color:var(--dim);border:1px solid var(--line2);border-radius:3px;padding:2px 6px")}>draft</span>정비사 작성 중</span>
        <span style={sx("display:inline-flex;align-items:center;gap:5px")}><span style={sx("font:700 9px 'JetBrains Mono',monospace;color:var(--blue-tx);border:1px solid var(--cite-bd);background:var(--cite-bg);border-radius:3px;padding:2px 6px")}>◔ pending</span>승인 대기</span>
        <span style={sx("display:inline-flex;align-items:center;gap:5px")}><span style={sx("font:700 9px 'JetBrains Mono',monospace;color:var(--ok-tx);border:1px solid var(--ok-bd);background:var(--ok-bg);border-radius:3px;padding:2px 6px")}>✓ approved</span>발주 확정</span>
        <span style={sx("display:inline-flex;align-items:center;gap:5px")}><span style={sx("font:700 9px 'JetBrains Mono',monospace;color:var(--orange-tx);border:1px solid var(--saf-cite-bd);background:var(--saf-cite-bg);border-radius:3px;padding:2px 6px")}>✕ rejected</span>반려</span>
      </div>
    </div>
  );
}
