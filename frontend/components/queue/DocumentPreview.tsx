"use client";

import { useState } from "react";
import { sx } from "@/lib/sx";

/**
 * D118 — 발주요청서(02)·진단보고서(01) 미리보기.
 *
 * ⛔ 문서 문안을 프론트가 만들지 않는다(`DecisionDetail.tsx`와 같은 원칙). 백엔드가
 * `po["documents_preview"]`에서 조회 시점에 렌더한 평문을 그대로 옮겨 적는다 — 여기서
 * 줄바꿈·필드를 다시 조립하면 doc2/doc1(`backend/services/po_documents.py`)의 렌더와
 * 화면이 서로 다른 문서를 보여줄 위험이 생긴다.
 *
 * 기본은 접힌 상태다 — 근거 카드·견적 비교가 이미 화면의 핵심이고, 전체 문서 본문은
 * "필요할 때 펼쳐 보는" 부가 자료다.
 */
export function DocumentPreview({
  title,
  sub,
  text,
}: {
  title: string;
  sub: string;
  text: string | null;
}) {
  const [open, setOpen] = useState(false);

  return (
    <div
      style={sx(
        "border:1px solid var(--line);border-radius:8px;background:var(--surface);" +
          "margin-bottom:14px;overflow:hidden"
      )}
    >
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        style={sx(
          "width:100%;display:flex;align-items:center;gap:9px;padding:12px 16px;" +
            "background:transparent;border:none;cursor:pointer;text-align:left"
        )}
      >
        <div style={sx("flex:1")}>
          <div
            style={sx(
              "font:700 11px 'JetBrains Mono',monospace;letter-spacing:.06em;color:var(--ink2)"
            )}
          >
            {title}
          </div>
          <div style={sx("font:11px 'Pretendard';color:var(--dim2);margin-top:3px")}>{sub}</div>
        </div>
        <span style={sx("font:11px 'JetBrains Mono',monospace;color:var(--dim2)")}>
          {text === null ? "해당 없음" : open ? "접기 ▲" : "펼치기 ▼"}
        </span>
      </button>

      {text === null ? (
        <div
          style={sx(
            "padding:0 16px 14px;font:12px 'Pretendard';color:var(--dim2)"
          )}
        >
          이 발주는 에러코드 진단에서 시작하지 않아(단종 대체·정기 교체 등) 진단 보고서가
          성립하지 않습니다.
        </div>
      ) : (
        open && (
          <pre
            style={sx(
              "margin:0;padding:0 16px 16px;font:12px/1.7 'JetBrains Mono',monospace;" +
                "color:var(--ink2);white-space:pre-wrap;word-break:break-word"
            )}
          >
            {text}
          </pre>
        )
      )}
    </div>
  );
}
