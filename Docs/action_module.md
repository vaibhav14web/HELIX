# Action Module

**Layer:** Action Layer  
**Status:** Implemented  
**Last Updated:** 2026-06-26  

---

## Overview

The Action Layer is responsible for converting user intents into executable operations. It receives planned steps from the Conversation/LLM pipeline, manages permissions via a **Static Risk Classification Matrix**, executes actions safely, and tracks patterns for productivity suggestions.

All inter-module communication happens exclusively through the **Event Bus** — no direct imports between modules.

---

## Architecture

```
Planner Engine        ← Breaks natural-language tasks into PlanSteps
      ↓
Automation Engine     ← Manages lifecycle (permissions, execution, history)
      ↓
Action Executor       ← Performs the actual system operations
      ↓
Productivity Engine   ← Observes patterns and suggests automations
```

### Sub-Module Dependency Graph

```
PlannerEngine ──► Event Bus ──► AutomationEngine ──► Event Bus ──► ActionExecutor
                                      │
                                ProductivityEngine (observes completed actions)
```

---

## Static Risk Classification Matrix

Every `PlanStep` is tagged with a `risk_level` by `PlannerEngine._classify_risk()`. The AutomationEngine uses this tag to determine the execution policy.

| Risk Level | Permitted Actions | Execution Policy |
|------------|------------------|------------------|
| **low** | `browser_search`, `read_file` (non-system paths), `launch_application` (known apps: chrome, edge, firefox, notepad, calc, mspaint, wt, explorer), `send_notification`, `open_url` | Auto-dispatch via `action.execute` — no user prompt required |
| **medium** | `compose_email`, `launch_application` (unknown/unlisted apps), `unknown` actions | Halt and issue a single authorization prompt. Wait for `permission.granted` before dispatching |
| **high** | `read_file` (system paths), `open_url` (blocked schemes), file operations on blocked extensions | Double-checkpoint: (1) verbal/text confirmation via `automation.confirm.request`, (2) formal permission barrier via `automation.permission_needed` |

### Risk Classification Logic

| Action | Condition | Risk Level |
|--------|-----------|------------|
| `browser_search` | Always | low |
| `read_file` | Path contains system paths (SystemRoot, ProgramData, Program Files) | high |
| `read_file` | Path has blocked extension (.exe, .bat, .ps1, .vbs, etc.) | high |
| `read_file` | Safe path | low |
| `launch_application` | App is in known low-risk list (chrome, notepad, etc.) | low |
| `launch_application` | App is known but not in low-risk list | medium |
| `compose_email` | Always | medium |
| `send_notification` | Always | low |
| `open_url` | URL scheme not in (http, https, mailto) | high |
| `open_url` | Safe scheme | low |
| `unknown` | Task didn't match any known intent | medium |

### System Protection Guardrails

The PlannerEngine enforces these safety checks at plan-creation time:

- **Blocked system paths**: `SystemRoot`, `ProgramData`, `Program Files` (and their resolved environment variable paths) are rejected
- **Blocked file extensions**: `.exe`, `.bat`, `.cmd`, `.ps1`, `.vbs`, `.js`, `.reg`, and 15+ more executable/script formats are blocked
- **URL scheme validation**: Only `http://`, `https://`, and `mailto:` schemes are permitted
- **Unknown intents**: Tasks that don't match any known pattern are tagged as `action: "unknown"` with `risk_level: "medium"`

---

## Sub-Modules

### 1. PlannerEngine (`action/planner_engine/planner_engine.py`)

Converts a free-text user task into a structured `Plan` containing ordered `PlanStep` objects.

#### Classes

| Class | Description |
|-------|-------------|
| `PlanStep` | A single executable step with `action`, `target`, `params`, `depends_on`, and `status` |
| `Plan` | Container for multiple `PlanStep`s with `plan_id`, `task`, `status`, timestamps |
| `PlannerEngine` | Event-driven planner that subscribes to `plan.request` |

#### Intent Mapping (`_build_steps`)

| User Says | Action Produced | Target / Params |
|-----------|----------------|-----------------|
| "search X", "browse X", "look up X", "find X" | `browser_search` | `target: "browser"`, `params: {"query": "X"}` |
| "open file X" | `read_file` | `params: {"path": "X"}` |
| "open X", "launch X", "start X" | `launch_application` | `target: "X"`, `params: {"application": "X"}` |
| "send email/mail ..." | `compose_email` | `params: {"subject": "..."}` |
| "notify ...", "alert ...", "remind ..." | `send_notification` | `params: {"message": "..."}` |
| "read X" | `read_file` | `params: {"path": "X"}` |
| Everything else | `unknown` | `params: {"task": "..."}` |

#### Events

| Subscribes To | Publishes |
|--------------|-----------|
| `plan.request` | `plan.created`, `plan.completed`, `plan.failed`, `plan.cancelled` |
| `plan.step.completed` | |
| `plan.step.failed` | |
| `plan.cancel` | |

---

### 2. AutomationEngine (`action/automation_engine/automation_engine.py`)

Manages the full lifecycle of an action: receives execution requests, applies risk-based permission gating, dispatches to the Action Executor, and tracks history.

#### Classes

| Class | Description |
|-------|-------------|
| `ActionRecord` | Tracks a single action's state through its lifecycle (`pending` → `waiting_permission` → `waiting_confirmation` → `executing` → `completed`/`failed`/`denied`/`timeout`) |
| `AutomationEngine` | Subscribes to automation events and orchestrates execution with risk-based gating |

#### Risk-Based Permission Flow

```
automation.execute
      ↓
Check risk_level (from PlanStep)
      ↓
┌──────────────────────────────────────────────────────────┐
│  LOW RISK → _execute_action() → action.execute          │
│           (auto-dispatch, no permission needed)          │
├──────────────────────────────────────────────────────────┤
│  MEDIUM RISK → _request_permission()                    │
│           → generates permission_id                     │
│           → stores in _actions_by_permission            │
│           → publishes automation.permission_needed      │
│           → waits for permission.granted                │
│           → on grant: _execute_action()                 │
│           → on deny: marks action as "denied"           │
├──────────────────────────────────────────────────────────┤
│  HIGH RISK → _request_confirmation()                    │
│     Step 1: → publishes automation.confirm.request      │
│             → waits for automation.confirm.response     │
│             → if denied: marks as "denied"              │
│             → if confirmed: proceeds to Step 2          │
│     Step 2: → _request_permission() (same as medium)    │
│             → publishes automation.permission_needed    │
│             → waits for permission.granted              │
│             → on grant: _execute_action()               │
│             → on deny: marks as "denied"                │
└──────────────────────────────────────────────────────────┘
      ↓
Action Executor publishes automation.result or automation.failed
```

#### Events

| Subscribes To | Publishes |
|--------------|-----------|
| `automation.execute` | `action.execute` |
| `automation.execute_step` | `automation.completed`, `automation.failed` |
| `automation.result` | `automation.permission_needed` |
| `automation.failed` | `automation.confirm.request` |
| `automation.cancel` | |
| `automation.confirm.response` | |
| `permission.granted` | |
| `permission.denied` | |

#### Action States

| State | Description |
|-------|-------------|
| `pending` | Just created, awaiting dispatch decision |
| `waiting_permission` | Medium/high risk — awaiting user permission grant |
| `waiting_confirmation` | High risk — awaiting verbal/textual confirmation (double-check step 1) |
| `executing` | Dispatched to ActionExecutor, awaiting result |
| `completed` | Action succeeded |
| `failed` | Action failed with error |
| `denied` | User denied permission |
| `timeout` | Permission or confirmation request timed out |

#### Safety Features

- Permission/confirmation timeout watchdog (configurable via `HELIX_AUTOMATION_PERMISSION_TIMEOUT`, default 300s)
- Max action history cap (`HELIX_AUTOMATION_MAX_HISTORY`, default 200)
- State persistence via `save_state()` / `load_state()`

---

### 3. ActionExecutor (`action/action_executor/action_executor.py`)

Performs the actual system-level operations. This is the only sub-module that interacts with the OS (processes, files, notifications, browser).

#### Trusted Sources

Only events from specific sources are accepted:
- `automation_engine`
- `planner_engine`
- `orchestrator`
- `test` (when `HELIX_DEV_MODE=true`)

#### Implemented Actions

| Action | Method | Description |
|--------|--------|-------------|
| `browser_search` | `_browser_search()` | Opens a search URL in the default browser |
| `launch_application` | `_launch_application()` | Launches a known application by name |
| `read_file` | `_read_file()` | Opens a file with the OS default handler |
| `send_notification` | `_send_notification()` | Sends a desktop toast/notification |
| `compose_email` | `_compose_email()` | Opens default mail client with pre-filled fields |
| `open_url` | `_open_url()` | Opens a URL in the default browser |

#### Known Applications

| Name | Executable |
|------|-----------|
| `chrome`, `google chrome` | `chrome.exe` |
| `edge`, `microsoft edge` | `msedge.exe` |
| `firefox` | `firefox.exe` |
| `notepad` | `notepad.exe` |
| `calculator` | `calc.exe` |
| `paint` | `mspaint.exe` |
| `terminal` | `wt.exe` |
| `explorer`, `file explorer` | `explorer.exe` |

#### Application Discovery (Fallback Paths)

When an executable is not found on the system PATH, the executor checks well-known install locations:

| Executable | Fallback Paths Checked |
|-----------|----------------------|
| `chrome.exe` | `%ProgramFiles%\Google\Chrome\Application\`, `%ProgramFiles(x86)%\Google\Chrome\Application\`, `%LocalAppData%\Google\Chrome\Application\` |
| `msedge.exe` | `%ProgramFiles(x86)%\Microsoft\Edge\Application\`, `%ProgramFiles%\Microsoft\Edge\Application\` |
| `firefox.exe` | `%ProgramFiles%\Mozilla Firefox\`, `%ProgramFiles(x86)%\Mozilla Firefox\` |

#### Security Protections

| Protection | Implementation |
|-----------|---------------|
| Source validation | Only trusted event sources can dispatch actions |
| Rate limiting | Max 5 actions per 2-second window |
| Input validation | String length caps, type checking, email regex |
| Blocked file paths | `SystemRoot`, `ProgramData`, `Program Files` inaccessible |
| Blocked file types | `.exe`, `.bat`, `.cmd`, `.ps1`, `.vbs`, `.js`, `.reg`, etc. |
| URL scheme validation | Only `http://`, `https://`, `mailto:` allowed |

#### Cross-Platform Support

| Feature | Windows | macOS | Linux |
|---------|---------|-------|-------|
| Launch app | `subprocess.Popen` | `subprocess.Popen` | `subprocess.Popen` |
| Open file | `os.startfile` | `open` | `xdg-open` |
| Notification | PowerShell toast | `osascript` | `notify-send` |
| Open URL | `webbrowser.open` | `webbrowser.open` | `webbrowser.open` |

---

### 4. ProductivityEngine (`action/productivity_engine/productivity_engine.py`)

Monitors completed actions to detect repeated patterns and suggests automations to the user.

#### Classes

| Class | Description |
|-------|-------------|
| `PatternObservation` | Tracks a detected action pattern (action, category, frequency, timestamps) |
| `Suggestion` | A user-facing suggestion with title, description, and workflow |
| `ProductivityEngine` | Observes events and manages patterns/suggestions |

#### Pattern Categories

| Category | Trigger Actions | Example Suggestion |
|----------|---------------|-------------------|
| `browsing` | `browser_search`, actions containing "browser" or "search" | "Automate browser search?" |
| `application` | `launch_application`, actions containing "open" | "Quick-launch {app}?" |
| `file_access` | `read_file`, actions containing "file" | "Create file access shortcut?" |
| `communication` | `compose_email`, actions containing "email" or "mail" | "Automate email task?" |
| `notification` | `send_notification` | Implicitly categorized |
| `general` | Everything else | "Automate repetitive task?" |

#### Configuration (Environment Variables)

| Variable | Default | Description |
|----------|---------|-------------|
| `HELIX_PRODUCTIVITY_MIN_FREQUENCY` | `3` | Minimum occurrences before suggesting automation |
| `HELIX_PRODUCTIVITY_MAX_PATTERNS` | `50` | Max tracked patterns |
| `HELIX_PRODUCTIVITY_MAX_SUGGESTIONS` | `20` | Max pending suggestions |
| `HELIX_PRODUCTIVITY_OBSERVATION_WINDOW` | `3600` | Window (seconds) for frequency counting |

#### Events

| Subscribes To | Publishes |
|--------------|-----------|
| `automation.completed` | `productivity.suggestion` |
| `productivity.suggestion.accept` | `productivity.workflow.create` |
| `productivity.suggestion.dismiss` | |
| `system.state.change` | |

---

## Event Flow Examples

### Low Risk — Auto-Dispatch

**User says:** "search for python tutorials"

```
1. PlannerEngine._build_steps("search for python tutorials")
   → Step: browser_search, params: {"query": "python tutorials"}, risk_level: "low"
      ↓
2. AutomationEngine._handle_execute
   → risk_level="low" → _execute_action() → action.execute
      ↓
3. ActionExecutor._browser_search → opens browser URL
   → Publishes automation.result
      ↓
4. ProductivityEngine._record_action("browser_search")
```

### Medium Risk — Permission Gate

**User says:** "send email to john@example.com"

```
1. PlannerEngine._build_steps("send email to john@example.com")
   → Step: compose_email, risk_level: "medium"
      ↓
2. AutomationEngine._handle_execute
   → risk_level="medium" → _request_permission()
   → Generates permission_id → publishes automation.permission_needed
      ↓
3. UI/Voice shows: "Allow Helix to compose email?"
   → User approves → publishes permission.granted
      ↓
4. AutomationEngine._handle_permission_granted
   → _execute_action() → action.execute
      ↓
5. ActionExecutor._compose_email → opens mail client
```

### High Risk — Double-Checkpoint

**User says:** "open file C:\Windows\System32\config"

```
1. PlannerEngine._build_steps("open file C:\Windows\System32\config")
   → _validate_task_safety() → path matches SystemRoot → raises ValueError
   → Publishes plan.failed → "Access denied: blocked system path"
```

**User says:** "read /etc/sensitive.conf" (hypothetical allowed path but high risk)

```
1. PlannerEngine → Step: read_file, risk_level: "high"
      ↓
2. AutomationEngine._handle_execute
   → risk_level="high" → _request_confirmation()
   → Publishes automation.confirm.request
      ↓
3. Voice: "Are you sure you want to read /etc/sensitive.conf?"
   → User confirms: publishes automation.confirm.response (confirmed=True)
      ↓
4. AutomationEngine → _request_permission() → permission gate
   → User approves → dispatches action
```

---

## Testing

Unit tests cover all three sub-modules:

| File | Tests |
|------|-------|
| `tests/unit/test_planner_engine.py` | Intent mapping, risk classification, guardrail validation |
| `tests/unit/test_automation_engine.py` | Permission flow, medium/high risk gating, confirm/deny |
| `tests/unit/test_action_executor.py` | Action dispatch, URL/email/file validation, rate limiting |

Run all action module tests:
```bash
HELIX_DEV_MODE=true python -m pytest tests/unit/test_planner_engine.py tests/unit/test_automation_engine.py tests/unit/test_action_executor.py -v
```

Note: Tests use `source="test"` which requires `HELIX_DEV_MODE=true` to pass the trusted-source check.

---

## Resource Budget

Per the HELIX architecture specs:

| Metric | Budget | Notes |
|--------|--------|-------|
| CPU | <20% | Mostly idle; brief spikes during `subprocess` calls |
| RAM | <500MB | In-memory action records, patterns, suggestions capped by env vars |

---

## Future Enhancements

- Add more known applications to `_KNOWN_APPS` and `_KNOWN_APP_PATHS`
- Support app launch via Windows Start Menu shortcuts
- Add voice feedback for action results (beyond logging)
- Implement suggestion acceptance workflow into actual automation creation
- Add `depends_on` step ordering in the planner
