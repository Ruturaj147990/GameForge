# GameForge Ecosystem Navigation Map

**Current Directory Role:** Desktop Studio Application, Chat/Prompt Interface, Agent Loop & Level Synthesizer  
**Master Ecosystem Authority:** `E:\GameForge_Documentation\context.md`  
**Host Config Profile:** `E:\GameForge_IDE\configs\host_profiles\dev-rx7700xt.json`  

## Complete 8-Directory Map
| Directory | Exact Purpose | Tech Stack / Stack Role |
|---|---|---|
| `E:\GameForge_IDE\` | Desktop Studio, Chat, Agent Runtime, Level Synthesizer | Python 3.10+, PySide6, FastAPI, Pydantic |
| `E:\GameForge_Unreal_Plugin\` | Native C++ Unreal Engine Plugin (`GameForge.uplugin`) | C++20, UE 5.7.4, 129 Python Ops, MSVC 14.44 |
| `E:\GameForge_AI_Models\` | Model Storage (85 GB), Ollama Blobs, GGUFs, Serving Daemon | Ollama Server (localhost:11434), llama.cpp GGUF |
| `E:\GameForge_AI_Training\` | Model Fine-Tuning, QLoRA, SFT, Datasets, ROCm VEnv | Python 3.10 + PyTorch ROCm 6.x (AMD RX 7700 XT) |
| `E:\GameForge_Benchmarks\` | Independent QA, 45 Protected Oracles, AI Grading Harness | Python CLI (`gameforge-bench`), Pytest Oracles |
| `E:\GameForge_Projects\` | Synthesized User Game Workspaces & Packaged Executables | Unreal Engine `.uproject`, C++, Content, Saved |
| `E:\GameForge_Engine_Testbed\`| 43 GB Unreal 5.7.4 Testbed (`GFKitTest.uproject`) & Lab | Unreal Engine 5.7.4 Automation Rig, Test Maps |
| `E:\GameForge_Documentation\` | Canonical History (`context.md`), Specs, Contracts, Ledgers | Markdown, Mermaid, Architecture RFCs |

## Quick Navigation Guide for AI Agents:
- **To edit the Desktop UI or Agent Runtime:** Go to `E:\GameForge_IDE\`.
- **To edit Unreal C++ engine mechanics or Python Ops:** Go to `E:\GameForge_Unreal_Plugin\`.
- **To check model weights, GGUFs, or Ollama server:** Go to `E:\GameForge_AI_Models\`.
- **To run QLoRA training or inspect training datasets:** Go to `E:\GameForge_AI_Training\`.
- **To run protected benchmark grading or inspect oracles:** Go to `E:\GameForge_Benchmarks\`.
- **To inspect generated games or run standalone executables:** Go to `E:\GameForge_Projects\`.
- **To run real-engine automation tests (Automation RunTests):** Go to `E:\GameForge_Engine_Testbed\`.
- **To read canonical context, decisions, or roadmap:** Go to `E:\GameForge_Documentation\`.
