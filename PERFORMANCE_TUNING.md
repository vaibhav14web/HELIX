# Performance Tuning

Last updated: 2026-06-25

---

## Memory Leak Fixes

| Fix | Files | Impact |
|-----|-------|--------|
| Revoke `URL.createObjectURL` after TTS playback | `ui/components/overlays/voice-dock.tsx`, `ui/app/chat/page.tsx` | Stops ~100MB+ leak over time |
| Cap `chatEntries` at 100 | `ui/components/system/system-provider.tsx` | Prevents unbounded frontend memory growth |
| Cap `PermissionManager._history` at 200 | `foundation/permission_manager/permission_manager.py` | Prevents unbounded permission history |
| Cap `ConversationEngine` sessions at 50 | `core_ai/conversation_engine/conversation_engine.py` | Prevents unbounded session accumulation |
| Cap `WorkMemory._sessions` at 50 | `memory/work_memory/work_memory.py` | Prunes oldest sessions when exceeded |

## Model Lifecycle — Auto-Unload on Idle

Added `_schedule_unload_if_idle()` + `_last_used` tracking to all public VoiceEngine methods, so STT (~1-2GB) and TTS (~200-300MB) models free RAM after 2 minutes of inactivity:

| Method | File |
|--------|------|
| `transcribe()` | `core_ai/voice_engine/voice_engine.py:365` |
| `synthesize()` | `core_ai/voice_engine/voice_engine.py:333` |
| `_synthesize_and_play()` | `core_ai/voice_engine/voice_engine.py:581` |
| `_ensure_stt_loaded()` (reuse path) | `core_ai/voice_engine/voice_engine.py:398` |
| `_ensure_tts_loaded()` (reuse path) | `core_ai/voice_engine/voice_engine.py:429` |

## Polling Reduction

| Change | File | Before | After |
|--------|------|--------|-------|
| Home page context poll | `ui/app/page.tsx` | 5000ms | 30000ms |

## Env Var Configuration

Variables added to `.env` for tuning:

```ini
# Session caps
HELIX_CONVERSATION_MAX_SESSIONS=50
HELIX_WORK_MAX_SESSIONS=50

# Voice — unload after 2min idle
HELIX_VOICE_IDLE_UNLOAD_SECONDS=120

# Context — reduce poll frequency
HELIX_SYSTEM_MONITOR_INTERVAL=120
HELIX_CONTEXT_CACHE_TTL_SECONDS=120

# LLM idle unload
HELIX_LLM_IDLE_UNLOAD_SECONDS=120
```

Required external Ollama env vars (set in system, not `.env`):

```ini
OLLAMA_NUM_PARALLEL=1    # Prevent multiple model instances
OLLAMA_KEEP_ALIVE=1m     # Unload from RAM after 1min idle
```

## Docs Updated

- `Docs/Agents.md` §5 — Added Performance Tuning Configuration block
- `Docs/Agents.md` §9 — Added rules for lazy-start, capped collections, `_schedule_unload_if_idle()`
- `Docs/Agents.md` §12 — Added reload/fresh/leak/IDLE targets + Known Budget Gap

## Estimated Impact

| State | Before | After | Source |
|-------|--------|-------|--------|
| IDLE backend RAM | ~2-3 GB (models loaded) | ~0.5-1 GB (models unloaded) | Auto-unload after 120s idle |
| Memory leak rate | ~50-100 MB/hour | ~0 MB/hour | Capped collections + ObjectURL fix |
| Backend CPU load | Polling every 5-30s | Polling every 30-120s | Reduced intervals |
