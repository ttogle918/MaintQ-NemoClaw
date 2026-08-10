import Link from "next/link";
import { CitationChip } from "@/components/ui/CitationChip";
import { sx } from "@/lib/sx";
import type { EvidenceEntry } from "@/lib/types";

/** 발주 상세의 기본 제목. 인자를 주지 않으면 이전과 **한 글자도 다르지 않다**. */
const DEFAULT_TITLE = "근거 요약 · 대화 전체를 읽지 않아도 판단 가능";

/**
 * 근거 요약 카드 — 팀장이 대화를 안 읽고 판단할 수 있게 하는 게 목적 (D18).
 *
 * 행 구성은 po_drafts 의 reason(헤드라인) + evidence JSON(D34)에서 온다:
 *   symptoms → SYMPTOMS · basis → DIAGNOSIS 인용 · notes → NOTES
 *
 * `title` 은 처분 상세(`DecisionDetail`)가 같은 시각 언어로 결정 요약을 싣기 위해 열어 둔
 * 자리다 — 처분서의 근거는 대화가 아니라 법령·룰이라 제목이 그대로면 화면이 거짓말을 한다.
 */
export function EvidenceCard({
  entries,
  title = DEFAULT_TITLE,
}: {
  entries: EvidenceEntry[];
  title?: string;
}) {
  return (
    <div
      style={sx(
        "border:1px solid var(--line2);border-radius:8px;background:var(--evi);padding:15px 16px;margin-bottom:14px"
      )}
    >
      <div
        style={sx(
          "font:700 10px 'JetBrains Mono',monospace;letter-spacing:.08em;color:var(--dim2);margin-bottom:12px"
        )}
      >
        {title}
      </div>
      <div style={sx("display:flex;flex-direction:column;gap:11px")}>
        {entries.map((e) => (
          <EvidenceRow key={e.label} entry={e} />
        ))}
      </div>
    </div>
  );
}

function EvidenceRow({ entry }: { entry: EvidenceEntry }) {
  return (
    <div style={sx("display:flex;gap:12px;align-items:baseline")}>
      <span
        style={sx(
          "font:700 10px 'JetBrains Mono',monospace;color:var(--dim);width:82px;flex-shrink:0"
        )}
      >
        {entry.label}
      </span>
      <span style={sx("font:12.5px/1.5 'Pretendard';color:var(--ink)")}>
        {entry.href ? (
          <Link
            href={entry.href}
            style={sx("color:var(--blue-br);text-decoration:underline")}
          >
            {entry.value}
          </Link>
        ) : (
          entry.value
        )}
        {entry.citation && (
          <>
            {" "}
            <CitationChip citation={entry.citation} />
          </>
        )}
      </span>
    </div>
  );
}
