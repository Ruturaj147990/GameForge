# GameForge IDE Development and Deployment Runbook

**Updated:** 2026-10-24T17:50:20+05:30  
**State:** Source-run development is available. Packaged release is blocked by the absent PyInstaller dependency and has not been validated.

## Development launch

1. From `E:\gameforge_step1`, use the project Python environment and install only declared project dependencies through the approved development process.
2. Launch the native desktop: `python -m src.gameforge_ide.launcher`.
3. Optional Unreal bridge: generate a per-run `GAMEFORGE_BRIDGE_TOKEN`, then start `python -m src.gameforge_ide.launcher --serve --host 127.0.0.1 --port 8000`. The launcher rejects non-loopback hosts and refuses to start without the token. Launch Unreal Editor from the same environment so it inherits the same token.
4. Local inference uses the user-managed Ollama daemon and `gameforge-27b-sft:latest`. Direct generation and the provider stream were verified during this work.

## Authenticated Unreal bridge

The Unreal context GET/POST routes are disabled unless `GAMEFORGE_BRIDGE_TOKEN` is set. The plugin reads the same variable from its editor process and sends it as a bearer token. Generate a per-run secret and start the bridge in PowerShell without printing or saving the secret:

```powershell
$tokenBytes = New-Object byte[] 32
[System.Security.Cryptography.RandomNumberGenerator]::Fill($tokenBytes)
$env:GAMEFORGE_BRIDGE_TOKEN = [Convert]::ToBase64String($tokenBytes)
python -m src.gameforge_ide.launcher --serve --host 127.0.0.1 --port 8000
```

Launch Unreal Editor from a process that inherits the same environment. Do not put the token in source control, project files, command-line arguments, or logs. The shared token blocks unauthenticated local requests; processes running as the same Windows user may still be able to access it.

## Diagnostics

- Verify the desktop's Python/PySide6 dependencies, then use the toolbar's **Check Ollama** action for provider reachability.
- Check Unreal discovery in the Unreal panel. The installed engine is `E:\UE\UE_5.7` (5.7.4); a detected engine does not prove plugin compilation.
- Run the full unit suite with `python -m pytest tests/unit/ -q --basetemp .pytest_codex_verify` and protected graders with `python -m pytest graders/protected/ -q --basetemp .pytest_codex_protected`. Some fixtures call `tempfile.mkdtemp()` directly, so if C: temp access is blocked, set process `TEMP` and `TMP` to an existing workspace-local temporary directory. In this sandbox, tests that open local sockets require the test process to run with socket access; without it, Starlette TestClient can block during Proactor startup.
- Inspect `.gameforge/` session and workspace settings before recovery. Pending diff review state is in memory and is not proven to survive process restart.

## Packaging and release checklist (not yet executed)

1. Obtain authorization before installing PyInstaller or other system-level packaging software.
2. Build from a clean, recorded source revision into a dedicated release directory; preserve current user changes and never package model weights or protected graders.
3. Record Python/dependency versions, build command, exit code, artifact paths, SHA-256 digests, and a software bill of materials.
4. On a clean Windows account, install/launch the artifact, verify theme/settings, local Ollama connection, prompt streaming, diff review/apply/rollback, terminal availability, and offline error behavior.
5. Sign and publish only after explicit release authorization. No executable, signature, installer, or public release is claimed here.

## Recovery

Keep source and user session data separate from generated release files. On an application failure, preserve logs/session JSON, restart only the application process manually, and re-open the workspace. Do not delete or recreate model storage as a recovery action. If context/session JSON is damaged, copy it before any manual repair.
