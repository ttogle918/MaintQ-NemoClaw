"use client";

import { useRouter } from "next/navigation";
import { MANAGER_IDENTITIES, ROLE_HOME, ROLE_USER_NAME, setManagerIdentity } from "@/lib/role";
import { sx } from "@/lib/sx";

/**
 * 진입 화면 — "누구로 볼까요?" 계정 선택.
 *
 * **진짜 로그인이 아니다** (D23·D38·D52) — 사용자 요청으로 "계정마다 다른 페이지"를
 * 체감할 수 있게 만든 시뮬레이션 신원 선택 화면이다. 고르면 매니저 신원은
 * `setManagerIdentity()`(localStorage)로 저장하고 각자의 랜딩 페이지로 보낸다.
 * 권한 경계(재무 승인 버튼 등)는 이 화면이 만드는 게 아니다 — 여전히 라우트(role)와
 * 백엔드 department 체크(D119)가 실제로 막는다. 이 화면은 "그 신원으로 들어간 것처럼
 * 보이게" 안내할 뿐이다.
 */
export default function EntryPage() {
  const router = useRouter();

  function enterAsTechnician() {
    router.push(ROLE_HOME.technician);
  }

  function enterAsManager(userId: string, destination: string) {
    setManagerIdentity(userId);
    router.push(destination);
  }

  return (
    <div
      style={sx(
        "min-height:100vh;display:flex;align-items:center;justify-content:center;" +
          "background:var(--page);padding:24px"
      )}
    >
      <div style={sx("width:100%;max-width:420px;display:flex;flex-direction:column;gap:20px")}>
        <div style={sx("text-align:center")}>
          <div style={sx("font:800 20px 'Pretendard';color:var(--ink,#161A21)")}>MaintQ</div>
          <div style={sx("font:13px 'Pretendard';color:var(--dim,#545F6E);margin-top:6px")}>
            누구로 볼까요?
          </div>
        </div>

        <div style={sx("display:flex;flex-direction:column;gap:10px")}>
          <PersonaButton
            icon="🔧"
            label={`정비사 · ${ROLE_USER_NAME.technician}`}
            sub="설비 진단 → 부품 발주"
            onClick={enterAsTechnician}
          />
          {MANAGER_IDENTITIES.map((identity) => (
            <PersonaButton
              key={identity.userId}
              icon={identity.department === "finance" ? "💰" : "🗂"}
              label={identity.label}
              sub={identity.department === "finance" ? "발주 재무 승인 · 자금집행" : "발주 1차 승인 · 처분·수리 서명"}
              onClick={() =>
                enterAsManager(
                  identity.userId,
                  identity.department === "finance" ? "/manager/finance" : "/manager"
                )
              }
            />
          ))}
        </div>

        <div style={sx("text-align:center;font:11px 'Pretendard';color:var(--dim2,#838EA0)")}>
          실제 로그인이 아닙니다 — 시연용 신원 선택 화면입니다.
        </div>
      </div>
    </div>
  );
}

function PersonaButton({
  icon,
  label,
  sub,
  onClick,
}: {
  icon: string;
  label: string;
  sub: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={sx(
        "display:flex;align-items:center;gap:14px;width:100%;text-align:left;" +
          "border:1px solid var(--line,#DBE0E7);border-radius:12px;background:var(--panel,#FFFFFF);" +
          "padding:16px 18px;cursor:pointer;transition:border-color .15s,box-shadow .15s"
      )}
    >
      <span style={sx("font-size:26px")}>{icon}</span>
      <span style={sx("display:flex;flex-direction:column;gap:2px")}>
        <span style={sx("font:700 14px 'Pretendard';color:var(--ink,#161A21)")}>{label}</span>
        <span style={sx("font:12px 'Pretendard';color:var(--dim,#545F6E)")}>{sub}</span>
      </span>
    </button>
  );
}
