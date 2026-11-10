# GameForge Ecosystem Navigation Map

**Current Directory Role:** Canonical Documentation, System Specifications, Architecture Contracts & Decision Registers  
**Master Ecosystem Authority:** `E:\GameForge_Documentation\context.md`  
**Host Config Profile:** `E:\GameForge_IDE\configs\host_profiles\dev-rx7700xt.json`  
**Core Architecture:** Unreal Engine 5.7.4 Exclusive (Active Core) with Dedicated Multi-Engine Repositories  

## Active 8-Directory Unreal Ecosystem
| Directory | Exact Purpose | Tech Stack / Stack Role |
|---|---|---|
| `E:\GameForge_IDE\` | Desktop Studio, Chat, Agent Runtime, Unreal C++ Synthesizer | Python 3.10+, PySide6, FastAPI, Pydantic |
| `E:\GameForge_Unreal_Plugin\` | Native C++ Unreal Engine Plugin (`GameForge.uplugin`) | C++20, UE 5.7.4, 129 Python Ops, MSVC 14.44 |
| `E:\GameForge_AI_Models\` | Model Storage (85 GB), Ollama Blobs, GGUFs, Serving Daemon | Ollama Server (localhost:11434), llama.cpp GGUF |
| `E:\GameForge_AI_Training\` | Model Fine-Tuning, QLoRA, SFT, Datasets, ROCm VEnv | Python 3.10 + PyTorch ROCm 6.x (AMD RX 7700 XT) |
| `E:\GameForge_Benchmarks\` | Consolidated QA, 45 Protected Oracles, AI Grading Harness | Python CLI (`gameforge-bench`), Pytest Oracles |
| `E:\GameForge_Projects\` | Synthesized User Game Workspaces & Packaged Executables | Unreal Engine `.uproject`, C++, Content, Saved |
| `E:\GameForge_Engine_Testbed\`| 43 GB Unreal 5.7.4 Testbed (`GFKitTest.uproject`) & Lab | Unreal Engine 5.7.4 Automation Rig, Test Maps |
| `E:\GameForge_Documentation\` | Canonical History (`context.md`), Specs, Contracts, Ledgers | Markdown, Mermaid, Architecture RFCs |

## Dedicated Separated Engine Repositories
The following standalone directories house the separated code, fixtures, adapters, benchmarks, training corpora, and specifications for non-Unreal engines:

| Engine | Directory | Contents & Maturity |
|---|---|---|
| **Unity** | `E:\GameForge_Unity\` | UnityEngineAdapter, discovery, 10 complete project fixtures, reference C# solutions, 10 eval rubrics, 160 SFT samples |
| **Godot 4.3** | `E:\GameForge_Godot\` | GDScript CharacterBody3D procedural codegen, knowledge base, 8 eval rubrics, 141 SFT samples |
| **Roblox Studio** | `E:\GameForge_Roblox\` | Luau RemoteEvent client-server replication codegen, security specs, eval questions, 100 SFT samples |
| **Bevy Engine** | `E:\GameForge_Bevy\` | Rust ECS system codegen, query scheduling & aliasing specs, eval questions, 80 SFT samples |
| **GameMaker** | `E:\GameForge_GameMaker\` | GML finite state machine & pixel collision specs, benchmark questions, 116-row feature matrix |
| **O3DE** | `E:\GameForge_O3DE\` | Atom Renderer & AZ::EBus component architecture specs, benchmark questions, 116-row feature matrix |

## Quick Navigation Guide for AI Agents:
- **To edit Desktop UI or Unreal Synthesizer:** Go to `E:\GameForge_IDE\`.
- **To edit Unreal C++ engine mechanics or Python Ops:** Go to `E:\GameForge_Unreal_Plugin\`.
- **To check model weights, GGUFs, or Ollama server:** Go to `E:\GameForge_AI_Models\`.
- **To run QLoRA training or inspect training datasets:** Go to `E:\GameForge_AI_Training\`.
- **To run protected benchmark grading or inspect oracles:** Go to `E:\GameForge_Benchmarks\`.
- **To inspect generated games or run standalone executables:** Go to `E:\GameForge_Projects\`.
- **To run real-engine automation tests (Automation RunTests):** Go to `E:\GameForge_Engine_Testbed\`.
- **To read canonical context, decisions, or roadmap:** Go to `E:\GameForge_Documentation\`.
- **To develop or inspect separated engines (Unity, Godot, Roblox, Bevy, GameMaker, O3DE):** Navigate directly to `E:\GameForge_<Engine>\`.
