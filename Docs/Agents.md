# AGENTS.md

# Helix — AI Agent Instruction Document

Version: 1.0
Status: Active
Owner: Vaibhav Kumar Singh
Governed By: 00_VISION.md → 01_HSD.md → 02_PRD.md → 03_SAD.md → 04_CFD.md

---

## 0. Prime Directive

You are a contributing agent to Helix — a Context-Aware Personal Cognitive Operating System.

Your job is to implement, extend, or review Helix modules.

You do not decide what Helix is.

The specification documents decide that.

Your job is to execute their intent precisely.

---

## 1. Document Authority Hierarchy

Before writing a single line of code, read the relevant documents.

Resolve all conflicts using this hierarchy:

```
01_HSD.md       ← Constitution. Wins all conflicts. Non-negotiable rules live here.
      ↓
00_VISION.md    ← Intent and philosophy. Use when HSD is silent.
      ↓
02_PRD.md       ← User requirements. Defines what must be built and why.
      ↓
03_SAD.md       ← System architecture. Defines how it is built.
      ↓
04_CFD.md       ← Control flow. Defines when and how things happen at runtime.
```

If a conflict exists between documents:
- Higher document wins.
- Log the conflict as a gap in `GAPS.md`.
- Do not silently resolve it by guessing.

---

## 2. Non-Negotiable Rules (from 01_HSD.md)

These rules can never be broken under any circumstance.
No feature, optimization, or shortcut overrides them.

| Rule | Requirement |
|------|-------------|
| N1 | Human authority is supreme |
| N2 | No autonomous execution |
| N3 | Every action requires permission |
| N4 | Everything must work offline first |
| N5 | Productivity is prioritized over aesthetics |
| N6 | Power efficiency is mandatory |
| N7 | Maintainability is mandatory |
| N8 | User trust is mandatory |
| N9 | Hardware constraints are permanent |
| N10 | Overengineering is forbidden |

If your implementation violates any of these, stop and redesign.

---

## 3. Hardware Constraints (Permanent)

These are fixed. Never design beyond them.

```
OS:         Windows 11
CPU:        Intel i5-12450H
GPU:        RTX3050 6GB VRAM
RAM:        16GB
Laptop SSD: 155GB available  ← runtime storage only
External SSD: 368GB          ← cold storage only
Single user. Laptop only. No distributed systems. No cloud dependency.
```

---

## 4. Storage Rules (from 01_HSD.md + 03_SAD.md + 04_CFD.md)

### Laptop SSD — Runtime Only
Allowed:
- Source code
- Models
- Databases
- Embeddings and vector indexes
- Configurations
- Active memory
- Runtime caches

### External SSD — Cold Storage Only
Allowed:
- Backups
- Logs
- Snapshots
- Archived memories
- Archived projects
- Research datasets
- Exports

Forbidden on External SSD:
- Running models
- Running databases
- Running vector stores
- Running active memory or indexes

Storage paths must always be configurable via environment variables.
Never hardcode a path.

```python
# Correct
LOG_PATH = os.getenv("HELIX_LOG_PATH", "/default/cold/logs")

# Forbidden
LOG_PATH = "F:/helix/logs"
```

---

## 5. Resource Budget (from 01_HSD.md + 04_CFD.md)

Your code must respect these limits at all times.

| State | CPU | RAM | GPU / VRAM |
|-------|-----|-----|------------|
| IDLE | <3% | <1.5GB | 0% / 0GB |
| LISTENING | <10% | <2GB | 0% / 0GB |
| PROCESSING | <40% | <5GB | — / <5GB |
| BACKGROUND | <20% | — | 0% / 0GB |
| Maximum | <70% | <8GB | — / <5.5GB |
| Disk Total | — | — | <30GB |

Per-layer runtime allocation (from 03_SAD.md):

| Layer | CPU | RAM |
|-------|-----|-----|
| Foundation | <1% | <300MB |
| Core AI | <30% | <3GB |
| Memory | <5% | <500MB |
| Context | <5% | <500MB |
| Action | <20% | <500MB |
| Companion | <5% | <500MB |

If your module exceeds its layer budget, it must not be merged.

### Performance Tuning Configuration

Set these env vars to stay within budget:

```ini
# Ollama — reduce memory footprint
OLLAMA_NUM_PARALLEL=1        # Prevent multiple model instances
OLLAMA_KEEP_ALIVE=1m         # Unload from RAM after 1min idle (default 5min)

# Voice — unload models faster after idle
HELIX_VOICE_IDLE_UNLOAD_SECONDS=120   # Free STT/TTS RAM after 2min (default 300)

# Context — reduce polling frequency
HELIX_SYSTEM_MONITOR_INTERVAL=120     # System metrics every 2min (default 30)
HELIX_CONTEXT_CACHE_TTL_SECONDS=120   # Stale context after 2min (default 30)

# Conversation — cap memory usage
HELIX_CONVERSATION_MAX_HISTORY=20     # Max turns per session
HELIX_CONVERSATION_MAX_SESSIONS=50    # Max concurrent sessions

# Work memory — cap stored sessions
HELIX_WORK_MAX_SESSIONS=50            # Prune oldest when exceeded

# Frontend — reduce poll rate (set in NEXT_PUBLIC_ or ui code)
# Home page context poll: 30000ms (default 5000)
```

---

## 6. Layer Architecture (from 01_HSD.md + 03_SAD.md)

```
Foundation Layer    ← Config, Logger, Event Bus, Permissions, Storage
        ↓
Core AI Layer       ← Wake Word, Voice, LLM, Conversation
        ↓
Memory Layer        ← Conversation Memory, Preference Memory, Work Memory, Explainability
        ↓
Context Layer       ← Browser, Project, File Intelligence, System Monitor, Aggregator
        ↓
Action Layer        ← Automation, Planner, Productivity
        ↓
Companion Layer     ← Coding Companion, Learning Companion, Future Companions
```

Rules:
- No layer may bypass another layer.
- No module may import another module directly.
- All communication happens through the Event Bus only.

---

## 7. Event Bus Rules (from 03_SAD.md)

All inter-module communication uses the Event Bus.

Every event must contain:

```python
{
    "event_id": str,        # unique UUID
    "timestamp": str,       # ISO 8601
    "source": str,          # module name
    "event_type": str,      # e.g. "memory.store", "context.update"
    "priority": int,        # 0=low, 1=normal, 2=high, 3=critical
    "payload": dict,        # event data
    "correlation_id": str   # links related events
}
```

Never use direct function calls or imports between modules.
Modules are publishers and subscribers only.

---

## 8. Permission System (from 01_HSD.md + 02_PRD.md + 04_CFD.md)

Every action that affects the user's environment must follow this exact flow.
No exceptions.

```
Observe
    ↓
Suggest
    ↓
Explain (why + benefits + risks + alternatives)
    ↓
Ask Permission
    ↓
Execute
    ↓
Report
```

If the user rejects: discard the action, return to IDLE.
Hidden execution is forbidden.
Silent execution is forbidden.

---

## 9. Power Efficiency Rules (from 01_HSD.md + 04_CFD.md)

Mandatory:

- Prefer events over polling loops.
- Prefer lazy loading over eager loading.
- Unload models after use — never keep loaded unnecessarily.
- Sleep inactive modules.
- Batch expensive operations.
- Schedule heavy tasks only when: CPU <20%, GPU=0%, user idle, plugged in preferred.
- If user becomes active during background tasks: stop immediately.
- Context engines (browser, file, system) must lazy-start on first request, not at boot.
- Frontend polls (context, health) must not exceed 30s intervals; prefer event-driven updates.
- Every public API method in VoiceEngine must call `_schedule_unload_if_idle()` to track last-used time.
- All lists with unbounded growth must be capped (chat entries, session history, permission history, work sessions).

Forbidden:
- Continuous GPU usage
- Continuous scanning
- Continuous polling
- Continuous indexing
- Continuous microphone processing
- Unbounded in-memory collections (always set a max size and prune)

---

## 10. Module Build Order

```
1. Memory Module
2. Context Ingestion Module
3. Companions Module
4. Projects / Workspace Module
5. Actions Module
```

Do not begin a module until the previous module has passing integration tests.

---

## 11. Module Completion Criteria (from 01_HSD.md §23)

A module is only complete when ALL of the following are true:

- [ ] Code exists and is functional
- [ ] Tests pass (unit + integration)
- [ ] Resource budget respected and measured
- [ ] Documentation updated
- [ ] Research contribution identified
- [ ] Performance measured against targets
- [ ] Power usage measured
- [ ] Decisions logged in `DECISIONS.md`
- [ ] Status updated in module README

---

## 12. Performance Targets (from 02_PRD.md + 03_SAD.md)

| Operation | Target |
|-----------|--------|
| Startup | <20s |
| Voice Response | <3s |
| Interrupt | <500ms |
| Project Load | <5s |
| Memory Retrieval | <200ms |
| Notification | <300ms |
| Voice model reload from idle | <2s (cold, from SSD) |
| Frontend context refresh | <500ms (network + backend) |
| Memory Leak Rate | 0 MB/hour (steady state) |
| IDLE RAM target | <3GB total (all layers + Ollama) |

Every module must be benchmarked against its relevant target before completion.

### Known Budget Gap

Current IDLE RAM exceeds the <1.5GB target (~2-3GB) due to:
- Ollama external process (~1-2GB separate)
- Voice models staying loaded when idle (mitigated by auto-unload at 120s)
- Frontend Next.js dev server (~300-500MB)

Target IDLE RAM of <1.5GB applies only to the Python backend process (Foundation + Core AI + Memory + Context layers). Ollama and the frontend are separate processes and tracked independently.

---

## 13. AI Behaviour Ceiling (from 00_VISION.md + 01_HSD.md)

```
Level 0 — Reactive
Level 1 — Aware
Level 2 — Suggestive
Level 3 — Predictive
Level 4 — Adaptive
Level 5 — Collaborative  ← Maximum allowed
```

Never implement behaviour beyond Level 5.
Never implement autonomous decision-making.
Never act without user permission.

---

## 14. Feature Acceptance Test (from 01_HSD.md §20)

Before implementing any feature, score it honestly:

| Factor | Question |
|--------|----------|
| Productivity Gain | How much time does this save? |
| Frequency of Use | How often will this be used? |
| Trust Impact | Does this increase or risk user trust? |
| Power Cost | What is the resource cost? |
| Complexity | How complex is this to build and maintain? |
| Maintainability | Can this be maintained long-term? |

If cost exceeds usefulness: reject the feature.
If a feature does not save time: it should not exist.

---

## 15. Error Handling Rules (from 03_SAD.md + 04_CFD.md)

Every error must follow:

```
Catch
    ↓
Retry once
    ↓
Still failed → Translate to human-readable message
    ↓
Explain fix
    ↓
Log to cold storage
    ↓
Continue system (never crash silently)
```

Never fail silently.
Never swallow exceptions without logging.
Never expose raw stack traces to the user.

---

## 16. Conversation Log Rules (from storage decisions)

- Format: JSONL (append-only)
- Location: `$HELIX_LOG_PATH` (external SSD cold storage)
- Each line must contain: `timestamp`, `session_id`, `companion_id`, `role`, `content`
- Rotation: by date or size threshold (configurable)
- Never write logs to the laptop SSD runtime store
- Never read logs at runtime for core operations (cold storage only)

---

## 17. What Agent Must Not Do

- Do not add features not specified in the docs
- Do not import modules directly (use Event Bus)
- Do not hardcode paths, credentials, or model names
- Do not run anything on the External SSD at runtime
- Do not implement autonomous execution
- Do not skip the permission flow
- Do not add unnecessary dependencies
- Do not build for multi-user, mobile, or cloud
- Do not resolve document conflicts silently — log them in `GAPS.md`
- Do not start a new module before the previous one has passing tests

---

## 18. What Agent Must Always Do

- Read relevant spec docs before writing code
- Follow the document authority hierarchy
- Respect hardware constraints
- Respect resource budgets per layer
- Communicate only via Event Bus
- Implement permission flow for every action
- Measure and log resource usage
- Write tests before marking a module complete
- Update `DECISIONS.md` for every architectural choice
- Flag ambiguities in `GAPS.md` rather than guessing

---

## 19. Stack

```
Language:       Python 3.11+
API Framework:  FastAPI
Vector Store:   Qdrant (Docker, laptop SSD volume)
Relational DB:  PostgreSQL (Docker, laptop SSD volume)
ORM:            SQLAlchemy
Embeddings:     sentence-transformers (local, no cloud API)
Log Format:     JSONL (append-only, external SSD)
Containerization: Docker + docker-compose
```

No paid external APIs.
No cloud dependencies.
All models run locally.

---

## 20. Companion Files to Maintain

| File | Purpose |
|------|---------|
| `AGENTS.md` | This file. Agent instructions. |
| `DECISIONS.md` | Log every architectural decision with rationale. |
| `GAPS.md` | Log every spec ambiguity or conflict found. |
| `STATUS.md` | Current build status per module. |
| `RESEARCH.md` | Research contributions identified per module. |

# AGENTS.md

# HELIX - Personal AI Operating System

## Philosophy

Helix is NOT:

- A chatbot
- A Jarvis clone
- A fully autonomous agent

Helix IS:

- A Personal Cognitive Operating System (PCOS)
- Local-first
- Permission-first
- Context-aware
- Human-in-control

Agents must never execute destructive actions without approval.

---

# CORE AI ARCHITECTURE

Core AI is composed of multiple specialized agents coordinated by the Orchestrator.

User

↓

Voice Agent

↓

Intent Agent

↓

Context Agent

↓

Reasoning Agent

↓

Planner Agent

↓

Action Agent

↓

Response Agent

↓

Memory Agent

---

# MODEL STACK

## LLM

Orchestrator & General Conversation:

Qwen3-4B-Q8_0.gguf

Coding & Programming Tasks:

qwen2.5-coder-3b-instruct-q8_0.gguf

Purpose:

- Reasoning, planning, and general conversation (Qwen3-4B)
- Code writing, refactoring, and debugging (qwen2.5-coder)

Location:

C:\Users\vaibh\Documents\HELIX_MODELS\LLM\

---

## Embedding Model

LFM2.5-Embedding-350M-Q8_0.gguf

Purpose:

- Memory search
- Semantic retrieval
- Context building

Location:

C:\Users\vaibh\Documents\HELIX_MODELS\Embeddings\

---

## STT

faster-whisper-small

Purpose:

- Speech to text

Location:

models/faster-whisper/

---

## TTS

piper-zh_CN-huayan-medium-f16.gguf (Mandarin Chinese Voice)

Purpose:

- Voice output

Location:

C:\Users\vaibh\Documents\HELIX_MODELS\PIPER\

---

## Wake Word

openWakeWord

Wake Phrase:

Hola Helix

Location:

models/openwakeword/

---

# AGENTS

## 1. Voice Agent

Responsibility:

- Wake word detection
- Microphone handling
- Voice recording
- STT execution
- TTS execution

Input:

Audio

Output:

Text

Owns:

voice_module

---

## 2. Intent Agent

Responsibility:

Convert user input into structured intent.

Example:

Input:

"Open chrome and search AI news"

Output:

{
  "intent":"browser_search",
  "target":"chrome",
  "query":"AI news"
}

Owns:

intent_parser

---

## 3. Context Agent

Responsibility:

Build user context.

Sources:

- Memory
- Open applications
- Browser tabs
- Active project
- Time
- System state

Owns:

context_builder

---

## 4. Memory Agent

Responsibility:

Store and retrieve memories.

Types:

- Conversation
- Preferences
- Projects
- Explainability

Uses:

SQLite

BGE embeddings

Owns:

memory_module

---

## 5. Reasoning Agent

Responsibility:

Think before acting.

Rules:

- Never hallucinate actions
- Never assume permissions
- Verify context

Uses:

Qwen3

Owns:

reasoning_engine

---

## 6. Planner Agent

Responsibility:

Break tasks into steps.

Example:

User:

"Prepare DSA study plan"

Output:

Step1
Step2
Step3

Owns:

planner

---

## 7. Action Agent

Responsibility:

Execute actions.

Examples:

- Open applications
- Launch browser
- Read files
- Notifications

Never execute destructive actions automatically.

Owns:

action_executor

---

## 8. Response Agent

Responsibility:

Generate final response.

Input:

Reasoning output

Output:

Natural language

Uses:

Qwen3

Owns:

response_generator

---

# ORCHESTRATOR RULES

Modules never directly communicate.

BAD:

Voice → Memory

Memory → Browser

Browser → Action

GOOD:

Voice

↓

Event Bus

↓

Orchestrator

↓

Agents

---

# EXECUTION PIPELINE

User

↓

Voice Agent

↓

Intent Agent

↓

Context Agent

↓

Memory Agent

↓

Reasoning Agent

↓

Planner Agent

↓

Action Agent

↓

Response Agent

↓

Voice Agent

---

# RESOURCE CONSTRAINTS

Hardware:

i5-12450H

RTX3050 6GB

16GB RAM

Rules:

- Heavy models must not stay loaded forever
- Lazy load models
- Unload when idle
- CPU idle <5%
- RAM target <4GB
- VRAM target <5GB

---

# DEVELOPMENT RULES

Always:

- Build modules independently
- Test modules independently
- Use sandbox scripts
- Use internal APIs
- Use event bus

Never:

- Hardcode paths
- Hardcode models
- Create circular dependencies
- Couple agents together