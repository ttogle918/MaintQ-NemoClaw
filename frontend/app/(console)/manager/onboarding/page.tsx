"use client";

import { usePathname } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ConsoleHeader, Spacer } from "@/components/layout/ConsoleFrame";
import { SafetyBlock } from "@/components/chat/SafetyBlock";
import { OnboardingBadge } from "@/components/onboarding/OnboardingBadge";
import { Badge, type BadgeTone } from "@/components/ui/Badge";
import { Divider, Logo } from "@/components/ui/Chip";
import { CitationChip } from "@/components/ui/CitationChip";
import { Mono } from "@/components/ui/Mono";
import {
  ApiError,
  approveSafetyCandidate,
  errorBody,
  getOnboardingBatches,
  getOnboardingGroups,
  getOnboardingStatus,
  getSafetyCandidates,
  promoteOnboardingGroup,
  rejectOnboardingRow,
  rejectSafetyCandidate,
  type ApiOnboardingBatch,
  type ApiOnboardingCause,
  type ApiOnboardingGroup,
  type ApiOnboardingRow,
  type ApiPromoteResult,
  type ApiSafetyCandidate,
} from "@/lib/api";
import type { Citation } from "@/lib/citation";
import {
  GROUP_FLAG_FILTERS,
  GROUP_STATUS_FILTERS,
  SAFETY_KIND_FILTERS,
  approvedDischargeCount,
  confidenceLabel,
  confidenceTone,
  defaultNormId,
  effectiveAcknowledged,
  findApprovedDischarge,
  flagHint,
  flagLabel,
  flagTone,
  groupFlags,
  groupHasLowConfidence,
  groupMatchesFlagFilter,
  groupStatusView,
  isCandidateStaged,
  isDischargeFailClosed,
  isDischargeWait,
  isOnboardingBlocked,
  isRowStaged,
  onboardingBadgeView,
  onboardingErrorText,
  promotableRows,
  promoteBlockers,
  requiredFlags,
  rowStateView,
  safetyKindLabel,
  safetyKindMatches,
  safetyStateView,
  safetyTextPrecheck,
  utcStamp,
  type GroupFlagFilter,
  type GroupStatusKey,
  type OnboardingTone,
} from "@/lib/onboarding";
import { roleFromPath, type Role } from "@/lib/role";
import { sx } from "@/lib/sx";

/**
 * `/manager/onboarding` — 새 기종 온보딩 검수 · 안전 문구 승인 (MQ-1911, 화면 C·D).
 *
 * 계약 (`backend/routers/onboarding.py` · `06 §2.11`):
 * - **코드 그룹 단위 승격**(D156) — 같은 코드의 staged 행을 한 번에 올린다. 행마다 정규화
 *   선택(기본 최신) · 대표(primary) 라디오 · 플래그 확인 체크(`acknowledged_flags`).
 *   디자인 C 의 「행 단위 승인」과 다르다 — 동작은 API 를 따른다. **일괄 승인 버튼 없음.**
 * - **원문(en)·정규화(ko) 나란히**(D145) — 번역만 보이는 상태가 없다. 인용(페이지)은 원문 쪽에만.
 * - 안전 문구(D147·D157): 한국어 문안은 **사람이 빈 칸에서 직접 쓴다**(정규화문을 미리 채우지
 *   않는다). 「원문과 대조했다」 체크 + 확인 모달 후 확정, 되돌리기 없음. 수치 검사·기종당 방전
 *   대기 1건은 **서버가 최종 판정** — 화면의 사전 경고는 참고용이고 서버 메시지를 그대로 보여 준다.
 * - 쓰기는 manager 만. 아니면 버튼 비활성 + 서버 403 그대로.
 *
 * ⛔ 상태 문자열 직접 비교 금지 (D87) — `lib/onboarding.ts` 헬퍼만 부른다.
 * ⛔ 오렌지는 안전 블록 미리보기에만 — 주입 의심 플래그는 잉크색(보안 이벤트)이다.
 */
export default function ManagerOnboardingPage() {
  const role = roleFromPath(usePathname() ?? "");
  const canWrite = role === "manager";

  const [batches, setBatches] = useState<ApiOnboardingBatch[] | null>(null);
  const [batchId, setBatchId] = useState<number | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [tab, setTab] = useState<"codes" | "safety">("codes");
  // 기종 상태 조회 결과 — 어느 기종에 대한 답인지 함께 둔다(다른 기종의 답을 현재 기종으로 오인하지 않게).
  // `failed` 는 조회 실패 — 「차단」으로 단정하지 않고 따로 보여 준다 (D87).
  const [statusLookup, setStatusLookup] = useState<
    { model: string; state: string; failed: false } | { model: string; failed: true; error: string } | null
  >(null);
  const [refresh, setRefresh] = useState(0);

  const batch = batches?.find((b) => b.batch_id === batchId) ?? null;
  const model = batch?.model ?? null;

  useEffect(() => {
    let alive = true;
    getOnboardingBatches(role)
      .then((list) => {
        if (!alive) return;
        setBatches(list);
        setLoadError(null);
        setBatchId((cur) => cur ?? (list.length > 0 ? list[list.length - 1].batch_id : null));
      })
      .catch((e: unknown) => {
        if (alive) setLoadError(describeError(e));
      });
    return () => {
      alive = false;
    };
  }, [role, refresh]);

  useEffect(() => {
    if (!model) return;
    let alive = true;
    getOnboardingStatus(role, model)
      .then((s) => alive && setStatusLookup({ model, state: s.state, failed: false }))
      .catch((e: unknown) => alive && setStatusLookup({ model, failed: true, error: describeError(e) }));
    return () => {
      alive = false;
    };
  }, [role, model, refresh]);

  const onChanged = useCallback(() => setRefresh((n) => n + 1), []);
  // 현재 기종에 대한 답만 쓴다. 아직 답이 없으면(로딩) 배너를 띄우지 않는다.
  const lookup = statusLookup && statusLookup.model === model ? statusLookup : null;

  return (
    <div style={sx("display:flex;flex-direction:column;align-items:center")}>
      <div
        style={sx(
          "width:1320px;max-width:100%;background:var(--surface);border:1px solid var(--line);color:var(--ink);" +
            "border-radius:8px;overflow:hidden;box-shadow:0 10px 40px rgba(0,0,0,.28)"
        )}
      >
        <ConsoleHeader>
          <Logo />
          <span style={sx("font:600 13px 'Pretendard';color:var(--ink)")}>MaintQ</span>
          <Divider />
          <span style={sx("font:700 12.5px 'Pretendard';color:var(--ink2)")}>기종 온보딩 검수</span>
          <Spacer />
          {!canWrite && (
            <Badge tone="neutral" size={10}>
              읽기 전용 — 승격·승인은 보전팀장만
            </Badge>
          )}
        </ConsoleHeader>

        {loadError && <ErrorBox title="온보딩 배치를 불러오지 못했습니다">{loadError}</ErrorBox>}
        {batches === null && !loadError && <Dim pad>불러오는 중…</Dim>}
        {batches !== null && batches.length === 0 && (
          <div style={sx("padding:48px 18px;text-align:center;font:13px 'Pretendard';color:var(--dim)")}>
            검수할 온보딩 없음
          </div>
        )}

        {batch && model && (
          <>
            <HeaderCard
              batch={batch}
              batches={batches ?? []}
              onPick={setBatchId}
              refreshKey={refresh}
            />
            {lookup?.failed && (
              <div style={sx("margin:0 18px 12px")}>
                <ErrorBox title="이 기종의 상태를 확인하지 못했습니다 (조회 실패)">
                  진단·절차 안내가 열려 있는지 차단되어 있는지 이 화면은 알 수 없습니다 — {lookup.error}
                </ErrorBox>
              </div>
            )}
            {lookup && !lookup.failed && onboardingBadgeView(lookup.state)?.known === false && (
              <div style={sx("margin:0 18px 12px")}>
                <ErrorBox title="이 기종의 상태를 이 화면이 모르는 값으로 받았습니다">
                  서버 응답 원문 <Mono size={11}>{lookup.state}</Mono> — 차단 여부를 단정하지 않습니다.
                </ErrorBox>
              </div>
            )}
            {lookup && !lookup.failed && isOnboardingBlocked(lookup.state) && (
              <div
                style={sx(
                  "margin:0 18px 12px;border:1px solid var(--cite-bd);background:var(--cite-bg);border-radius:7px;" +
                    "padding:9px 13px;font:12px/1.6 'Pretendard';color:var(--ink2)"
                )}
              >
                <b>🔒 이 기종의 점검·교체 절차 안내가 차단되어 있습니다</b>
                <span style={sx("color:var(--dim)")}>
                  {" "}
                  — 의도된 차단입니다. 코드가 승격돼야 진단이 되고, 방전 대기 안전 문구가 승인돼야 절차 안내가
                  열립니다 (D146·D157).
                </span>
              </div>
            )}
            <div style={sx("display:flex;gap:4px;padding:0 18px;border-bottom:1px solid var(--line)")}>
              <TabButton on={tab === "codes"} onClick={() => setTab("codes")}>
                코드 검수 · 승격
              </TabButton>
              <TabButton on={tab === "safety"} onClick={() => setTab("safety")}>
                안전 문구 후보
              </TabButton>
            </div>
            {tab === "codes" ? (
              <CodesTab
                key={`codes-${batch.batch_id}`}
                role={role}
                batch={batch}
                canWrite={canWrite}
                refreshKey={refresh}
                onChanged={onChanged}
              />
            ) : (
              <SafetyTab
                key={`safety-${model}`}
                role={role}
                model={model}
                canWrite={canWrite}
                refreshKey={refresh}
                onChanged={onChanged}
              />
            )}
          </>
        )}
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* 헤더 카드 — 기종 · 온보딩 뱃지 · 진행                                             */

function HeaderCard({
  batch,
  batches,
  onPick,
  refreshKey,
}: {
  batch: ApiOnboardingBatch;
  batches: ApiOnboardingBatch[];
  onPick: (id: number) => void;
  refreshKey: number;
}) {
  const total = Math.max(batch.rows, 1);
  const pct = (n: number) => `${((n / total) * 100).toFixed(2)}%`;
  return (
    <div
      style={sx(
        "margin:14px 18px 12px;border:1px solid var(--line);border-radius:8px;background:var(--panel);" +
          "padding:14px 16px;display:grid;grid-template-columns:minmax(0,1fr) 420px;gap:24px;align-items:center"
      )}
    >
      <div style={sx("display:flex;flex-direction:column;gap:6px;min-width:0")}>
        <div style={sx("display:flex;align-items:center;gap:10px;flex-wrap:wrap")}>
          <span style={sx("font:800 18px 'Pretendard';color:var(--ink)")}>
            <Mono size={18}>{batch.model}</Mono>
          </span>
          <OnboardingBadge model={batch.model} size={10} showFailure refreshKey={refreshKey} />
          <span
            style={sx(
              "font:700 10px 'Pretendard';color:var(--dim);border:1px dashed var(--line2);border-radius:4px;padding:2px 7px"
            )}
          >
            AI 초안 — 사람 승인 전
          </span>
          {batches.length > 1 && (
            <select
              value={batch.batch_id}
              onChange={(e) => onPick(Number(e.target.value))}
              style={sx("font:11px 'Pretendard';padding:3px 6px;background:var(--raise);color:var(--ink2)")}
            >
              {batches.map((b) => (
                <option key={b.batch_id} value={b.batch_id}>
                  배치 #{b.batch_id} · {b.model} · {b.manual_id}
                </option>
              ))}
            </select>
          )}
        </div>
        <div style={sx("font:11.5px 'Pretendard';color:var(--dim)")}>
          원본 매뉴얼 <Mono size={11}>{batch.manual_id}</Mono> (영문) · 배치 #{batch.batch_id} · 적재{" "}
          {utcStamp(batch.loaded_at)} · 정규화된 행 {batch.normalized_rows}/{batch.rows}
        </div>
        <div style={sx("font:11px 'Pretendard';color:var(--dim2)")}>
          승격 전 이 기종은 정비사 화면에서 <b>진단 불가(온보딩 중)</b> — 설계된 동작 (D146)
        </div>
      </div>
      <div style={sx("display:flex;flex-direction:column;gap:6px")}>
        <div style={sx("display:flex;justify-content:space-between;font:11px 'Pretendard';color:var(--dim)")}>
          <span>검수 진행 (행 기준)</span>
          <span>
            총 <b style={sx("color:var(--ink)")}>{batch.rows}</b>행
          </span>
        </div>
        <div style={sx("display:flex;height:7px;border-radius:4px;overflow:hidden;background:var(--sw);border:1px solid var(--line)")}>
          <div style={sx(`width:${pct(batch.approved)};background:var(--blue)`)} />
          <div style={sx(`width:${pct(batch.rejected)};background:var(--dim2)`)} />
        </div>
        <div style={sx("display:flex;gap:14px;font:11px 'Pretendard';color:var(--dim)")}>
          <span>
            <Swatch color="var(--blue)" /> 승격 <b style={sx("color:var(--ink)")}>{batch.approved}</b>
          </span>
          <span>
            <Swatch color="var(--dim2)" /> 반려 <b style={sx("color:var(--ink)")}>{batch.rejected}</b>
          </span>
          <span>
            <Swatch color="var(--sw)" /> 대기 <b style={sx("color:var(--ink)")}>{batch.staged}</b>
          </span>
        </div>
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* 코드 검수 탭                                                                   */

function CodesTab({
  role,
  batch,
  canWrite,
  refreshKey,
  onChanged,
}: {
  role: Role;
  batch: ApiOnboardingBatch;
  canWrite: boolean;
  refreshKey: number;
  onChanged: () => void;
}) {
  const [groups, setGroups] = useState<ApiOnboardingGroup[] | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<GroupStatusKey | "all">("pending");
  const [flagFilter, setFlagFilter] = useState<GroupFlagFilter>("all");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    getOnboardingGroups(role, batch.batch_id, "all")
      .then((g) => {
        if (!alive) return;
        setGroups(g);
        setFailure(null);
      })
      .catch((e: unknown) => alive && setFailure(describeError(e)));
    return () => {
      alive = false;
    };
  }, [role, batch.batch_id, refreshKey]);

  const visible = useMemo(() => {
    if (!groups) return [];
    const q = query.trim().toUpperCase();
    return groups.filter((g) => {
      const st = groupStatusView(g);
      if (statusFilter !== "all" && st.key !== statusFilter) return false;
      if (!groupMatchesFlagFilter(g, flagFilter)) return false;
      if (q && !g.code.includes(q) && !g.rows.some((r) => r.display_code.toUpperCase().includes(q))) return false;
      return true;
    });
  }, [groups, statusFilter, flagFilter, query]);

  const current = groups?.find((g) => g.code === selected) ?? null;

  if (failure) return <ErrorBox title="코드 그룹을 불러오지 못했습니다">{failure}</ErrorBox>;
  if (!groups) return <Dim pad>불러오는 중…</Dim>;

  return (
    <div style={sx("display:grid;grid-template-columns:300px minmax(0,1fr);min-height:640px")}>
      <div style={sx("border-right:1px solid var(--line);background:var(--panel);display:flex;flex-direction:column")}>
        <div style={sx("padding:12px 12px 8px;display:flex;flex-direction:column;gap:7px")}>
          <FilterRow label="상태">
            {GROUP_STATUS_FILTERS.map((f) => (
              <FilterChip key={f.key} on={statusFilter === f.key} onClick={() => setStatusFilter(f.key)}>
                {f.label}
              </FilterChip>
            ))}
          </FilterRow>
          <FilterRow label="플래그">
            {GROUP_FLAG_FILTERS.map((f) => (
              <FilterChip key={f.key} on={flagFilter === f.key} onClick={() => setFlagFilter(f.key)}>
                {f.label}
              </FilterChip>
            ))}
          </FilterRow>
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="코드 검색 (예: OH, CPF06)"
            style={sx(
              "font:12px 'JetBrains Mono',monospace;padding:6px 8px;border:1px solid var(--line2);border-radius:5px;" +
                "background:var(--field);color:var(--ink)"
            )}
          />
          <span style={sx("font:10px 'JetBrains Mono',monospace;color:var(--dim2);letter-spacing:.05em")}>
            코드 그룹 · {visible.length} / {groups.length} 표시
          </span>
        </div>
        <div style={sx("flex:1;overflow-y:auto;max-height:720px;padding:0 10px 12px;display:flex;flex-direction:column;gap:6px")}>
          {visible.length === 0 && <Dim>조건에 맞는 코드가 없습니다.</Dim>}
          {visible.map((g) => (
            <GroupListItem key={g.code} group={g} on={g.code === selected} onClick={() => setSelected(g.code)} />
          ))}
        </div>
      </div>

      <div style={sx("padding:16px 18px;min-width:0")}>
        {current ? (
          <GroupDetail
            key={current.code}
            role={role}
            group={current}
            manualLabel={`${batch.model} 매뉴얼`}
            canWrite={canWrite}
            onChanged={onChanged}
          />
        ) : (
          <Dim>왼쪽에서 코드 그룹을 고르십시오. 승격은 코드 그룹 단위로만 합니다 (D156) — 일괄 승인은 없습니다.</Dim>
        )}
      </div>
    </div>
  );
}

function GroupListItem({ group, on, onClick }: { group: ApiOnboardingGroup; on: boolean; onClick: () => void }) {
  const st = groupStatusView(group);
  const flags = groupFlags(group);
  const low = groupHasLowConfidence(group);
  const pages = group.rows.flatMap((r) => r.pages);
  const first = group.rows[0];
  return (
    <button
      onClick={onClick}
      style={sx(
        "text-align:left;cursor:pointer;border-radius:7px;padding:8px 10px;display:flex;flex-direction:column;gap:4px;color:var(--ink);" +
          (on ? "border:2px solid var(--blue);background:var(--sel)" : "border:1px solid var(--line);background:var(--surface)")
      )}
    >
      <div style={sx("display:flex;align-items:center;gap:6px")}>
        <span style={sx("font:700 13px 'JetBrains Mono',monospace;color:var(--ink)")}>{group.code}</span>
        {group.rows.map((r) => (
          <Badge key={r.row_id} tone="neutral" size={8.5}>
            {r.section_ko}
          </Badge>
        ))}
        <span style={sx("flex:1")} />
        {flags.some((f) => flagTone(f) === "security") && <FlagMark tone="security">SEC</FlagMark>}
        {low && <FlagMark tone="caution">LOW</FlagMark>}
        {group.rows.length > 1 && <FlagMark tone="neutral">×{group.rows.length}</FlagMark>}
        <ToneBadge tone={st.tone} size={9}>
          {st.label}
        </ToneBadge>
      </div>
      <div style={sx("display:flex;gap:6px;font:11px 'Pretendard';color:var(--dim)")}>
        <span style={sx("flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis")}>
          {first?.name_en ?? "—"}
        </span>
        <Mono size={10}>{pages.length ? `p.${Math.min(...pages)}` : ""}</Mono>
      </div>
    </button>
  );
}

function GroupDetail({
  role,
  group,
  manualLabel,
  canWrite,
  onChanged,
}: {
  role: Role;
  group: ApiOnboardingGroup;
  manualLabel: string;
  canWrite: boolean;
  onChanged: () => void;
}) {
  const st = groupStatusView(group);
  const staged = promotableRows(group.rows);
  const [selection, setSelection] = useState<Record<number, number | null>>(() =>
    Object.fromEntries(group.rows.map((r) => [r.row_id, defaultNormId(r)]))
  );
  const [primary, setPrimary] = useState<number | null>(staged[0]?.row_id ?? null);
  const [acked, setAcked] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ApiPromoteResult | null>(null);

  const needed = requiredFlags(group.rows, selection);
  // D156 — 보내는 것도, 체크 표시도 **현재 선택된 norm 이 요구하는 플래그 ∩ 체크한 플래그** 다.
  const ackedNow = effectiveAcknowledged(needed, acked);
  const blockers = promoteBlockers(group.rows, selection, primary, ackedNow);

  function selectNorm(rowId: number, nid: number) {
    const next = { ...selection, [rowId]: nid };
    setSelection(next);
    // norm 을 바꾸면 이전 체크가 새 선택으로 넘어가지 않게, 새 요구 플래그 밖의 체크는 버린다.
    // (A→B→A 로 돌아와도 A 의 플래그는 다시 확인해야 한다.)
    const nextNeeded = requiredFlags(group.rows, next);
    setAcked((a) => effectiveAcknowledged(nextNeeded, a));
  }
  const allFlags = groupFlags(group);

  async function promote() {
    if (primary === null) return;
    setBusy(true);
    setError(null);
    try {
      const res = await promoteOnboardingGroup(role, {
        model: group.model,
        code: group.code,
        primary_row_id: primary,
        rows: staged
          .filter((r) => selection[r.row_id] != null)
          .map((r) => ({ row_id: r.row_id, norm_id: selection[r.row_id] as number })),
        acknowledged_flags: ackedNow,
      });
      setResult(res);
      onChanged();
    } catch (e) {
      setError(describeError(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={sx("display:flex;flex-direction:column;gap:12px")}>
      <div style={sx("display:flex;align-items:center;gap:10px;flex-wrap:wrap")}>
        <span style={sx("font:800 22px 'JetBrains Mono',monospace;color:var(--ink)")}>{group.code}</span>
        {group.rows.map((r) => (
          <Badge key={r.row_id} tone="neutral" size={10}>
            {r.section_ko} · {r.display_code}
          </Badge>
        ))}
        <ToneBadge tone={st.tone} size={10.5}>
          {st.label}
        </ToneBadge>
        <Spacer />
        <span style={sx("font:10.5px 'Pretendard';color:var(--dim2)")}>
          {group.model} · 행 {group.rows.length}개 · 대기 {staged.length}
        </span>
      </div>

      {allFlags.map((f) => (
        <FlagBanner key={f} flag={f} />
      ))}
      {group.rows.length > 1 && (
        <div
          style={sx(
            "border:1px solid var(--line2);border-radius:7px;padding:8px 12px;font:12px/1.6 'Pretendard';color:var(--ink2)"
          )}
        >
          ⧉ <b>이 코드는 {group.rows.length}개 행({[...new Set(group.rows.map((r) => r.section_ko))].join(" · ")})에 있습니다</b>
          <span style={sx("color:var(--dim)")}>
            {" "}
            — 코드 단위로 함께 승격되며, 원인·조치 앞에 구역 접두가 붙습니다 (D156). 빠질 행은 먼저 반려하십시오.
          </span>
        </div>
      )}

      {group.rows.map((r) => (
        <RowCompare
          key={r.row_id}
          role={role}
          row={r}
          manualLabel={manualLabel}
          selectedNorm={selection[r.row_id] ?? null}
          onSelectNorm={(nid) => selectNorm(r.row_id, nid)}
          isPrimary={primary === r.row_id}
          onPrimary={() => setPrimary(r.row_id)}
          canWrite={canWrite}
          onChanged={onChanged}
        />
      ))}

      {result ? (
        <div
          style={sx(
            "border:1px solid var(--cite-bd);background:var(--cite-bg);border-radius:7px;padding:10px 13px;" +
              "font:12px/1.7 'Pretendard';color:var(--ink2)"
          )}
        >
          <b>승격 #{result.promo_id} 완료</b> — <Mono size={11.5}>{result.error_code.display_code}</Mono>{" "}
          {result.error_code.error_name} · severity <Mono size={11}>{result.error_code.severity}</Mono> · 원인{" "}
          {result.error_code.causes.length}건 · 조치 {result.error_code.actions.length}건 · 청크 {result.chunk_ids.length}건 ·
          근거 {result.error_code.actions_source.manual_id} p.{result.error_code.actions_source.page}
          <br />
          <span style={sx("color:var(--dim)")}>승격 취소 API 는 없습니다 — 잘못 승격했다면 DB 수동 조치 절차를 따르십시오.</span>
        </div>
      ) : (
        staged.length > 0 && (
          <div
            style={sx(
              "border-top:1px solid var(--line);padding-top:12px;display:flex;flex-direction:column;gap:8px"
            )}
          >
            {needed.length > 0 && (
              <div style={sx("display:flex;flex-direction:column;gap:4px")}>
                <span style={sx("font:700 11.5px 'Pretendard';color:var(--ink2)")}>
                  플래그 확인 — 체크한 플래그만 acknowledged_flags 로 보냅니다
                </span>
                {needed.map((f) => (
                  <label key={f} style={sx("display:flex;align-items:center;gap:7px;font:12px 'Pretendard';color:var(--ink2)")}>
                    <input
                      type="checkbox"
                      checked={ackedNow.includes(f)}
                      disabled={!canWrite}
                      onChange={(e) =>
                        setAcked((a) => (e.target.checked ? [...a.filter((x) => x !== f), f] : a.filter((x) => x !== f)))
                      }
                    />
                    {flagLabel(f)} <Mono size={10.5}>{f}</Mono>
                    <span style={sx("color:var(--dim2);font-size:11px")}>— {flagHint(f)}</span>
                  </label>
                ))}
              </div>
            )}
            {blockers.length > 0 && (
              <ul style={sx("margin:0;padding-left:18px;font:11.5px/1.6 'Pretendard';color:var(--dim)")}>
                {blockers.map((b) => (
                  <li key={b}>{b}</li>
                ))}
              </ul>
            )}
            {error && <ErrorBox title="승격 실패 — 서버 응답 그대로">{error}</ErrorBox>}
            <div style={sx("display:flex;align-items:center;gap:10px")}>
              <span style={sx("flex:1;font:11px 'Pretendard';color:var(--dim2)")}>
                승격하면 이 코드가 {group.model} 진단 표(error_codes)와 검색 청크에 반영됩니다. 코드 그룹 단위로만 승격합니다.
              </span>
              <ActionButton
                disabled={!canWrite || busy || blockers.length > 0}
                title={!canWrite ? "보전팀장만 승격할 수 있습니다" : blockers[0]}
                onClick={promote}
              >
                {busy ? "승격 중…" : `코드 ${group.code} 승격 (${staged.length}행)`}
              </ActionButton>
            </div>
          </div>
        )
      )}
    </div>
  );
}

function RowCompare({
  role,
  row,
  manualLabel,
  selectedNorm,
  onSelectNorm,
  isPrimary,
  onPrimary,
  canWrite,
  onChanged,
}: {
  role: Role;
  row: ApiOnboardingRow;
  manualLabel: string;
  selectedNorm: number | null;
  onSelectNorm: (nid: number) => void;
  isPrimary: boolean;
  onPrimary: () => void;
  canWrite: boolean;
  onChanged: () => void;
}) {
  const rs = rowStateView(row.state);
  const staged = isRowStaged(row.state);
  const norm = row.norms.find((n) => n.norm_id === selectedNorm) ?? null;
  const [expanded, setExpanded] = useState(false);
  const [rejectNote, setRejectNote] = useState("");
  const [rejectOpen, setRejectOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const LIMIT = 3;
  const n = Math.max(row.causes_en.length, norm?.causes_ko.length ?? 0);
  const shown = expanded ? n : Math.min(n, LIMIT);
  const citations: Citation[] = row.pages.map((p) => ({ manual: manualLabel, page: p }));

  async function reject() {
    setBusy(true);
    setError(null);
    try {
      await rejectOnboardingRow(role, row.row_id, rejectNote);
      onChanged();
    } catch (e) {
      setError(describeError(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={sx("border:1px solid var(--line);border-radius:8px;overflow:hidden;" + (staged ? "" : "opacity:.72"))}>
      <div
        style={sx(
          "display:flex;align-items:center;gap:9px;flex-wrap:wrap;padding:8px 12px;background:var(--head);border-bottom:1px solid var(--line)"
        )}
      >
        <label style={sx("display:flex;align-items:center;gap:5px;font:11.5px 'Pretendard';color:var(--ink2)")}>
          <input type="radio" checked={isPrimary} disabled={!staged || !canWrite} onChange={onPrimary} />
          대표(primary)
        </label>
        <Mono size={12}>{row.display_code}</Mono>
        <span style={sx("font:600 12px 'Pretendard';color:var(--ink2)")}>
          {row.section_ko} <span style={sx("color:var(--dim2);font-weight:400")}>({row.section_en})</span>
        </span>
        <Mono size={10}>row #{row.row_id}</Mono>
        <ToneBadge tone={rs.tone} size={9.5}>
          {rs.label}
        </ToneBadge>
        <Spacer />
        {row.norms.length > 0 ? (
          <label style={sx("display:flex;align-items:center;gap:5px;font:11px 'Pretendard';color:var(--dim)")}>
            정규화
            <select
              value={selectedNorm ?? ""}
              disabled={!staged || !canWrite}
              onChange={(e) => onSelectNorm(Number(e.target.value))}
              style={sx("font:11px 'JetBrains Mono',monospace;padding:2px 4px;background:var(--raise);color:var(--ink2)")}
            >
              {row.norms.map((nm, i) => (
                <option key={nm.norm_id} value={nm.norm_id}>
                  #{nm.norm_id}
                  {i === 0 ? " (최신)" : ""} · {confidenceLabel(nm.confidence)} · {nm.staged_by} · {utcStamp(nm.created_at)}
                </option>
              ))}
            </select>
          </label>
        ) : (
          <Badge tone="unknown" size={9.5}>
            한국어 정규화 없음 — 승격 불가
          </Badge>
        )}
      </div>

      <div style={sx("display:grid;grid-template-columns:64px minmax(0,1fr) minmax(0,1fr)")}>
        <Cell head />
        <Cell head>
          원문 (영문) <span style={sx("color:var(--dim2);font-weight:400")}>· 근거</span>
        </Cell>
        <Cell head>
          한국어 정규화 (AI 초안){" "}
          <span style={sx("color:var(--dim2);font-weight:400")}>· 대조용, 근거 아님</span>
          {norm && (
            <span style={sx(`margin-left:6px;font:700 10px 'Pretendard';color:${confidenceTone(norm.confidence) === "ok" ? "var(--dim)" : "var(--error-tx)"}`)}>
              {confidenceLabel(norm.confidence)}
            </span>
          )}
          {norm?.flags.map((f) => (
            <span key={f} style={sx("margin-left:5px")}>
              <FlagMark tone={flagTone(f)}>{flagLabel(f)}</FlagMark>
            </span>
          ))}
        </Cell>

        <Cell label>명칭</Cell>
        <Cell>
          <span style={sx("font-weight:600")}>{row.name_en}</span>
        </Cell>
        <Cell>{norm ? <span style={sx("font-weight:600")}>{norm.name_ko}</span> : <NoKo />}</Cell>

        {Array.from({ length: shown }, (_, i) => (
          <CausePair key={i} index={i} en={row.causes_en[i]} ko={norm ? norm.causes_ko[i] : undefined} hasNorm={!!norm} />
        ))}

        <Cell label>근거</Cell>
        <Cell>
          <div style={sx("display:flex;gap:5px;flex-wrap:wrap")}>
            {citations.map((c) => (
              <CitationChip key={c.page} citation={c} />
            ))}
          </div>
        </Cell>
        <Cell>
          <span style={sx("font:11px 'Pretendard';color:var(--dim2)")}>번역문에는 인용을 달지 않습니다 (D145)</span>
        </Cell>
      </div>

      {n > LIMIT && (
        <button
          onClick={() => setExpanded((v) => !v)}
          style={sx(
            "width:100%;border:none;border-top:1px solid var(--line);background:var(--panel);cursor:pointer;" +
              "padding:6px;font:11.5px 'Pretendard';color:var(--blue-tx)"
          )}
        >
          {expanded ? "접기" : `원인 ${n - LIMIT}건 더 보기`}
        </button>
      )}

      {staged && (
        <div style={sx("border-top:1px solid var(--line);padding:8px 12px;display:flex;flex-direction:column;gap:6px")}>
          {rejectOpen ? (
            <div style={sx("display:flex;gap:8px;align-items:center")}>
              <input
                value={rejectNote}
                onChange={(e) => setRejectNote(e.target.value)}
                placeholder="반려 사유 (필수)"
                style={sx(
                  "flex:1;font:12px 'Pretendard';padding:6px 8px;border:1px solid var(--line2);border-radius:5px;" +
                    "background:var(--field);color:var(--ink)"
                )}
              />
              <ActionButton variant="outline" disabled={!canWrite || busy} onClick={reject}>
                {busy ? "반려 중…" : "이 행 반려"}
              </ActionButton>
              <ActionButton variant="outline" onClick={() => setRejectOpen(false)}>
                취소
              </ActionButton>
            </div>
          ) : (
            <div style={sx("display:flex;justify-content:flex-end")}>
              <ActionButton
                variant="outline"
                disabled={!canWrite}
                title={canWrite ? undefined : "보전팀장만 반려할 수 있습니다"}
                onClick={() => setRejectOpen(true)}
              >
                행 반려…
              </ActionButton>
            </div>
          )}
          {error && <ErrorBox title="반려 실패 — 서버 응답 그대로">{error}</ErrorBox>}
        </div>
      )}
    </div>
  );
}

function CausePair({
  index,
  en,
  ko,
  hasNorm,
}: {
  index: number;
  en: ApiOnboardingCause | undefined;
  ko: ApiOnboardingCause | undefined;
  hasNorm: boolean;
}) {
  return (
    <>
      <Cell label>원인 {index + 1}</Cell>
      <Cell>{en ? <CauseBody c={en} /> : <span style={sx("color:var(--dim2)")}>(원문 없음)</span>}</Cell>
      <Cell>{ko ? <CauseBody c={ko} /> : hasNorm ? <span style={sx("color:var(--error-tx)")}>⚠ 정규화에 이 원인이 없음</span> : <NoKo />}</Cell>
    </>
  );
}

function CauseBody({ c }: { c: ApiOnboardingCause }) {
  return (
    <div style={sx("display:flex;flex-direction:column;gap:4px")}>
      {c.cause ? <span>{c.cause}</span> : <span style={sx("color:var(--dim2)")}>(원인 칸 비어 있음)</span>}
      {c.solutions.length > 0 && (
        <ul style={sx("margin:0;padding-left:16px;color:var(--ink2)")}>
          {c.solutions.map((s, i) => (
            <li key={i}>
              <span style={sx("color:var(--dim2);font-size:10.5px")}>조치</span> {s}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function NoKo() {
  return <span style={sx("color:var(--dim2);font-style:italic")}>한국어 정규화 없음 — 원문만 있습니다</span>;
}

/* -------------------------------------------------------------------------- */
/* 안전 문구 후보 탭 (D147·D157)                                                   */

function SafetyTab({
  role,
  model,
  canWrite,
  refreshKey,
  onChanged,
}: {
  role: Role;
  model: string;
  canWrite: boolean;
  refreshKey: number;
  onChanged: () => void;
}) {
  const [cands, setCands] = useState<ApiSafetyCandidate[] | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [kind, setKind] = useState("discharge_wait");
  const [selected, setSelected] = useState<number | null>(null);

  useEffect(() => {
    let alive = true;
    getSafetyCandidates(role, model)
      .then((c) => {
        if (!alive) return;
        setCands(c);
        setFailure(null);
      })
      .catch((e: unknown) => alive && setFailure(describeError(e)));
    return () => {
      alive = false;
    };
  }, [role, model, refreshKey]);

  if (failure) return <ErrorBox title="안전 문구 후보를 불러오지 못했습니다">{failure}</ErrorBox>;
  if (!cands) return <Dim pad>불러오는 중…</Dim>;

  const approvedDischarge = approvedDischargeCount(cands);
  const visible = cands.filter((c) => safetyKindMatches(c.kind, kind));
  const failClosed = isDischargeFailClosed(approvedDischarge);
  const current = cands.find((c) => c.cand_id === selected) ?? null;

  return (
    <div style={sx("display:flex;flex-direction:column")}>
      <div
        style={sx(
          "margin:12px 18px 0;display:flex;align-items:center;gap:14px;border:1px solid var(--line);border-radius:7px;" +
            "padding:9px 13px;background:var(--panel)"
        )}
      >
        <span style={sx("font:12px/1.6 'Pretendard';color:var(--ink2);flex:1")}>
          AI(결정적 추출기)가 매뉴얼에서 뽑은 <b>원문 후보</b>입니다. 한국어 안전 문안은 <b>사람이 직접</b> 씁니다 — AI 는
          한국어 안전 문구를 제안하지 않습니다 (D147). 승인은 되돌릴 수 없습니다.
        </span>
        <span
          style={sx(
            "font:700 12px 'JetBrains Mono',monospace;white-space:nowrap;" +
              (failClosed ? "color:var(--error-tx)" : "color:var(--blue-tx)")
          )}
        >
          {failClosed ? "⚠ " : ""}방전 대기 승인 {approvedDischarge} / 1
        </span>
      </div>
      {failClosed && (
        <div style={sx("margin:8px 18px 0")}>
          <ErrorBox title={`방전 대기 승인이 ${approvedDischarge}건 — 이 기종의 절차 안내가 차단(fail-closed)되어 있습니다`}>
            기종당 1건이어야 합니다(D157). 2건 이상이면 서버가 어느 문구를 쓸지 고르지 않고 안전 문구를 비워 절차 안내를
            막습니다. 승인 취소 API 는 없으므로 DB 수동 조치 절차로 1건만 남기십시오.
          </ErrorBox>
        </div>
      )}
      <div style={sx("display:grid;grid-template-columns:360px minmax(0,1fr);min-height:640px")}>
        <div style={sx("border-right:1px solid var(--line);display:flex;flex-direction:column")}>
          <div style={sx("padding:12px 12px 8px")}>
            <FilterRow label="종류">
              {SAFETY_KIND_FILTERS.map((f) => (
                <FilterChip key={f.key} on={kind === f.key} onClick={() => setKind(f.key)}>
                  {f.label}
                </FilterChip>
              ))}
            </FilterRow>
            <span style={sx("display:block;margin-top:7px;font:10px 'JetBrains Mono',monospace;color:var(--dim2)")}>
              후보 {visible.length} / {cands.length}
            </span>
          </div>
          <div style={sx("flex:1;overflow-y:auto;max-height:760px;padding:0 10px 12px;display:flex;flex-direction:column;gap:6px")}>
            {visible.length === 0 && <Dim>이 종류의 후보가 없습니다.</Dim>}
            {visible.map((c) => {
              const sv = safetyStateView(c.state);
              return (
                <button
                  key={c.cand_id}
                  onClick={() => setSelected(c.cand_id)}
                  style={sx(
                    "text-align:left;cursor:pointer;border-radius:7px;padding:8px 10px;display:flex;flex-direction:column;gap:4px;color:var(--ink);" +
                      (c.cand_id === selected
                        ? "border:2px solid var(--blue);background:var(--sel)"
                        : "border:1px solid var(--line);background:var(--surface)")
                  )}
                >
                  <div style={sx("display:flex;align-items:center;gap:6px")}>
                    <Mono size={11}>SC-{c.cand_id}</Mono>
                    <Badge tone="neutral" size={8.5}>
                      {safetyKindLabel(c.kind)}
                    </Badge>
                    <ToneBadge tone={sv.tone} size={8.5}>
                      {sv.label}
                    </ToneBadge>
                    <span style={sx("flex:1")} />
                    <Mono size={10}>p.{c.page}</Mono>
                  </div>
                  <span
                    style={sx(
                      "font:10.5px/1.45 'JetBrains Mono',monospace;color:var(--dim);display:-webkit-box;" +
                        "-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden"
                    )}
                  >
                    {c.quote_en}
                  </span>
                  <span style={sx("font:10.5px 'Pretendard';color:var(--dim2)")}>
                    원문 수치 {c.wait_minutes_in_text === null ? "없음" : `${c.wait_minutes_in_text} minutes`}
                  </span>
                </button>
              );
            })}
          </div>
        </div>
        <div style={sx("padding:16px 18px;min-width:0")}>
          {current ? (
            <SafetyDetail
              key={current.cand_id}
              role={role}
              model={model}
              cand={current}
              approvedDischarge={findApprovedDischarge(cands)}
              canWrite={canWrite}
              onChanged={onChanged}
            />
          ) : (
            <Dim>왼쪽에서 안전 문구 후보를 고르십시오.</Dim>
          )}
        </div>
      </div>
    </div>
  );
}

function SafetyDetail({
  role,
  model,
  cand,
  approvedDischarge,
  canWrite,
  onChanged,
}: {
  role: Role;
  model: string;
  cand: ApiSafetyCandidate;
  approvedDischarge: ApiSafetyCandidate | null;
  canWrite: boolean;
  onChanged: () => void;
}) {
  const sv = safetyStateView(cand.state);
  const staged = isCandidateStaged(cand.state);
  // D147 — **빈 칸에서 시작한다.** 정규화문·원문 번역을 미리 채우지 않는다.
  const [text, setText] = useState("");
  const [reviewed, setReviewed] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [rejectNote, setRejectNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  const manual = `${model} 매뉴얼`;
  const citation: Citation = { manual, page: cand.page };
  const precheck = text.trim() ? safetyTextPrecheck(text, cand.wait_minutes_in_text) : null;

  async function approve() {
    setBusy(true);
    setError(null);
    try {
      await approveSafetyCandidate(role, cand.cand_id, text, reviewed);
      setDone("승인했습니다 — 되돌릴 수 없습니다.");
      onChanged();
    } catch (e) {
      setError(describeError(e));
    } finally {
      setBusy(false);
      setConfirming(false);
    }
  }

  async function reject() {
    setBusy(true);
    setError(null);
    try {
      await rejectSafetyCandidate(role, cand.cand_id, rejectNote);
      setDone("반려했습니다.");
      onChanged();
    } catch (e) {
      setError(describeError(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={sx("display:grid;grid-template-columns:minmax(0,1fr) 360px;gap:18px")}>
      <div style={sx("display:flex;flex-direction:column;gap:12px;min-width:0")}>
        <div style={sx("display:flex;align-items:center;gap:8px;flex-wrap:wrap")}>
          <span style={sx("font:800 18px 'JetBrains Mono',monospace;color:var(--ink)")}>SC-{cand.cand_id}</span>
          <Badge tone="neutral" size={10}>
            {safetyKindLabel(cand.kind)}
          </Badge>
          <ToneBadge tone={sv.tone} size={10}>
            {sv.label}
          </ToneBadge>
          <Spacer />
          <CitationChip citation={citation} />
          {cand.also_pages.map((p) => (
            <CitationChip key={p} citation={{ manual, page: p }} />
          ))}
        </div>

        <div style={sx("border:1px solid var(--line);border-radius:7px;background:var(--panel);padding:10px 13px")}>
          <div style={sx("font:10px 'JetBrains Mono',monospace;letter-spacing:.06em;color:var(--dim2);margin-bottom:5px")}>
            원문 발췌 (영문) · 근거
          </div>
          <div style={sx("font:12px/1.65 'JetBrains Mono',monospace;color:var(--ink);white-space:pre-wrap")}>
            {cand.quote_en}
          </div>
        </div>

        <div style={sx("display:flex;align-items:center;gap:10px;font:12px 'Pretendard';color:var(--ink2)")}>
          <Badge tone="neutral" size={10}>
            수치 대조
          </Badge>
          원문 대기시간{" "}
          {cand.wait_minutes_in_text === null ? (
            <b>명시 없음</b>
          ) : (
            <span
              style={sx(
                "font:800 14px 'JetBrains Mono',monospace;color:var(--ink);border:1.5px solid var(--ink);border-radius:4px;padding:1px 6px"
              )}
            >
              {cand.wait_minutes_in_text} minutes
            </span>
          )}
          <span style={sx("color:var(--dim2);font-size:11px")}>
            {cand.wait_minutes_in_text === null
              ? "— 문안에 「N분」 숫자를 넣으면 서버가 거부합니다(number_not_in_source)"
              : `— 문안에 「${cand.wait_minutes_in_text}분」 을 그대로 쓰고 다른 값을 붙이지 마십시오(wait_value_mismatch)`}
          </span>
        </div>

        {staged ? (
          <div style={sx("display:flex;flex-direction:column;gap:8px")}>
            {isDischargeWait(cand.kind) && approvedDischarge && (
              <div style={sx("font:11.5px/1.6 'Pretendard';color:var(--dim)")}>
                이 기종에는 이미 승인된 방전 대기 문구가 있습니다(SC-{approvedDischarge.cand_id}). 기종당 1건이라(D157) 서버가
                거부합니다.
              </div>
            )}
            <label style={sx("font:700 11.5px 'Pretendard';color:var(--ink2)")}>
              한국어 안전 문안 — 사람이 직접 작성
            </label>
            <textarea
              value={text}
              onChange={(e) => {
                setText(e.target.value);
                // 대조한 뒤 문안을 바꿨다면 그 대조는 더 이상 이 문안에 대한 것이 아니다 (D147).
                setReviewed(false);
              }}
              disabled={!canWrite}
              rows={4}
              placeholder="원문을 읽고 직접 작성하십시오. (AI 번역·정규화문을 붙여 넣지 마십시오 — D147)"
              style={sx(
                "font:13px/1.6 'Pretendard';padding:8px 10px;border:1px solid var(--line2);border-radius:6px;" +
                  "background:var(--field);color:var(--ink);resize:vertical"
              )}
            />
            {precheck && (
              <div style={sx("font:11.5px/1.6 'Pretendard';color:var(--error-tx)")}>
                ⚠ 사전 경고(참고용 — 최종 판정은 서버): {precheck}
              </div>
            )}
            <label style={sx("display:flex;align-items:center;gap:7px;font:12px 'Pretendard';color:var(--ink2)")}>
              <input type="checkbox" checked={reviewed} disabled={!canWrite} onChange={(e) => setReviewed(e.target.checked)} />
              원문(p.{cand.page})과 대조했다
            </label>
            {error && <ErrorBox title="서버 응답 그대로">{error}</ErrorBox>}
            {done && <Dim>{done}</Dim>}
            <div style={sx("display:flex;gap:8px;justify-content:flex-end;align-items:center")}>
              <input
                value={rejectNote}
                onChange={(e) => setRejectNote(e.target.value)}
                disabled={!canWrite}
                placeholder="반려 사유 (반려 시 필수)"
                style={sx(
                  "flex:1;max-width:280px;font:12px 'Pretendard';padding:6px 8px;border:1px solid var(--line2);" +
                    "border-radius:5px;background:var(--field);color:var(--ink)"
                )}
              />
              <ActionButton variant="outline" disabled={!canWrite || busy} onClick={reject}>
                반려
              </ActionButton>
              <ActionButton
                disabled={!canWrite || busy || !text.trim() || !reviewed}
                title={
                  !canWrite
                    ? "보전팀장만 승인할 수 있습니다"
                    : !text.trim()
                      ? "문안을 입력하십시오"
                      : !reviewed
                        ? "「원문과 대조했다」를 체크하십시오"
                        : undefined
                }
                onClick={() => setConfirming(true)}
              >
                승인…
              </ActionButton>
            </div>
          </div>
        ) : (
          <div
            style={sx(
              "border:1px solid var(--line);border-radius:7px;padding:10px 13px;font:12px/1.7 'Pretendard';color:var(--ink2)"
            )}
          >
            {cand.approved_text ? (
              <>
                <b>승인 문안</b>: {cand.approved_text}
                <br />
                <span style={sx("color:var(--dim)")}>
                  승인 {cand.approved_by ?? "—"} · {utcStamp(cand.approved_at)} · 원문 대조 {utcStamp(cand.text_reviewed_at)} ·
                  되돌리기 없음
                </span>
              </>
            ) : (
              <span style={sx("color:var(--dim)")}>검수가 끝난 후보입니다 ({sv.label}).</span>
            )}
          </div>
        )}
      </div>

      <div style={sx("display:flex;flex-direction:column;gap:8px")}>
        <div style={sx("font:10px 'JetBrains Mono',monospace;letter-spacing:.06em;color:var(--dim2)")}>승인 시 적용되는 곳</div>
        <div style={sx("font:11px 'Pretendard';color:var(--dim)")}>
          정비사 진단 콘솔 · {model} 점검·교체 절차 응답의 안전 경고 블록 (D157)
        </div>
        <div style={sx("border:1px solid var(--line);border-radius:8px;padding:12px;display:flex;flex-direction:column")}>
          {(staged ? text.trim() : cand.approved_text) ? (
            <SafetyBlock title="SAFETY · 미리보기" citation={citation}>
              {staged ? text : cand.approved_text}
            </SafetyBlock>
          ) : (
            <Dim>문안을 입력하면 여기에 그대로 보입니다.</Dim>
          )}
        </div>
      </div>

      {confirming && (
        <div
          role="dialog"
          aria-modal="true"
          style={sx(
            "position:fixed;inset:0;z-index:50;background:rgba(0,0,0,.45);display:flex;align-items:center;justify-content:center"
          )}
        >
          <div
            style={sx(
              "width:480px;max-width:92vw;background:var(--surface);border:1px solid var(--line);border-radius:10px;" +
                "padding:18px 20px;display:flex;flex-direction:column;gap:12px;box-shadow:0 20px 60px rgba(0,0,0,.4)"
            )}
          >
            <b style={sx("font:700 15px 'Pretendard';color:var(--ink)")}>승인하면 되돌릴 수 없습니다</b>
            <span style={sx("font:12.5px/1.7 'Pretendard';color:var(--ink2)")}>
              이 문안이 {model} 점검·교체 절차 응답의 안전 경고로 그대로 쓰입니다. 원문 p.{cand.page} 와 대조했는지 다시
              확인하십시오. 승인 취소 API 는 없습니다.
            </span>
            <div
              style={sx(
                "border:1px solid var(--line);border-radius:6px;padding:8px 10px;font:12.5px/1.6 'Pretendard';color:var(--ink);background:var(--panel)"
              )}
            >
              {text}
            </div>
            <div style={sx("display:flex;gap:8px;justify-content:flex-end")}>
              <ActionButton variant="outline" onClick={() => setConfirming(false)}>
                취소
              </ActionButton>
              <ActionButton disabled={busy || !reviewed} onClick={approve}>
                {busy ? "승인 중…" : "승인 확정"}
              </ActionButton>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* 조각                                                                          */

function describeError(e: unknown): string {
  if (e instanceof ApiError) return onboardingErrorText(e.status, errorBody(e), e.body);
  return "백엔드에 연결하지 못했습니다.";
}

/** 온보딩 톤 → 배지 프리미티브 톤. 색 결정은 `Badge` 프리미티브 한 곳이다. */
const TONE_BADGE: Record<OnboardingTone, BadgeTone> = {
  ok: "ok",
  info: "blue",
  neutral: "neutral",
  caution: "neutral",
  security: "neutral",
  unknown: "unknown",
};

function ToneBadge({ tone, size, children }: { tone: OnboardingTone; size?: number; children: React.ReactNode }) {
  return (
    <Badge tone={TONE_BADGE[tone]} size={size}>
      {children}
    </Badge>
  );
}

/** 목록·헤더의 작은 플래그 표식. 보안(주입 의심)은 잉크색 반전 — **오렌지 아님**. */
function FlagMark({ tone, children }: { tone: OnboardingTone; children: React.ReactNode }) {
  const skin =
    tone === "security"
      ? "color:var(--surface);background:var(--ink);border:1px solid var(--ink)"
      : tone === "caution"
        ? "color:var(--dim);background:transparent;border:1px dashed var(--line2)"
        : tone === "unknown"
          ? "color:var(--error-tx);background:transparent;border:1px dashed var(--error-tx)"
          : "color:var(--dim);background:var(--raise);border:1px solid var(--line2)";
  return (
    <span style={sx(`font:700 8.5px 'JetBrains Mono',monospace;border-radius:3px;padding:1px 5px;white-space:nowrap;${skin}`)}>
      {children}
    </span>
  );
}

/** 플래그 배너 — 보안(잉크 2px 테두리 + 반전 아이콘 칸) / 주의(회색 점선). */
function FlagBanner({ flag }: { flag: string }) {
  const tone = flagTone(flag);
  if (tone === "security") {
    return (
      <div style={sx("display:flex;border:2px solid var(--ink);border-radius:7px;overflow:hidden")}>
        <div
          style={sx(
            "width:44px;flex-shrink:0;background:var(--ink);color:var(--surface);display:flex;align-items:center;justify-content:center;font-size:18px"
          )}
        >
          ⛨
        </div>
        <div style={sx("padding:8px 12px;font:12px/1.6 'Pretendard';color:var(--ink2)")}>
          <FlagMark tone="security">보안</FlagMark> <b>{flagLabel(flag)}</b> <Mono size={10.5}>{flag}</Mono>
          <br />
          {flagHint(flag)}. 원문 PDF 를 직접 열어 문장 출처를 확인하십시오.
        </div>
      </div>
    );
  }
  return (
    <div
      style={sx(
        "border:1px dashed " +
          (tone === "unknown" ? "var(--error-tx)" : "var(--line2)") +
          ";border-radius:7px;padding:8px 12px;font:12px/1.6 'Pretendard';color:var(--ink2)"
      )}
    >
      <FlagMark tone={tone}>{tone === "unknown" ? "미상" : "주의"}</FlagMark> <b>{flagLabel(flag)}</b>{" "}
      <Mono size={10.5}>{flag}</Mono> — {flagHint(flag)}
    </div>
  );
}

function Cell({ children, head = false, label = false }: { children?: React.ReactNode; head?: boolean; label?: boolean }) {
  const base = "padding:8px 11px;border-bottom:1px solid var(--line);font:12.5px/1.6 'Pretendard';color:var(--ink);min-width:0;";
  if (head) return <div style={sx(base + "background:var(--panel);font-weight:700;font-size:11.5px;color:var(--ink2)")}>{children}</div>;
  if (label) return <div style={sx(base + "font-size:11px;font-weight:700;color:var(--dim)")}>{children}</div>;
  return <div style={sx(base + "border-left:1px solid var(--line);overflow-wrap:anywhere")}>{children}</div>;
}

function ActionButton({
  children,
  onClick,
  disabled = false,
  variant = "primary",
  title,
}: {
  children: React.ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  variant?: "primary" | "outline";
  title?: string;
}) {
  const skin =
    variant === "primary"
      ? "border:none;background:var(--blue);color:#fff"
      : "border:1px solid var(--line2);background:transparent;color:var(--ink2)";
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      title={title}
      style={sx(
        `border-radius:6px;font:600 12px 'Pretendard';padding:8px 15px;white-space:nowrap;${skin};` +
          (disabled ? "opacity:.45;cursor:not-allowed" : "cursor:pointer")
      )}
    >
      {children}
    </button>
  );
}

function TabButton({ on, onClick, children }: { on: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      style={sx(
        "border:none;background:transparent;cursor:pointer;padding:9px 14px;font:600 12.5px 'Pretendard';" +
          (on ? "color:var(--ink);border-bottom:2px solid var(--blue)" : "color:var(--dim);border-bottom:2px solid transparent")
      )}
    >
      {children}
    </button>
  );
}

function FilterRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={sx("display:flex;align-items:center;gap:5px;flex-wrap:wrap")}>
      <span style={sx("width:36px;font:11px 'Pretendard';color:var(--dim)")}>{label}</span>
      {children}
    </div>
  );
}

function FilterChip({ on, onClick, children }: { on: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      style={sx(
        "cursor:pointer;border-radius:4px;padding:3px 8px;font:600 11px 'Pretendard';" +
          (on ? "border:1px solid var(--blue);background:var(--blue);color:#fff" : "border:1px solid var(--line2);background:transparent;color:var(--ink2)")
      )}
    >
      {children}
    </button>
  );
}

function Swatch({ color }: { color: string }) {
  return <span style={sx(`display:inline-block;width:8px;height:8px;border-radius:2px;background:${color};border:1px solid var(--line2)`)} />;
}

function Dim({ children, pad = false }: { children: React.ReactNode; pad?: boolean }) {
  return <div style={sx(`font:12px/1.6 'Pretendard';color:var(--dim);${pad ? "padding:16px 18px" : ""}`)}>{children}</div>;
}

function ErrorBox({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div
      style={sx(
        "border:1.5px dashed var(--error-tx);border-radius:6px;padding:8px 10px;margin:4px 0;" +
          "font:11.5px/1.6 'Pretendard';color:var(--error-tx)"
      )}
    >
      <b>{title}</b>
      <br />
      {children}
    </div>
  );
}
