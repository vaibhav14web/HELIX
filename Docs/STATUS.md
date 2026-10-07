# STATUS.md

# HELIX — Build Status

Last updated: 2026-10-07

---

## Legend

| Status | Meaning |
|--------|---------|
| ✅ Complete | Code exists, tests pass, meets budget |
| 🔨 In Progress | Code exists, functional, but undergoing refinement or partial |
| ❌ Missing | Not started |

---

## Layer: Foundation

| Module | Status | Notes |
|--------|--------|-------|
| config_manager | ✅ | env + JSON/YAML loader, defaults fallback |
| event_bus | ✅ | Async pub/sub with priority and fault-isolated subscriber handlers (A6) |
| logger | ✅ | File + console, JSONL cold logs |
| permission_manager | ✅ | Request/grant/deny flow, auto-approve patterns, risk validation |
| storage_manager | ✅ | Runtime + cold path config with degradation guards |
| auth & security | ✅ | 127.0.0.1 bind, Windows DPAPI bearer token, non-admin manifest (A1-A3) |
| crypto_dpapi | ✅ | DPAPI encryption at rest for memory and persisted automation state (A2, A7) |
| world_model_engine | ✅ | Win32 active window, foreground title & process telemetry |
| project_registry | ✅ | Local workspace scanner, Git branch & language stack indexer |
| observability_engine | ✅ | Distributed latency tracer, telemetry snapshot broadcasts |

---

## Layer: Core AI

| Module | Status | Notes |
|--------|--------|-------|
| llm_engine | ✅ | Ollama / llama.cpp GGUF / transformers, structured outputs |
| conversation_engine | ✅ | EventBus-driven contextual chat with rolling history |
| voice_engine | ✅ | faster-whisper STT + Piper TTS, sentence streaming, base64 audio bridge |
| wake_word_engine | ✅ | Low-power ambient wake engine, shared RingBuffer, openwakeword/energy VAD, ECS/SelfModel wired, REST endpoints |
| self_model_engine | ✅ | Identity vector, subsystem health status, resource tracking |
| goal_manager | ✅ | Long-running multi-step goal DAG manager & milestone progress |
| tool_calling | ✅ | Standard schema, multi-format parser (JSON/XML), sandboxed executor |

---

## Layer: Memory

| Module | Status | Notes |
|--------|--------|-------|
| conversation_memory | ✅ | JSONL, 7-day rolling window, DPAPI encryption at rest |
| preference_memory | ✅ | Permanent JSON store, categorized preferences, DPAPI encrypted |
| work_memory | ✅ | Session-scoped active work context + JSON persistence |
| explainability_engine | ✅ | JSONL append-only audit trail (reasons, benefits, risks) |
| warm_memory (vector) | ✅ | Semantic vector tier (Qdrant embedded/Docker) with FastEmbed ONNX, 8-30d recall, RAG prompt injection |
| cold_memory (external) | 🔨 | External SSD backup path configured; auto-sync daemon in progress |

---

## Layer: Context

| Module | Status | Notes |
|--------|--------|-------|
| context_aggregator | ✅ | Aggregates system, project, and user context snapshots |
| browser_engine | 🔨 | Win32 EnumWindows title inspection; deep CDP tab bridge planned |
| file_intelligence_engine | ✅ | Path-sandboxed file scanner and context reader (A5) |
| project_engine | ✅ | Project switch detection, root locator, session metadata |
| system_monitor_engine | ✅ | CPU, RAM, disk, idle state, and NVIDIA GPU telemetry |

---

## Layer: Action

| Module | Status | Notes |
|--------|--------|-------|
| planner_engine | ✅ | Task DAG planner, risk-classified steps, crash recovery (A7) |
| automation_engine | ✅ | Stepwise execution engine, DPAPI persisted state, abort handlers |
| action_executor | ✅ | Sandboxed app launch, file I/O, terminal commands, web search |
| productivity_engine | ✅ | Action pattern recorder, repeated workflow suggestions |
| timetable_scheduler | ✅ | Timetable JSON parser, scheduled reminder.due voice events |
| capability_registry | ✅ | System capability matrix, permissions, risk levels |
| app_discovery_engine | ✅ | Windows Start Menu, Registry, PATH & Winget software indexer |
| action_verification | ✅ | Empirical post-execution validation (tasklist process checks) |

---

## Layer: Companion

| Module | Status | Notes |
|--------|--------|-------|
| coding_companion | 🔨 | File TODO/FIXME detection; stuck-state loop detector in development |
| learning_companion | 🔨 | DSA topic detection; bilingual explanation suggestion triggers |
| productivity_companion | 🔨 | Automation completion tracking; sequence n-gram suggestion engine |

---

## Orchestrator & Executive Control

| Module | Status | Notes |
|--------|--------|-------|
| orchestrator | ✅ | Central lifecycle coordinator, subsystem startup and monitoring |
| executive_control_system | ✅ | 15-state ECS machine (Idle, Listening, Thinking, Executing, Sleeping) |

---

## API / Deployment

| Module | Status | Notes |
|--------|--------|-------|
| FastAPI main.py | ✅ | 40+ REST endpoints, WebSocket event bus bridge, token auth |
| loopback bind | ✅ | Explicitly locked to 127.0.0.1:8000 |
| Dockerfile & Compose | 🔨 | Docker Compose configuration proposed for Qdrant vector store |

---

## UI

| Module | Status | Notes |
|--------|--------|-------|
| Next.js 16 frontend | ✅ | OSShell modular interface with 13 nav sections |
| System Model View | ✅ | Live identity vector, active window focus, capability matrix |
| Goals Canvas View | ✅ | Visual multi-step goal DAG trees and subtask tracking |
| WebSocket bridge | ✅ | Real-time event streaming and audio response playback |

---

## Tests

| Test Suite | Status | Notes |
|------------|--------|-------|
| Unit & Integration Tests | ✅ | 319 passed across foundation, core_ai, memory, action, api, wake_word_pipeline |
| Security Verification | ✅ | Verified DPAPI encryption, path sandbox, privilege boundary |
| Document Tools | 🔨 | Requires python-docx & reportlab installed in runtime venv |

---

## PCOS Architectural Milestones

1. **Ambient Perception & Wake Word Engine (Phase 1):** ✅ **DONE — VERIFIED**
   - Shared low-power circular ring buffer (`RingBuffer`) with marker-based multi-consumer reading.
   - Dual-engine wake pipeline: `openwakeword` ONNX runtime + `energy_vad` fallback RMS power detector.
   - Full event wiring: `voice.wake` transitions ECS (`ExecutiveState.SLEEPING`/`IDLE` -> `LISTENING`) and updates `SelfModelEngine` state.
   - REST endpoints exposed: `GET /voice/wake-status` and `POST /voice/wake/simulate`.
   - Verified with 27/27 passed tests across wake and voice suites.
2. **3-Tier Warm Memory & Vector Layer (Phase 2):** ✅ **DONE — VERIFIED**
   - Embedded local disk / Docker Qdrant vector store (`QdrantVectorStore`) with `FastEmbed` ONNX embeddings (`bge-small-en-v1.5`, 384-dim) and pure in-memory fallback.
   - EventBus wiring: `memory.warm.index`, `memory.warm.search`, `memory.warm.searched`, `memory.warm.delete`, `memory.warm.rollover`.
   - Automatic RAG retrieval injection into `ConversationEngine` prompts (`<|context:retrieved_memories|>`) within `<500ms` target latency budget.
   - 8–30 day conversation rollover archiving pipeline (`rollover_conversations`).
   - REST endpoints exposed: `POST /memory/warm/index`, `POST /memory/warm/search`, `GET /memory/warm/stats`, `DELETE /memory/warm/{id}`, `POST /memory/warm/rollover`.
   - Verified with 8/8 unit & integration tests passing.
3. **Proactive Companion Upgrades (Phase 3):** 🔨 Planned. Implement developer stuck-loop detection and DSA spaced-repetition knowledge graph.
4. **Model Lifecycle Governance (Phase 4):** 🔨 Planned. Enforce ADR-025 VRAM eviction (Ollama `keep_alive: 0` on idle) and ADR-024 battery throttling.
