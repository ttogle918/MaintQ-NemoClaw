import Link from "next/link";
import { CitationChip } from "@/components/ui/CitationChip";
import { sx } from "@/lib/sx";
import type { EvidenceEntry } from "@/lib/types";

/**
 * 근거 요약 카드 — 팀장이 대화를 안 읽고 판단할 수 있게 하는 게 목적 (D18).
 *
 * 행 구성은 po_drafts 의 reason(헤드라인) + evidence JSON(D34)에서 온다:
 *   symptoms → SYMPTOMS · basis → DIAGNOSIS 인용 · notes → NOTES
 */
export function EvidenceCard({ entries }: { entries: EvidenceEntry[] }) {
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
        근거 요약 · 대화 전체를 읽지 않아도 판단 가능
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
