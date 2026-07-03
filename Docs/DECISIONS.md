# DECISIONS.md

# HELIX — Architectural Decisions Log

---

## DEC-001: Event Bus as Sole Inter-Module Communication

**Date:** 2026-06-24
**Status:** Accepted
**Modules:** All

**Decision:** All inter-module communication uses the `EventBus` only. No direct function calls or imports between modules.

**Rationale:** Decouples layers, enables async state machine, makes testing easier, aligns with AGENTS.md §6 and §7.

**Consequences:** Slightly more verbose, but system is testable, replaceable, and follows the spec exactly.

---

## DEC-002: Async-First Architecture

**Date:** 2026-06-24
**Status:** Accepted
**Modules:** All

**Decision:** All engine `start()`, `stop()`, and handlers are `async`. Blocking work (model loading, audio capture) runs in `asyncio.run_in_executor`.

**Rationale:** Prevents I/O and model inference from blocking the event loop. Required for real-time voice + LLM concurrency.

**Consequences:** All module APIs are async. Tests must use `pytest-asyncio`.

---

## DEC-003: State-Based Model Orchestration (ADR-025)

**Date:** 2026-06-24
**Status:** Accepted
**Modules:** Core AI, LLM Engine, Voice Engine

**Decision:** System runs three states:
- **Sleep:** Wake word only, EventBus, Logger, Memory Router. CPU<3%, RAM<2GB, VRAM 0MB.
- **Conversation:** Wake word → STT → LLM → TTS → unload. VRAM 4-5GB max.
- **Background:** Only when laptop idle + plugged in. Embedding generation, archiving, index maintenance. No LLM.

**Rationale:** RTX 3050 has only 6GB VRAM. 8GB LLM cannot fit. Continuous GPU usage violates N6 and ADR-009.

**Consequences:** Models are loaded on demand and unloaded after idle. Conversation state is the only state with significant VRAM load.

---

## DEC-004: LLM Backend Priority: Ollama → llama.cpp → transformers

**Date:** 2026-06-24
**Status:** Accepted
**Modules:** llm_engine

**Decision:** Backends in order of ease of setup and performance:
1. `ollama` — local server, no Python bindings, easiest to swap models
2. `llama.cpp` — Python bindings, direct GGUF loading
3. `transformers` — PyTorch, most flexible but heaviest

**Rationale:** User has Ollama available. `ollama` backend reduces Python dependency chain and allows hot-swapping models without restarting Python process.

---

## DEC-005: Voice Engine Backend: Mock → faster-whisper + Piper

**Date:** 2026-06-24
**Status:** Accepted
**Modules:** voice_engine

**Decision:** Default backend is `mock`. Production backends:
- STT: `faster-whisper` (CTranslate2, quantized, fast)
- TTS: `piper` (ONNX, small footprint, low latency)

**Rationale:** `faster-whisper` is significantly faster than OpenAI Whisper. Piper TTS is lightweight (few MB) and runs on CPU.

**Consequences:** Requires `sounddevice`, `numpy`, `faster-whisper`, `piper-tts` in production.

---

## DEC-006: Conversation Memory: JSONL + Rolling Window

**Date:** 2026-06-24
**Status:** Accepted
**Modules:** conversation_memory

**Decision:** Store conversations as JSONL files per session per day. Enforce 7-day rolling window. Archive (not delete) after 7 days.

**Rationale:** JSONL is append-only, human-readable, no database required for MVP. Rolling window matches PRD acceptance criteria and ADR-020.

**Consequences:** Search is currently substring-based (not vector). Warm Memory (Qdrant) will be added later for semantic search.

---

## DEC-007: Preference Memory: Permanent JSON Store

**Date:** 2026-06-24
**Status:** Accepted
**Modules:** preference_memory

**Decision:** Preferences stored in a single JSON file. No expiry. Loaded into memory on startup, saved on shutdown or mutation.

**Rationale:** Preference memory is permanent per ADR-020. Small enough for a single file.

---

## DEC-008: Work Memory: In-Memory + JSON Persistence

**Date:** 2026-06-24
**Status:** Accepted
**Modules:** work_memory

**Decision:** Active work session held in memory. Persisted to JSON on mutation/shutdown. Lifetime = project lifetime.

**Rationale:** Fast access for current session. Durable across restarts.

---

## DEC-009: Permission Flow: Event-Driven Approval

**Date:** 2026-06-24
**Status:** Accepted
**Modules:** permission_manager, all action modules

**Decision:** Every side-effecting action must:
1. Publish `permission.request` with `action`, `reasoning`, `benefits`, `risks`, `alternatives`
2. Wait for `permission.granted` or `permission.denied`
3. Execute or discard accordingly

**Rationale:** N3 — Every action requires permission. HSD non-negotiable.

---

## DEC-010: Cold Storage Logging: JSONL on External SSD

**Date:** 2026-06-24
**Status:** Accepted
**Modules:** logger

**Decision:** Conversation logs and explainability records use JSONL append-only format on `$HELIX_COLD_PATH` (external SSD). Logs are never written to runtime SSD.

**Rationale:** HSD §4 + AGENTS.md §16.

---

## DEC-011: UI Stack: Next.js 15 + React 19 + Tailwind CSS 4 + Framer Motion

**Date:** 2026-06-24
**Status:** Accepted
**Modules:** ui/

**Decision:** Frontend is a standalone Next.js App Router project under `ui/`. Communicates with Python backend via REST API.

**Rationale:** User requirement. FastAPI backend serves both UI and API.

---

## DEC-012: API Layer: FastAPI on localhost only

**Date:** 2026-06-24
**Status:** Accepted
**Modules:** api/

**Decision:** FastAPI app serves REST endpoints. Session token generated at startup. No cloud auth, no login screen.

**Rationale:** ADR-021. Local-only API.

---

## DEC-013: Docker: Runtime Services Only

**Date:** 2026-06-24
**Status:** Proposed
**Modules:** deployment/

**Decision:** Docker Compose runs:
- Qdrant (vector store)
- PostgreSQL (relational DB)
- FastAPI (backend API)

Models, active memory, and indexes stay on laptop SSD volumes.

**Rationale:** Matches AGENTS.md §19 stack. Services are stateful and need volumes.
