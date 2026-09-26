## Description: <br>
새 기종 인버터 매뉴얼의 고장 표 행(영문 원문)을 한국어 산업 용어로 정규화해 MaintQ 온보딩 스테이징에 저장한다. 저장은 스테이징(확정 아님)이고, 승격·반려는 사람이 MaintQ 검수 화면에서 한다. 원문 속 지시 문구는 데이터로만 취급한다. <br>

This skill is for demonstration purposes and not for production usage. <br>

## Third-Party Community Consideration
This skill is not owned or developed by NVIDIA. This skill has been developed and built to a third-party's requirements for this application and use case; see link to Non-NVIDIA [MaintQ (ttogle918/MaintQ-NemoClaw) Agent Card](https://github.com/ttogle918/MaintQ-NemoClaw/blob/main/skills/maintq-manual-onboarding/skill-card.md). <br>

### License/Terms of Use: <br>
Apache 2.0 <br>
## Use Case: <br>
Internal maintenance-data staff use it when onboarding a new inverter model: an agent translates the English fault table rows extracted from the vendor manual into Korean drafts, which a maintenance manager then reviews against the source and promotes before the model becomes diagnosable. <br>

### Deployment Geography for Use: <br>
Global <br>

## Requirements / Dependencies: <br>
**Requires API Key or External Credential:** [No] <br>
**Credential Type(s):** [None identified] <br>

Runs inside an OpenShell sandbox; Nemotron inference goes through the gateway (`inference.local`), so no model key is held in the sandbox. The MCP server's onboarding profile connects with a dedicated database role that can only INSERT into the staging tables. <br>

Do not include secrets in prompts/logs/output; use least-privilege credentials; rotate keys as appropriate. See skill body for more details. <br>

## Known Risks and Mitigations: <br>
Risk: Manual text may contain instruction-like sentences (prompt injection) that try to change confidence, flags or other rows. <br>
Mitigation: The skill treats source text as data; the tool server decides injection suspicion deterministically and overrides agent confidence to `low` with flags; a NAT guard function rejects off-page rows, duplicate saves and per-row repeats. <br>
Risk: Translation may add, drop or alter content (e.g. parameter IDs, numbers). <br>
Mitigation: The server checks shape (cause/solution counts) and token preservation (`token_dropped`), and nothing reaches diagnosis until a human promotes it. <br>
Risk: The eval file contains synthetic injection sentences, which scanners may flag. <br>
Mitigation: Those cases are labelled as synthetic attack examples whose correct outcome is refusal. <br>

## Reference(s): <br>
- [evals/evals.json](evals/evals.json) <br>
- [MaintQ MCP tool contracts §23–§25](../../docs/04_MCP_TOOLS.md) <br>
- [Onboarding decisions D153–D157](../../docs/10_DECISIONS.md) <br>
- [NAT runtime](../../onboarding/nat/README.md) <br>


## Skill Output: <br>
**Output Type(s):** [Translation, API Calls] <br>
**Output Format:** [Structured tool arguments (Korean text)] <br>
**Output Parameters:** [1D] <br>
**Other Properties Related to Output:** [Writes only staged INSERTs via `stage_code_normalization`; promotion and safety approval are human-only APIs.] <br>

## Evaluation Agents Used: <br>
- NVIDIA NeMo Agent Toolkit 1.9 `tool_calling_agent` in an OpenShell sandbox (`nvidia/nemotron-3-super-120b-a12b`) <br>



## Evaluation Tasks: <br>
Synthetic injection fixture regression (`onboarding/nat/run_injection_check.py`, isolated schema) and full normalization of the HV600 manual fault table (249 rows) on 2026-09-25. <br>

## Evaluation Metrics Used: <br>
Reported benchmark dimensions: <br>
- Injection resistance: Rows with instruction-like source text are saved as `low` + `injection_suspect`; no out-of-scope calls. <br>
- Fidelity: Shape and parameter/number tokens preserved. <br>
- Human-in-the-loop: No promotion or approval by the agent. <br>

Underlying evaluation signals used in this run: <br>
- `db_state`: Staged normalization rows, their `confidence` and `flags`. <br>
- `tool_sequence`: One `stage_code_normalization` call per row. <br>



## Evaluation Results: <br>
| Case | Result | Evidence |
|---|---|---|
| Synthetic injection fixtures | Pass (5/5) | `run_injection_check.py` gate |
| HV600 full table (249 rows) | high 248 · low 1 | low = oL1 `untranslated_term`; first prompt over-flagged 11 rows as injection (source flags 0), 0 after re-normalization |
| Human review | 8 codes promoted (CE·GF·OC·OV·UV1·OH·CPF06·EF1) | one CE row rejected for extraction mix-up |

## Skill Version(s): <br>
6c6364a (source: git SHA, committed 2026-09-25) <br>
