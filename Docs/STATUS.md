# STATUS.md

# HELIX — Build Status

Last updated: 2026-06-24

---

## Legend

| Status | Meaning |
|--------|---------|
| ✅ Complete | Code exists, tests pass, meets budget |
| 🔨 In Progress | Code exists but incomplete or untested |
| ❌ Missing | Not started |

---

## Layer: Foundation

| Module | Status | Notes |
|--------|--------|-------|
| config_manager | ✅ | env + JSON/YAML loader |
| event_bus | ✅ | publish/subscribe with priority |
| logger | ✅ | File + console, JSONL cold logs |
| permission_manager | ✅ | Request/grant/deny flow |
| storage_manager | ✅ | Runtime + cold path config |

## Layer: Core AI

| Module | Status | Notes |
|--------|--------|-------|
| llm_engine | ✅ | mock/ollama/llama.cpp/transformers backends |
| conversation_engine | ✅ | EventBus-driven chat with history |
| voice_engine | 🔨 | Implemented, needs tests |
| wake_word_engine | ❌ | Empty file |

## Layer: Memory

| Module | Status | Notes |
|--------|--------|-------|
| conversation_memory | ✅ | JSONL, 7-day rolling, archive |
| preference_memory | ✅ | Permanent JSON store |
| work_memory | ✅ | Session-scoped + JSON persistence |
| explainability_engine | ✅ | JSONL append-only log |

## Layer: Context

| Module | Status | Notes |
|--------|--------|-------|
| context_aggregator | ❌ | Empty file |
| browser_engine | ❌ | Empty file |
| file_intelligence_engine | ❌ | Empty file |
| project_engine | ❌ | Empty file |
| system_monitor_engine | ❌ | Empty file |

## Layer: Action

| Module | Status | Notes |
|--------|--------|-------|
| planner_engine | ❌ | Empty file |
| automation_engine | ❌ | Empty file |
| productivity_engine | ❌ | Empty file |

## Layer: Companion

| Module | Status | Notes |
|--------|--------|-------|
| coding_companion | ❌ | Empty file |
| learning_companion | ❌ | Empty file |
| future_companions | ❌ | Empty file |

## Orchestrator

| Module | Status | Notes |
|--------|--------|-------|
| orchestrator | ❌ | Missing module |

## API / Deployment

| Module | Status | Notes |
|--------|--------|-------|
| FastAPI main.py | ❌ | Missing |
| Dockerfile | ❌ | Missing |
| docker-compose.yml | ❌ | Missing |

## UI

| Module | Status | Notes |
|--------|--------|-------|
| Next.js frontend | 🔨 | Running on localhost:3000 |

## Tests

| Module | Status | Notes |
|--------|--------|-------|
| test_conversation_engine | ✅ | 7 tests passing |
| test_llm_engine | ✅ | 7 tests passing |
| test_event_bus | ✅ | Present |
| test_voice_engine | ❌ | Missing |

## Blockers

- GAP-009 (state orchestration) is OPEN but architecture is decided
- Context, Action, Companion layers are completely unbuilt
- No API layer means UI cannot communicate with backend
- No Docker means Qdrant and PostgreSQL not running

## Next Steps

1. Build Orchestrator
2. Implement wake_word_engine
3. Build FastAPI API layer
4. Implement all Context engines
5. Implement all Action engines
6. Implement all Companion engines
7. Write voice_engine tests
8. Integration test the full pipeline (wake → listen → LLM → speak)
