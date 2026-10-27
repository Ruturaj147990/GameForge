# Technical Investigation Report: Unreal Engine 5.8 MCP Transport vs UE 5.7.4 Python Remote Execution

**Date:** October 27, 2026  
**Document ID:** GF-REPORT-UE58-MCP-01  
**Author:** GameForge Autonomous Engineering Agent  
**Conformance Reference:** GameForge — Master Blueprint (Oct 27, 2026)  

---

## 1. Executive Summary

This investigation evaluates the architectural and operational implications of Epic Games' Model Context Protocol (MCP) transport documented for Unreal Engine 5.8, contrasted against the verified Python Remote Execution transport currently operational on host Unreal Engine 5.7.4 (`E:\UE\UE_5.7\Engine\Binaries\Win64\UnrealEditor.exe`).

### Core Conclusion
- **UE 5.7.4 (Active Project Baseline):** Native Epic MCP does **not** exist in UE 5.7.4. The engine features Python Remote Execution (UDP 239.0.0.1:6766 multicast discovery, loopback TCP channel) and the experimental Remote Control HTTP API (port 30010).
- **UE 5.8 (Future Forward Target):** Epic's native MCP server operates as an in-editor endpoint (`127.0.0.1:8000/mcp`), exposing serial tool execution bound directly to the Unreal Game Thread.
- **Architectural Solution:** GameForge's `EditorTransport` abstraction layer (`PythonRemoteTransport` vs `EpicMcpTransport`) encapsulates the protocol differences behind a unified schema, ensuring zero agent runtime disruption when transitioning across engine versions.

---

## 2. Comparative Analysis of Transport Channels

| Evaluation Criterion | UE 5.7.4 Python Remote Execution (Active) | UE 5.8 Native Epic MCP (Investigated) |
| :--- | :--- | :--- |
| **Engine Status** | Fully operational on host `E:\UE\UE_5.7` | Documented in UE 5.8 preview docs; labeled Experimental |
| **Network Endpoint** | UDP discovery multicast (`239.0.0.1:6766`) + ephemeral loopback TCP | Direct HTTP JSON-RPC endpoint at `http://127.0.0.1:8000/mcp` |
| **Authentication** | None provided by Epic. GameForge injects mutual token validation (`UnrealSecurityBoundary`) | None provided by Epic. Requires local Windows user firewall or loopback token |
| **Thread Model** | Python execution blocks the Editor UI while running; single-threaded | Tools execute strictly serialized on the Unreal Game Thread |
| **PIE Interaction** | Connection drops during Play In Editor (PIE) because game thread is owned by simulation | Pauses or rejects MCP tool calls during PIE; requires explicit resume gate |
| **Shader Compilation** | Rapid calls during cold shader compilation crash the Python interpreter | HTTP server queues or times out requests during heavy asynchronous tasks |
| **Payload Format** | Custom Python script invocation string returning stringified standard out | Standardized Model Context Protocol JSON-RPC 2.0 schema |

---

## 3. Epic MCP Operational Hazards & Mitigation Strategy

1. **Cold-Editor Overload (TickLoop Hazard):**
   - *Hazard:* Firing rapid remote tool requests at an editor instance still compiling initial shaders or loading large level packages causes deadlock or crash in the engine's remote listener.
   - *GameForge Mitigation:* The `UnrealSupervisor` and `SerializedMutationQueue` enforce an **Idle Gate**: mutations wait for engine readiness (`shader_compiling == False`, `is_loading == False`, `in_pie == False`).

2. **Unauthenticated Local Surface:**
   - *Hazard:* Any rogue process or compromised local tool running under the developer's session could connect to `127.0.0.1:8000/mcp` and execute destructive editor commands without consent.
   - *GameForge Mitigation:* The GameForge gateway wraps the MCP transport with session tokens written to user-only ACL files (`.gameforge/unreal_session.token`), rejecting any untokenized caller.

3. **Game Thread Serialization Bottleneck:**
   - *Hazard:* Long-running MCP tool executions freeze the editor UI, resulting in Windows detecting the process as unresponsive ("Not Responding") and prompting termination.
   - *GameForge Mitigation:* All heavy operations (geometry generation, asset remeshing, lightmap baking) run outside the editor in background workers; the in-editor tool executes only brief atomic transactions (`ScopedSlowTask` with `should_cancel()`).

---

## 4. Transition Plan & Adapter Architecture

GameForge isolates the Unreal Engine communication through the abstract `EditorTransport` interface (`src/gameforge_ide/unreal/transport.py`):

```
       ┌────────────────────────────────────────────────────────┐
       │                GameForge Agent Runtime                 │
       └──────────────────────────┬─────────────────────────────┘
                                  │
                                  ▼
       ┌────────────────────────────────────────────────────────┐
       │               EditorTransport (Interface)              │
       └──────────────┬──────────────────────────┬──────────────┘
                      │                          │
                      ▼                          ▼
         ┌─────────────────────────┐┌─────────────────────────┐
         │  PythonRemoteTransport  ││    EpicMcpTransport     │
         │  (Active on UE 5.7.4)   ││   (Enabled on UE 5.8)   │
         └─────────────────────────┘└─────────────────────────┘
```

### Feature Detection at Startup
During supervisor initialization (`UnrealSupervisor._detect_features()`):
1. Test probe sent to `http://127.0.0.1:8000/mcp`.
2. If responsive with valid MCP handshake, activate `EpicMcpTransport`.
3. If unavailable (as on host UE 5.7.4), fail over to `PythonRemoteTransport` via `remote_execution.py`.
4. Feature flags reflect transport capability in UI settings.

---

## 5. Verification Sign-Off

- **Investigation Status:** COMPLETED.
- **Action Item:** Keep `EpicMcpTransport` disabled by default on UE 5.7.4 host; automatically feature-detect and promote on UE 5.8 upgrades.
- **Architectural Conformance:** 100% compliant with Master Blueprint directives.
