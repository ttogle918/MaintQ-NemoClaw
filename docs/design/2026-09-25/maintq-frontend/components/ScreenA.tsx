"use client";

import { useState } from "react";
import { sx } from "@/lib/sx";
import type { Theme } from "@/lib/theme";

export type Scenario = "s1" | "s3";

interface ScreenAProps {
  theme: Theme;
  /** Fired when the technician requests team-lead approval for a PO draft. */
  onRequestApproval?: () => void;
  /** Which orchestration scenario to render (S1 pipeline / S3 repeated fault). */
  scenario?: Scenario;
}

export default function ScreenA({
  theme,
  onRequestApproval,
  scenario = "s1",
}: ScreenAProps) {
  const [listening, setListening] = useState(false);
  const isS1 = scenario === "s1";
  const isS3 = scenario === "s3";

  return (
    <div
      className="app-root"
      data-theme={theme}
      style={sx(
        "background:var(--page);display:flex;flex-direction:column;align-items:center;gap:18px;transition:background .2s"
      )}
    >
      {/* 콘솔 */}
      <div
        style={sx(
          "width:1020px;max-width:100%;background:var(--surface);border:1px solid var(--line);border-radius:8px;overflow:hidden;box-shadow:0 10px 40px rgba(0,0,0,.28)"
        )}
      >
        {/* header */}
        <div style={sx("display:flex;align-items:center;gap:10px;padding:11px 16px;border-bottom:1px solid var(--line);background:var(--head)")}>
          <div style={sx("width:24px;height:24px;border-radius:5px;background:var(--blue);display:flex;align-items:center;justify-content:center;font:700 12px 'JetBrains Mono',monospace;color:#fff")}>M</div>
          <span style={sx("font:600 13px 'Pretendard';color:var(--ink)")}>MaintQ</span>
          <span style={sx("width:1px;height:16px;background:var(--line);margin:0 4px")} />
          <span style={sx("border:1px solid var(--line2);border-radius:14px;padding:4px 11px;font:12px 'Pretendard';color:var(--ink2);background:var(--raise)")}>라인 · 1번 조립 <span style={sx("color:var(--dim2)")}>▾</span></span>
          <span style={sx("border:1px solid var(--line2);border-radius:14px;padding:4px 11px;font:12px 'Pretendard';color:var(--ink2);background:var(--raise)")}>장비 · <span style={sx("font-family:'JetBrains Mono',monospace;font-size:11px")}>LS iG5A</span> <span style={sx("color:var(--dim2)")}>▾</span></span>
          <div style={sx("flex:1")} />
          <span style={sx("font:12px 'Pretendard';color:var(--dim)")}>정비사 김OO</span>
          <div style={sx("width:26px;height:26px;border-radius:50%;background:var(--raise);border:1px solid var(--line)")} />
        </div>

        <div style={sx("display:grid;grid-template-columns:1.25fr 1fr;min-height:580px")}>
          {/* chat */}
          <div style={sx("display:flex;flex-direction:column;border-right:1px solid var(--line)")}>
            <div style={sx("flex:1;padding:16px;display:flex;flex-direction:column;gap:12px")}>
              {isS1 && (
                <div style={sx("display:flex;flex-direction:column;gap:12px")}>
                  <div style={sx("align-self:flex-end;max-width:78%;background:var(--userbub);border:1px solid var(--userbub-line);border-radius:9px 9px 3px 9px;padding:9px 13px;font:13px/1.5 'Pretendard';color:var(--ink)")}>iG5A 인버터에 <span style={sx("font-family:'JetBrains Mono',monospace;font-size:12px")}>OHt</span> 에러 떴어</div>

                  <div style={sx("align-self:flex-start;max-width:86%;background:var(--aibub);border:1px solid var(--line);border-radius:9px 9px 9px 3px;padding:11px 13px;font:13px/1.62 'Pretendard';color:var(--ink2)")}>
                    <span style={sx("font-weight:700;color:var(--ink)")}><span style={sx("font-family:'JetBrains Mono',monospace")}>OHt</span> — 인버터 과열</span>입니다. 유력 원인은 냉각팬 고장·주위 온도 초과. 냉각팬 상태 점검을 권장합니다.
                    <div style={sx("margin-top:8px")}><span style={sx("display:inline-flex;align-items:center;gap:5px;font:500 10.5px 'JetBrains Mono',monospace;color:var(--blue-tx);border:1px solid var(--cite-bd);background:var(--cite-bg);border-radius:4px;padding:2px 7px")}><span>▤</span> iG5A 매뉴얼 p.208</span></div>
                  </div>

                  {/* safety block */}
                  <div style={sx("align-self:flex-start;max-width:88%;border:1px solid var(--saf-bd);border-left:4px solid var(--saf-bd);border-radius:7px;background:var(--saf-bg);padding:11px 13px")}>
                    <div style={sx("display:flex;align-items:center;gap:7px;margin-bottom:6px")}><span style={sx("font-size:13px")}>⚠</span><span style={sx("font:700 11px 'JetBrains Mono',monospace;letter-spacing:.06em;color:var(--orange-tx)")}>SAFETY · 감전 위험</span></div>
                    <div style={sx("font:13px/1.6 'Pretendard';color:var(--saf-tx)")}>커버 개방 전 전원 차단 후 <b style={sx("color:var(--saf-strong)")}>10분 이상 대기</b>, 테스터로 직류 전압 방전 확인. 활선 상태 접촉·측정 금지.</div>
                    <div style={sx("margin-top:8px")}><span style={sx("display:inline-flex;align-items:center;gap:5px;font:500 10.5px 'JetBrains Mono',monospace;color:var(--saf-cite-tx);border:1px solid var(--saf-cite-bd);background:var(--saf-cite-bg);border-radius:4px;padding:2px 7px")}><span>▤</span> iG5A 매뉴얼 p.4</span></div>
                  </div>

                  {/* po card */}
                  <div style={sx("align-self:flex-start;width:88%;border:1px solid var(--line2);border-radius:8px;background:var(--pocard);overflow:hidden")}>
                    <div style={sx("display:flex;justify-content:space-between;align-items:center;padding:9px 13px;border-bottom:1px solid var(--line);background:var(--pocard-head)")}>
                      <span style={sx("font:700 12.5px 'Pretendard';color:var(--ink)")}>발주서 초안 <span style={sx("font-family:'JetBrains Mono',monospace")}>#PO-0117</span></span>
                      <span style={sx("font:600 9.5px 'JetBrains Mono',monospace;letter-spacing:.05em;color:var(--dim);border:1px solid var(--line2);border-radius:3px;padding:2px 6px")}>DRAFT</span>
                    </div>
                    <div style={sx("display:grid;grid-template-columns:1fr 1fr;gap:9px 14px;padding:12px 13px;font:12px 'Pretendard'")}>
                      <div><span style={sx("color:var(--dim2)")}>품목</span><br /><span style={sx("color:var(--ink)")}>냉각팬 <span style={sx("font-family:'JetBrains Mono',monospace;font-size:11px")}>FAN-IG5-01</span></span></div>
                      <div><span style={sx("color:var(--dim2)")}>수량</span><br /><span style={sx("color:var(--ink)")}>2 EA <span style={sx("color:var(--orange-tx);font-size:11px")}>· 부족분 포함</span></span></div>
                      <div><span style={sx("color:var(--dim2)")}>공급사</span><br /><span style={sx("color:var(--ink)")}>A사 · 리드타임 3일</span></div>
                      <div><span style={sx("color:var(--dim2)")}>단가</span><br /><span style={sx("color:var(--ink);font-family:'JetBrains Mono',monospace")}>₩38,000</span></div>
                    </div>
                    <div style={sx("display:flex;gap:8px;padding:11px 13px;border-top:1px solid var(--line)")}>
                      <button onClick={onRequestApproval} style={sx("border:none;background:var(--blue);color:#fff;border-radius:6px;padding:9px 16px;font:600 12px 'Pretendard';cursor:pointer")}>팀장 승인 요청</button>
                      <button style={sx("border:1px solid var(--line2);background:transparent;color:var(--ink2);border-radius:6px;padding:9px 14px;font:600 12px 'Pretendard';cursor:pointer")}>수정</button>
                    </div>
                  </div>
                </div>
              )}

              {isS3 && (
                <div style={sx("display:flex;flex-direction:column;gap:12px")}>
                  <div style={sx("align-self:flex-end;max-width:78%;background:var(--userbub);border:1px solid var(--userbub-line);border-radius:9px 9px 3px 9px;padding:9px 13px;font:13px/1.5 'Pretendard';color:var(--ink)")}>3번 라인 인버터 <b>또</b> <span style={sx("font-family:'JetBrains Mono',monospace;font-size:12px")}>OCt</span> 떴어</div>

                  <div style={sx("align-self:flex-start;max-width:86%;background:var(--aibub);border:1px solid var(--line);border-radius:9px 9px 9px 3px;padding:11px 13px;font:13px/1.62 'Pretendard';color:var(--ink2)")}>
                    <span style={sx("font-weight:700;color:var(--ink)")}><span style={sx("font-family:'JetBrains Mono',monospace")}>OCt</span> — 인버터 과전류</span>입니다. 다만 이 설비는 <b style={sx("color:var(--orange-tx)")}>30일 내 3회 반복 발생</b>(매번 리셋만 수행)으로, 단순 조치 대신 <b style={sx("color:var(--ink)")}>근본원인 점검 모드</b>로 전환합니다.
                    <div style={sx("margin-top:8px")}><span style={sx("display:inline-flex;align-items:center;gap:5px;font:500 10.5px 'JetBrains Mono',monospace;color:var(--blue-tx);border:1px solid var(--cite-bd);background:var(--cite-bg);border-radius:4px;padding:2px 7px")}><span>▤</span> iG5A 매뉴얼 p.212 · 6.3 보호기능</span></div>
                  </div>

                  {/* 반복 고장 감지 배너 */}
                  <div style={sx("align-self:flex-start;max-width:88%;display:flex;align-items:center;gap:9px;border:1px solid var(--line2);border-radius:7px;background:var(--raise);padding:9px 12px")}>
                    <span style={sx("width:22px;height:22px;flex-shrink:0;border-radius:5px;background:var(--cite-bg);border:1px solid var(--cite-bd);display:flex;align-items:center;justify-content:center;font:700 11px 'JetBrains Mono';color:var(--blue-tx)")}>3×</span>
                    <span style={sx("font:12px/1.5 'Pretendard';color:var(--ink2)")}><b style={sx("color:var(--ink)")}>반복 고장 감지</b> — 3번 라인 <span style={sx("font-family:'JetBrains Mono',monospace;font-size:11px")}>INV-L3-01</span> · 최근 30일 <span style={sx("font-family:'JetBrains Mono',monospace;font-size:11px")}>OCt</span> 3회 (07-01·07-11·07-19)</span>
                  </div>

                  {/* safety block */}
                  <div style={sx("align-self:flex-start;max-width:88%;border:1px solid var(--saf-bd);border-left:4px solid var(--saf-bd);border-radius:7px;background:var(--saf-bg);padding:11px 13px")}>
                    <div style={sx("display:flex;align-items:center;gap:7px;margin-bottom:6px")}><span style={sx("font-size:13px")}>⚠</span><span style={sx("font:700 11px 'JetBrains Mono',monospace;letter-spacing:.06em;color:var(--orange-tx)")}>SAFETY · 감전 위험</span></div>
                    <div style={sx("font:13px/1.6 'Pretendard';color:var(--saf-tx)")}>절연저항 측정 전 전원 차단 후 <b style={sx("color:var(--saf-strong)")}>10분 이상 대기</b>, 테스터로 직류 전압 방전 확인. 활선 상태 절연 측정 금지.</div>
                    <div style={sx("margin-top:8px")}><span style={sx("display:inline-flex;align-items:center;gap:5px;font:500 10.5px 'JetBrains Mono',monospace;color:var(--saf-cite-tx);border:1px solid var(--saf-cite-bd);background:var(--saf-cite-bg);border-radius:4px;padding:2px 7px")}><span>▤</span> iG5A 트러블슈팅 p.6</span></div>
                  </div>

                  {/* 발주 보류 상태 블록 */}
                  <div style={sx("align-self:flex-start;width:88%;border:1px solid var(--line2);border-left:4px solid var(--orange);border-radius:8px;background:var(--pocard);overflow:hidden")}>
                    <div style={sx("display:flex;justify-content:space-between;align-items:center;padding:9px 13px;border-bottom:1px solid var(--line);background:var(--pocard-head)")}>
                      <span style={sx("display:flex;align-items:center;gap:7px;font:700 12.5px 'Pretendard';color:var(--ink)")}><span style={sx("font-size:13px")}>⏸</span> 발주 보류 — 원인 확정 후 진행</span>
                      <span style={sx("font:600 9.5px 'JetBrains Mono',monospace;letter-spacing:.05em;color:var(--orange-tx);border:1px solid var(--saf-cite-bd);background:var(--saf-cite-bg);border-radius:3px;padding:2px 6px")}>HOLD</span>
                    </div>
                    <div style={sx("padding:11px 13px;font:12px/1.6 'Pretendard';color:var(--ink2)")}>
                      반복 고장은 부품 교체만으로 재발할 수 있어, <b style={sx("color:var(--ink)")}>근본원인이 확정되기 전에는 발주서를 생성하지 않습니다.</b> 아래 점검을 먼저 진행하세요.
                      <div style={sx("margin-top:10px;display:flex;flex-direction:column;gap:7px")}>
                        <label style={sx("display:flex;align-items:center;gap:8px;font:12px 'Pretendard';color:var(--ink2);cursor:pointer")}><span style={sx("width:15px;height:15px;border:1.5px solid var(--dim3);border-radius:3px;flex-shrink:0")} />출력측 지락(단락) 점검 <span style={sx("font:10px 'JetBrains Mono';color:var(--dim2)")}>· p.212</span></label>
                        <label style={sx("display:flex;align-items:center;gap:8px;font:12px 'Pretendard';color:var(--ink2);cursor:pointer")}><span style={sx("width:15px;height:15px;border:1.5px solid var(--dim3);border-radius:3px;flex-shrink:0")} />모터 절연저항 측정 (권선 절연 저하) <span style={sx("font:10px 'JetBrains Mono';color:var(--dim2)")}>· p.213</span></label>
                        <label style={sx("display:flex;align-items:center;gap:8px;font:12px 'Pretendard';color:var(--ink2);cursor:pointer")}><span style={sx("width:15px;height:15px;border:1.5px solid var(--dim3);border-radius:3px;flex-shrink:0")} />부하 이상·가감속 시간 과다 확인 <span style={sx("font:10px 'JetBrains Mono';color:var(--dim2)")}>· p.214</span></label>
                      </div>
                    </div>
                    <div style={sx("display:flex;gap:8px;align-items:center;padding:11px 13px;border-top:1px solid var(--line)")}>
                      <button style={sx("border:none;background:var(--blue);color:#fff;border-radius:6px;padding:9px 16px;font:600 12px 'Pretendard';cursor:pointer")}>점검 결과 입력</button>
                      <span style={sx("font:11px 'Pretendard';color:var(--dim2)")}>원인 확정 시 발주서 초안 생성이 재개됩니다</span>
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* 입력: 채팅 + 음성 */}
            <div style={sx("border-top:1px solid var(--line);background:var(--head);padding:12px 14px")}>
              {!listening ? (
                <div style={sx("display:flex;gap:8px;align-items:center")}>
                  <button onClick={() => setListening(true)} title="음성으로 말하기" style={sx("width:40px;height:40px;flex-shrink:0;border:1px solid var(--line2);background:var(--raise);border-radius:9px;color:var(--dim);cursor:pointer;font-size:16px;display:flex;align-items:center;justify-content:center")}>🎤</button>
                  <div style={sx("flex:1;height:40px;border:1px solid var(--line2);border-radius:9px;background:var(--field);display:flex;align-items:center;padding:0 13px;font:12.5px 'Pretendard';color:var(--field-tx)")}>메시지를 입력하거나, 마이크를 눌러 말하세요…</div>
                  <button style={sx("width:40px;height:40px;flex-shrink:0;border:1px solid var(--line2);background:var(--raise);border-radius:9px;color:var(--dim);cursor:pointer")}>📷</button>
                  <button style={sx("height:40px;border:none;background:var(--blue);color:#fff;border-radius:9px;padding:0 20px;font:600 12.5px 'Pretendard';cursor:pointer")}>전송</button>
                </div>
              ) : (
                <div style={sx("display:flex;gap:12px;align-items:center;height:40px")}>
                  <button onClick={() => setListening(false)} style={sx("width:40px;height:40px;flex-shrink:0;border:none;background:var(--orange);border-radius:9px;color:#fff;cursor:pointer;font-size:16px;display:flex;align-items:center;justify-content:center;animation:mq-ring 1.4s infinite")}>■</button>
                  <div style={sx("flex:1;display:flex;align-items:center;gap:12px;height:40px;border:1px solid var(--saf-cite-bd);border-radius:9px;background:var(--saf-cite-bg);padding:0 15px")}>
                    <div style={sx("display:flex;align-items:flex-end;gap:3px;height:20px")}>
                      {[0, 0.15, 0.3, 0.45, 0.6].map((d) => (
                        <span key={d} style={sx(`width:3px;height:100%;background:var(--orange);border-radius:2px;animation:mq-wave .9s ease-in-out infinite;animation-delay:${d}s`)} />
                      ))}
                    </div>
                    <span style={sx("font:600 12.5px 'Pretendard';color:var(--saf-tx)")}>듣고 있어요 — 말씀하세요</span>
                    <div style={sx("flex:1")} />
                    <span style={sx("font:11px 'JetBrains Mono',monospace;color:var(--saf-cite-tx)")}>0:03</span>
                  </div>
                  <button onClick={() => setListening(false)} style={sx("height:40px;border:1px solid var(--line2);background:var(--raise);color:var(--ink2);border-radius:9px;padding:0 16px;font:600 12.5px 'Pretendard';cursor:pointer")}>완료</button>
                </div>
              )}
            </div>
          </div>

          {/* trace */}
          <div style={sx("display:flex;flex-direction:column;background:var(--panel)")}>
            <div style={sx("display:flex;border-bottom:1px solid var(--line)")}>
              <div style={sx("padding:11px 15px;font:700 12px 'Pretendard';color:var(--ink);border-bottom:2px solid var(--blue-br)")}>실행 로그</div>
              <div style={sx("padding:11px 15px;font:500 12px 'Pretendard';color:var(--dim3)")}>근거 문서</div>
              <div style={sx("padding:11px 15px;font:500 12px 'Pretendard';color:var(--dim3)")}>발주 이력</div>
            </div>

            {isS1 && (
              <div>
                <div style={sx("padding:15px 16px 10px;display:flex;align-items:center;gap:8px;border-bottom:1px solid var(--step-line)")}>
                  <span style={sx("font:600 10px 'JetBrains Mono',monospace;color:var(--blue-tx2);letter-spacing:.08em")}>SESSION #S1 · 오케스트레이션</span>
                  <div style={sx("flex:1")} />
                  <span style={sx("font:10px 'JetBrains Mono',monospace;color:var(--dim2)")}>2.1s · 5 calls</span>
                </div>
                <div style={sx("padding:16px;display:flex;flex-direction:column")}>
                  <TraceStep line summary="✓ 0.4s · 과열 · related: FAN-IG5-01" summaryColor="var(--blue-tx2)" status="ok" name="lookup_error_code" input={'in: {model:"iG5A", code:"OHt"}'} />
                  <TraceStep line summary="✓ 1.2s · p.208 인용 2건" summaryColor="var(--blue-tx2)" status="ok" name="rag_search_manual" input={'in: {query:"OHt 점검 절차"}'} />
                  <TraceStep line summary="⚠ 분기 · 재고 1 < 안전재고 3 → 부족분 2 제안" summaryColor="var(--orange-tx2)" status="warn" name="search_inventory" input={'in: {part:"FAN-IG5-01"}'} />
                  <TraceStep line summary="✓ 0.3s · A사 3일 vs B사 14일" summaryColor="var(--blue-tx2)" status="ok" name="get_supplier_quotes" input={'in: {part:"FAN-IG5-01", qty:2}'} />
                  <TraceStep summary="○ pending" summaryColor="var(--dim2)" status="pending" name="create_po_draft" input="대기: 사용자 공급사 선택 필요" />
                </div>
              </div>
            )}

            {isS3 && (
              <div>
                <div style={sx("padding:15px 16px 10px;display:flex;align-items:center;gap:8px;border-bottom:1px solid var(--step-line)")}>
                  <span style={sx("font:600 10px 'JetBrains Mono',monospace;color:var(--orange-tx2);letter-spacing:.08em")}>SESSION #S3 · 이력 기반 판단 · 분기</span>
                  <div style={sx("flex:1")} />
                  <span style={sx("font:10px 'JetBrains Mono',monospace;color:var(--dim2)")}>1.9s · 3 calls</span>
                </div>
                <div style={sx("padding:16px;display:flex;flex-direction:column")}>
                  <TraceStep line summary="✓ 0.4s · 과전류 · related: 모터·케이블" summaryColor="var(--blue-tx2)" status="ok" name="lookup_error_code" input={'in: {model:"iG5A", code:"OCt"}'} />
                  <TraceStep line summary="⚠ 분기 · count 3, repeated=true → 근본원인 모드" summaryColor="var(--orange-tx2)" status="warn" name="get_error_history" input={'in: {equipment_id:"INV-L3-01", days:30}'} />
                  <TraceStep line summary="✓ 1.1s · p.212·213 인용 3건 · ⚠ 안전 경고 삽입" summaryColor="var(--blue-tx2)" status="ok" name="rag_search_manual" input={'in: {query:"OCt 근본원인 점검 절차"}'} />
                  <TraceStep summary="⏸ held · 발주 보류" summaryColor="var(--orange-tx2)" status="held" name="create_po_draft" nameStrike input="차단: 원인 확정 전 발주 금지" />
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------------- */
/* One node in the agent execution trace timeline.                           */
type StepStatus = "ok" | "warn" | "pending" | "held";

function TraceStep({
  name,
  input,
  summary,
  summaryColor,
  status,
  line = false,
  nameStrike = false,
}: {
  name: string;
  input: string;
  summary: string;
  summaryColor: string;
  status: StepStatus;
  line?: boolean;
  nameStrike?: boolean;
}) {
  const dot: Record<StepStatus, string> = {
    ok: "width:17px;height:17px;border-radius:50%;background:var(--blue);border:2px solid var(--blue-br);flex-shrink:0;display:flex;align-items:center;justify-content:center;font:700 9px 'JetBrains Mono';color:#fff;z-index:1",
    warn: "width:17px;height:17px;border-radius:50%;background:var(--orange);border:2px solid var(--orange-tx);flex-shrink:0;display:flex;align-items:center;justify-content:center;font:700 10px 'JetBrains Mono';color:#fff;z-index:1",
    pending: "width:17px;height:17px;border-radius:50%;background:transparent;border:2px dashed var(--dim3);flex-shrink:0;z-index:1",
    held: "width:17px;height:17px;border-radius:50%;background:transparent;border:2px solid var(--orange-tx);flex-shrink:0;display:flex;align-items:center;justify-content:center;font:700 10px 'JetBrains Mono';color:var(--orange-tx);z-index:1",
  };
  const dotGlyph: Record<StepStatus, string> = { ok: "✓", warn: "!", pending: "", held: "⏸" };
  const nameColor = status === "pending" || status === "held" ? "var(--dim)" : "var(--ink2)";
  const inputColor = status === "pending" || status === "held" ? "var(--dim3)" : "var(--dim2)";

  return (
    <div style={sx(`display:flex;gap:12px;position:relative${line ? ";padding-bottom:16px" : ""}`)}>
      {line && <div style={sx("position:absolute;left:8px;top:20px;bottom:0;width:1.5px;background:var(--step-line)")} />}
      <div style={sx(dot[status])}>{dotGlyph[status]}</div>
      <div style={sx("flex:1")}>
        <div style={sx(`font:700 12px 'JetBrains Mono',monospace;color:${nameColor}`)}>{nameStrike ? <s>{name}</s> : name}</div>
        <div style={sx(`font:11px/1.4 'JetBrains Mono',monospace;color:${inputColor};margin-top:2px`)}>{input}</div>
        <div style={sx(`font:10.5px/1.5 'JetBrains Mono',monospace;color:${summaryColor};margin-top:3px`)}>{summary}</div>
      </div>
    </div>
  );
}
