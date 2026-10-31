# Future GameForge-Hosted Inference Architecture

**Status:** Design only. No service, deployment, GPU reservation, or hosted endpoint exists.

## Separation of responsibilities

- The Windows IDE keeps filesystem, Git, terminal, Unreal build, approvals, and project context local.
- A provider adapter implements a documented OpenAI-compatible chat/streaming contract and maps server tool-call deltas to GameForge's provider-neutral response model. Local tools execute only on the client after local schema and permission checks.
- The hosted service is inference-only. It must never accept arbitrary local tool execution requests or assume a model/API key is an authorization boundary for tools.

## Proposed service boundaries

1. TLS ingress/API gateway for authenticated clients, request-size enforcement, request IDs, per-account rate limits, concurrency and bounded queues.
2. Inference API with `/v1/models`, streaming chat, cancellation propagation, strict event sequencing, model/version routing, timeout/error normalization, and health/readiness surfaces.
3. GPU serving workers behind an internal scheduler; model storage is read-only to request workers and deployments use immutable model/version identifiers.
4. Separate administration plane for tenant/key lifecycle, model rollout, quota policy, and operational metrics. Admin endpoints are not exposed on the inference listener.
5. Usage ledger records account/model/request ID, token counts where available, latency, and outcome. Prompt/source content is excluded from logs by default.

## Security and reliability requirements

- Short-lived client credentials or rotatable API keys, TLS at every external boundary, secret-manager integration, key revocation, abuse limits, and tenant-scoped authorization.
- Input/output byte and token limits, bounded concurrency, queue deadlines, backpressure, cancellation, per-request isolation, and no cross-request prompt/result state.
- Structured redacted logs, correlation IDs, metrics/tracing hooks, readiness/liveness endpoints, graceful worker draining, rollbackable model routing, and incident runbooks.
- Pin and scan dependencies/images, record model provenance/licence, sign deployment artifacts, and separate inference from administration credentials.
- Treat prompts, retrieved code, and generated tool-call text as untrusted. Client tools remain locally permissioned. Do not claim LLM guardrails replace code-level authorization.

## Compatibility contract and test plan

The provider adapter should map OpenAI-compatible content and SSE chunks, tool-call deltas, finish reasons, usage, retryable errors, rate limits, and request IDs. A contract test suite must cover auth failures, model listing, normal and streamed responses, tool-call continuation formatting, malformed SSE, timeout/cancel, 429/backpressure, 5xx, reconnect, maximum request size, and cross-tenant isolation. A local mock server can validate client compatibility without remote calls.

## Deployment and capacity

Local container deployment should use a mock inference backend and synthetic requests; it can prove configuration and API behavior, not GPU performance. A later GPU deployment template must require an explicitly authorized provider/account, region, budget, model licence review, data-handling policy, and operational owner. Load-test scripts should report concurrency, queue depth, TTFT, tokens/sec, p50/p95 latency, GPU utilization/memory, and errors by model/version. Capacity and cost are unknown until a specific model, GPU, region, serving stack, and traffic profile are selected.
