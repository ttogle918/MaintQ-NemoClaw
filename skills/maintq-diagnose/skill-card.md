## Description: <br>
인버터 에러코드 진단부터 재고 확인·공급사 견적·발주 초안까지 MaintQ MCP 도구(maintq__*)로 순서대로 처리하며, 매뉴얼에 없는 코드는 추측하지 않고 A/S 로 넘긴다. <br>

This skill is for demonstration purposes and not for production usage. <br>

## Third-Party Community Consideration
<span style="color:#d73a49">This skill is not owned or developed by NVIDIA. This skill has been developed and built to a third-party's requirements for this application and use case; see link to Non-NVIDIA [MaintQ (ttogle918/MaintQ-NemoClaw) Agent Card](https://github.com/ttogle918/MaintQ-NemoClaw/blob/main/skills/maintq-diagnose/skill-card.md).</span> <!-- VERIFY: frontmatter metadata.author 'MaintQ' and git remote; no formal owner record --> <br>

### License/Terms of Use: <br>
Apache 2.0 <br>
## Use Case: <br>
External users — factory maintenance technicians — use it to turn an inverter fault report (error code or part-replacement request) into a manual-grounded diagnosis, stock and supplier-quote comparison, and a purchase-order draft that a human approves. <br>

### Deployment Geography for Use: <br>
Global <br>

## Requirements / Dependencies: <br>
**Requires API Key or External Credential:** [Not Specified] <br>
**Credential Type(s):** [None identified] <br>  

Do not include secrets in prompts/logs/output; use least-privilege credentials; rotate keys as appropriate. See skill body for more details. <br>

## Known Risks and Mitigations: <br>
Risk: Review before execution as proposals could introduce incorrect or misleading guidance into skills. <br>
Mitigation: Review and scan skill before deployment. <br>

## Reference(s): <br>
- [evals/evals.json](evals/evals.json) <br>
- [MaintQ scenarios S1–S4](../../docs/02_SCENARIOS.md) <br>
- [MaintQ MCP tool contracts](../../docs/04_MCP_TOOLS.md) <br>


## Skill Output: <br>
**Output Type(s):** [Analysis, API Calls] <br>
**Output Format:** [Markdown (Korean)] <br>
**Output Parameters:** [1D] <br>
**Other Properties Related to Output:** [Purchase orders are written only as drafts (INSERT); state transitions require a human API.] <br>

## Evaluation Agents Used: <br>
- OpenClaw on NemoClaw (`nvidia/nemotron-3-super-120b-a12b`) <br>



## Evaluation Tasks: <br>
3 of the 4 cases in evals/evals.json run once each in the NemoClaw sandbox on 2026-09-24 (S1 two turns, S4, missing-model); S2 not yet run. <br>

## Evaluation Metrics Used: <br>
Reported benchmark dimensions: <br>
- Hallucination avoidance: Unknown codes return not_found without guessed codes, causes or actions. <br>
- Grounding: Cited manual pages appear in tool results; safety text matches the approved baseline verbatim. <br>
- Human-in-the-loop: No PO draft in the quote turn; draft only after user selection. <br>

Underlying evaluation signals used in this run: <br>
- `tool_sequence`: Tool calls extracted from exported OpenClaw session JSONL. <br>
- `db_state`: Resulting po_drafts row has state=draft. <br>



## Evaluation Results: <br>
| Case | Result | Evidence |
|---|---|---|
| S1 turn 1 (iG5A OHt) | Pass | lookup → history → rag → inventory → quotes; no PO call; pages 202/43/205 found in tool results; safety text verbatim |
| S1 turn 2 (supplier chosen) | Pass | PO-0122 created, state=draft |
| S4 (iG5A XY9) | Pass | lookup returned not_found; no guessed code or cause |
| Missing model (OCt) | Pass | asked for model before any tool call |
| S2 (S100 control board) | Not run | — |

## Skill Version(s): <br>
c53bb02 (source: git SHA, committed 2026-09-24) <br>


