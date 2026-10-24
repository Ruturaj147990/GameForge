# GameForge IDE Security Review

**Updated:** 2026-10-24T18:15:45+05:30  
**Scope:** Native desktop agent tool gateway, local bridge, prompt/context handling, and edit lifecycle. Review informed by OWASP GenAI LLM Top 10 2026 and OWASP Prompt Injection guidance.

| Area | Status | Implemented control | Residual risk |
|---|---|---|---|
| Path traversal | PASS | `BoundaryManager` resolves paths under the selected workspace and blocks protected writes. | Symlink/reparse-point behavior relies on Windows path resolution; no OS sandbox is claimed. |
| Protected oracles | PASS | Writes to `graders/protected` and `.git` are blocked by the boundary; protected suite is unchanged. | Read access is intentionally available to local developers; the product agent must not be given hidden-oracle context. |
| Agent commands | PASS | `TerminalTools` uses shell-free argv execution, rejects chaining/redirection/interpolation, restricts executables, validates working directory, and limits timeout to 300 seconds. `ToolGateway` applies approval policy for every caller. | Allowlisted programs can still modify the workspace after explicit user approval; this is not capability isolation. |
| Approval | PASS | `ToolGateway` blocks approval-marked tools unless the caller explicitly grants approval. Diff apply/rollback and staged build buttons use the approved path; model JSON and the general API tool endpoint do not. | Agent command execution has no general approval dialog and remains unavailable to the agent. |
| Edit integrity | PASS | Diff records bind original/new SHA-256 byte digests. Apply and rollback reject stale files; writes are atomic. | Review state is memory-resident, so pending diffs do not survive restart. |
| Embedded terminal | DISCLOSED | Terminal is a direct user-controlled PowerShell, separate from agent tools. | It is not an OS sandbox and must not be described as one. |
| Secrets and egress | PARTIAL | Remote adapter reads only named environment variables and remote calls remain disabled without authorization. | Credential Manager integration, TLS configuration, audit export, and hosted-service authorization remain future work. |
| Unreal bridge exposure | PARTIAL PASS | `--serve` rejects non-loopback hosts; context GET/POST require a shared bearer token from `GAMEFORGE_BRIDGE_TOKEN`; comparison is constant-time; plugin reads the same inherited environment variable; context fields are typed, length-bounded and atomically persisted; prompt labels this data untrusted. | Other processes under the same user may read/inherit the environment token; this is not OS process isolation. HTTPS is not used on loopback; plugin request timeout and token rotation are not implemented. |
| Prompt fidelity | PASS | Composer now checks whitespace-only input without trimming the payload sent to the agent. | Full long-context, attachment, and prompt-injection matrix remains unverified. |
| Context budget | PARTIAL | Whole-message history selection, full active-prompt pinning, estimated budget reporting, and explicit over-budget error; older messages are omitted rather than clipped. | Token estimate is UTF-8 bytes/3, not tokenizer usage; no tokenizer parity validation or indirect-injection defense is implemented. |
| Prompt injection / untrusted project data | OPEN | Tool authorization is enforced in code, independent of model instruction following. | Source/docs/log content has no provenance labels or injection-resistant tool policy; do not treat model refusal or system prompt secrecy as a security boundary. |
| Hosted inference | NOT IMPLEMENTED | Future topology is documented separately. | No authenticated service, tenant isolation, rate limits, TLS ingress, quota accounting, or operational controls exist. |

## Regression evidence

- Latest full suite after bridge authentication: **195 passed in 17.82s** (2 upstream deprecation warnings); protected graders: **45 passed in 0.06s**. API tests verify unset-token 503, missing/wrong-token 401, and authorized POST/GET. A disposable UE 5.7.4 editor command completed authenticated POST through the live backend and persisted project/version context. Same-user environment visibility, lack of request timeout/token rotation, and no OS-level process isolation remain residual risks.
- `tests/unit/test_ide_api.py -k bridge_server_host_is_loopback_only`: **1 passed**.
- `graders/protected/`: **45 passed** on 2026-10-24.
- New regressions cover shell chaining rejection, workspace escape rejection, shell-free allowlisted execution, stale apply/rollback rejection, gateway approval enforcement, loopback-only binding, and exact composer payload preservation.

## External guidance reviewed

- OWASP GenAI LLM Top 10 2026 is the current edition reported by OWASP at review time; its risk coverage informed the prompt-injection, agency, authorization, and hosted-service gaps below: [OWASP GenAI LLM Top 10 2026](https://genai.owasp.org/resource/owasp-genai-llm-top-10-2026/).
- OWASP describes prompt injection as untrusted input influencing model behavior and notes possible unauthorized actions or data disclosure: [Prompt Injection glossary](https://genai.owasp.org/glossary/prompt-injection/).

This is an engineering review, not a penetration test or independent security certification. No OS-level isolation is claimed.
