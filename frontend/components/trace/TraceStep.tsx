import { sx } from "@/lib/sx";
import type { TraceStatus, TraceStepData } from "@/lib/types";

/**
 * 장애 전용 적색 (D44 · 09_RUNTIME §3 "✗ error(붉은 점)").
 *
 * 테마 토큰(globals.css)에는 error 색이 없고, 오렌지는 **안전·긴급 전용**이라
 * 재사용하면 장애와 안전 경고가 같은 색으로 섞인다. 토큰 추가는 4개 테마를 동시에
 * 건드리는 일이라 이 태스크(추가만) 범위 밖이므로 리터럴로 둔다.
 * 다크(--panel #0d1014)·라이트(--panel #fafbfc) 양쪽에서 읽히는 중간 채도를 골랐다.
 */
const ERROR_DOT = "#C0392B";
const ERROR_TX = "#D64545";

const DOT: Record<TraceStatus, string> = {
  ok: "background:var(--blue);border:2px solid var(--blue-br);color:#fff",
  warn: "background:var(--orange);border:2px solid var(--orange-tx);color:#fff",
  pending: "background:transparent;border:2px dashed var(--dim3)",
  held: "background:transparent;border:2px solid var(--orange-tx);color:var(--orange-tx)",
  error: `background:${ERROR_DOT};border:2px solid ${ERROR_TX};color:#fff`,
};

const GLYPH: Record<TraceStatus, string> = {
  ok: "✓",
  warn: "!",
  pending: "",
  held: "⏸",
  error: "✗",
};

const SUMMARY_COLOR: Record<TraceStatus, string> = {
  ok: "var(--blue-tx2)",
  warn: "var(--orange-tx2)",
  pending: "var(--dim2)",
  held: "var(--orange-tx2)",
  error: ERROR_TX,
};

/**
 * 타임라인 한 스텝 = tool_call + tool_result 한 쌍.
 * tool_call 은 도구 호출 "직전" 발행되므로 pending 상태가 먼저 그려지고,
 * tool_result 가 도착하면 ok/warn 으로 바뀐다 (A1).
 */
export function TraceStep({
  step,
  connector = false,
}: {
  step: TraceStepData;
  /** 다음 스텝과 잇는 세로선 */
  connector?: boolean;
}) {
  const muted = step.status === "pending" || step.status === "held";
  const nameColor = muted ? "var(--dim)" : "var(--ink2)";
  const inputColor = muted ? "var(--dim3)" : "var(--dim2)";

  return (
    <div
      style={sx(
        `display:flex;gap:12px;position:relative${connector ? ";padding-bottom:16px" : ""}`
      )}
    >
      {connector && (
        <div
          style={sx(
            "position:absolute;left:8px;top:20px;bottom:0;width:1.5px;background:var(--step-line)"
          )}
        />
      )}
      <div
        style={sx(
          "width:17px;height:17px;border-radius:50%;flex-shrink:0;display:flex;align-items:center;" +
            `justify-content:center;font:700 9px 'JetBrains Mono';z-index:1;${DOT[step.status]}`
        )}
      >
        {GLYPH[step.status]}
      </div>
      <div style={sx("flex:1")}>
        <div style={sx(`font:700 12px 'JetBrains Mono',monospace;color:${nameColor}`)}>
          {step.strikeTool ? <s>{step.tool}</s> : step.tool}
        </div>
        <div
          style={sx(`font:11px/1.4 'JetBrains Mono',monospace;color:${inputColor};margin-top:2px`)}
        >
          {step.input}
        </div>
        <div
          style={sx(
            `font:10.5px/1.5 'JetBrains Mono',monospace;color:${SUMMARY_COLOR[step.status]};margin-top:3px`
          )}
        >
          {step.summary}
        </div>
      </div>
    </div>
  );
}
