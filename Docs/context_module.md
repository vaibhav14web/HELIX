# Context Module

**Layer:** Context Layer  
**Status:** Implemented  
**Last Updated:** 2026-06-26  

---

## Overview

The Context Layer builds a complete picture of the user's current environment by observing browser activity, open files, system metrics, and active projects. It operates strictly through the **Event Bus** with no direct inter-module imports.

Key characteristics:
- **Lazy-start** — engines boot on first request, not at system startup (N9 power efficiency)
- **Event-driven** — no polling loops except the system monitor's configurable tick
- **Cache-aware** — the `ContextAggregator` caches sub-engine responses with a configurable TTL
- **State-aware** — respects `system.state.change` (`sleep`, `background`, `conversation`) to pause/resume activity
- **Resource-bounded** — the entire Context Layer budgets at **<5% CPU** and **<500MB RAM**

---

## Architecture

```
User / UI / Orchestrator
        ↓
  context.request          (entry point)
        ↓
  ContextAggregator        (fans out, merges, caches)
        ↓
  ┌─────────┬──────────┬──────────────────┬─────────────┐
  │ Browser │   File   │   System Monitor │   Project   │
  │ Engine  │ Engine   │      Engine      │   Engine    │
  └─────────┴──────────┴──────────────────┴─────────────┘
        ↓
  context.provided         (unified payload)
        ↓
  Downstream consumers (Memory, Companion, Action)
```

### Sub-Module Dependency Graph

```
Event Bus ↔ ContextAggregator ↔ Event Bus ↔ { BrowserEngine, FileIntelligenceEngine, ProjectEngine, SystemMonitorEngine }
```

No sub-engine depends on another. The aggregator is the sole composition point.

---

## Sub-Modules

### 1. ContextAggregator (`context/context_aggregator/context_aggregator.py`)

Event-driven orchestrator that fans out `context.request` to all sub-engines, collects their responses, maintains a time-bounded cache, and publishes the unified `context.provided` payload.

#### Classes

| Class | Description |
|-------|-------------|
| `ContextAggregator` | Main orchestrator — subscribes to sub-engine responses, manages cache TTL, publishes merged context |

#### Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `HELIX_CONTEXT_CACHE_TTL_SECONDS` | `30` | Max age (seconds) for a cached full-context before refresh |

#### Events

| Subscribes To | Publishes |
|--------------|-----------|
| `context.request` | `context.provided` |
| `context.update` | |
| `system.state.change` | |
| `context.browser.provided` | |
| `context.browser.history.provided` | |
| `context.file.provided` | |
| `context.file.recent.provided` | |
| `context.file.project_detected` | |
| `system.monitor.provided` | |
| `system.monitor.tick` | |
| `project.opened` | |
| `project.switched` | |
| `project.closed` | |

#### Cache Behavior

- On `context.request`: returns cached context immediately if `now - last_full_context_time < TTL`.
- On cache miss / force refresh: fans out parallel requests, yields briefly (0.1s) for in-process EventBus delivery, then publishes whatever responses have arrived.
- On `project.switched`: invalidates file and recent-files cache timestamps so the next request fetches fresh data.

---

### 2. BrowserEngine (`context/browser_engine/browser_engine.py`)

Discovers currently visible browser tabs via Win32 window enumeration and reads browser history from Chromium-based SQLite `History` files (read-only copy to avoid lock conflicts).

#### Classes

| Class | Description |
|-------|-------------|
| `BrowserEngine` | Handles tab enumeration, history reading, and URL launching |

#### Supported Browsers

| Browser | Window Title Match | History DB Path |
|---------|-------------------|-----------------|
| Chrome | “Google Chrome” / “- Chrome” | `%LOCALAPPDATA%\Google\Chrome\User Data\Default\History` |
| Edge | “Microsoft Edge” | `%LOCALAPPDATA%\Microsoft\Edge\User Data\Default\History` |
| Firefox | “Mozilla Firefox” / “- Firefox” | Detected by title only (no SQLite history mapping) |
| Opera | “- Opera” | Detected by title only |
| Brave | “- Brave” | Detected by title only |

#### Events

| Subscribes To | Publishes |
|--------------|-----------|
| `context.browser.request` | `context.browser.provided` |
| `context.browser.history` | `context.browser.history.provided` |
| `context.browser.open_url` | `context.browser.url_opened` |
| | `context.browser.error` |

#### Implementation Notes

- Tab enumeration uses `ctypes.windll.user32.EnumWindows` + `GetWindowTextW` — no external dependencies.
- History reads from a temp-file copy of the locked SQLite database (`file:...?mode=ro`, URI mode).
- Title clean suffix stripping handles both hyphen and em-dash separators.

#### Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `HELIX_BROWSER_PROFILE_PATH` | `""` | Custom profile path override for History DB |
| `HELIX_BROWSER_HISTORY_LIMIT` | `20` | Max history entries to return per request |

---

### 3. FileIntelligenceEngine (`context/file_intelligence_engine/file_intelligence_engine.py`)

Provides awareness of the filesystem: file/directory metadata, recursive listings (bounded depth), recently modified files, and project-type detection from marker files.

#### Classes

| Class | Description |
|-------|-------------|
| `FileIntelligenceEngine` | File system observer with scanning, project detection, and ignore-list filtering |

#### Project Type Detection

| Marker File(s) | Primary Type |
|----------------|-------------|
| `pyproject.toml`, `setup.py`, `requirements.txt`, `Pipfile` | `python` |
| `package.json` | `node` |
| `tsconfig.json` | `typescript` |
| `Cargo.toml` | `rust` |
| `go.mod` | `go` |
| `pom.xml` | `java-maven` |
| `build.gradle` | `java-gradle` |
| `CMakeLists.txt` | `cmake` |
| `Makefile` | `make` |
| `*.sln`, `*.csproj` | `dotnet` |
| `composer.json` | `php` |
| `Gemfile` | `ruby` |

#### Events

| Subscribes To | Publishes |
|--------------|-----------|
| `context.file.request` | `context.file.provided` |
| `context.file.list` | `context.file.listed` |
| `context.file.recent` | `context.file.recent.provided` |
| `context.file.detect_project` | `context.file.project_detected` |
| | `context.file.error` |

#### Filesystem Behavior

- All blocking I/O runs in `asyncio` thread-pool executors.
- Directories named in `_DEFAULT_IGNORE` (plus `HELIX_FILE_IGNORE_DIRS`) are skipped during walks.
- Recursive depth capped at `HELIX_FILE_MAX_DEPTH` (default 4).
- Recent-file scan returns capped at 100 entries.

#### Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `HELIX_FILE_WATCH_PATHS` | `.` | Semicolon-delimited search roots |
| `HELIX_FILE_IGNORE_DIRS` | `""` | Semicolon-delimited extra ignore directories |
| `HELIX_FILE_RECENT_MINUTES` | `30` | Lookback window for recent-file queries |
| `HELIX_FILE_MAX_DEPTH` | `4` | Max recursion depth for directory listings |

---

### 4. ProjectEngine (`context/project_engine/project_engine.py`)

Manages the lifecycle of known projects: creates, opens, closes, tracks open/close counts, detects project roots, and persists session metadata (active files, last conversation ID) to disk.

#### Classes

| Class | Description |
|-------|-------------|
| `ProjectEngine` | Project catalog with lifecycle management and JSON persistence |

#### Project Root Markers

| Marker | Detected Type |
|--------|--------------|
| `.git`, `.svn`, `.hg` | VCS root (type resolved by other markers) |
| `pyproject.toml`, `setup.py`, `setup.cfg` | `python` |
| `package.json` | `node` |
| `Cargo.toml` | `rust` |
| `go.mod` | `go` |
| `pom.xml` | `java` |
| `build.gradle` | `java` |
| `CMakeLists.txt` | `cmake` |
| `*.sln`, `*.csproj` | `dotnet` |
| `composer.json` | `php` |
| `Gemfile` | `ruby` |

#### Events

| Subscribes To | Publishes |
|--------------|-----------|
| `project.create` | `project.created` |
| `project.open` | `project.opened`, `project.switched` |
| `project.close` | `project.closed` |
| `project.list` | `project.listed` |
| `project.detect` | `project.detected` |
| `project.update_session` | |
| | `project.error` |

#### Persistence

- Projects are saved to `HELIX_PROJECT_PATH/projects.json` (UTF-8 JSON).
- On shutdown, the active project's `last_closed` timestamp is written before exit.

#### Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `HELIX_PROJECT_PATH` | `<cwd>/data/projects` | Root directory for project catalog JSON |

---

### 5. SystemMonitorEngine (`context/system_monitor_engine/system_monitor_engine.py`)

Collects real-time and periodic system metrics: CPU, memory, battery, disk usage, and GPU stats (via `nvidia-smi`). Publishes an on-demand `system.monitor.provided` event and a background `system.monitor.tick` at a configurable interval. Detects system idle state based on sustained low CPU.

#### Classes

| Class | Description |
|-------|-------------|
| `SystemMonitorEngine` | Metric collector with idle detection and GPU telemetry |

#### Metrics Collected

| Category | Fields |
|----------|--------|
| CPU | `cpu_percent` |
| Memory | `total`, `used`, `available`, `percent` |
| Battery | `percent`, `plugged` (if available) |
| Disk | `total`, `used`, `free`, `percent` |
| GPU | `utilization_percent`, `memory_used_mb`, `memory_total_mb`, `temperature_c` |
| Idle | `is_idle`, `idle_seconds` |

#### Events

| Subscribes To | Publishes |
|--------------|-----------|
| `system.monitor.request` | `system.monitor.provided` |
| `system.state.change` | |
| | `system.monitor.tick` |
| | `system.idle.detected` |

#### Idle Detection Logic

- CPU must remain below `HELIX_IDLE_CPU_THRESHOLD` for `HELIX_IDLE_DURATION_SECONDS` consecutive seconds before `is_idle=True`.
- `system.idle.detected` is published when idle is confirmed.

#### Chipsets / Tooling

| Platform | Tool | Notes |
|----------|------|-------|
| NVIDIA GPUs | `nvidia-smi` | Non-blocking 2s subprocess timeout |
| All platforms | `psutil` | CPU, memory, battery, disk |

#### Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `HELIX_SYSTEM_MONITOR_INTERVAL` | `30` | Seconds between background `system.monitor.tick` events |
| `HELIX_IDLE_CPU_THRESHOLD` | `20` | CPU% below which the system is considered potentially idle |
| `HELIX_IDLE_DURATION_SECONDS` | `30` | Sustained low-CPU duration required to declare idle |
| `HELIX_RUNTIME_PATH` | `<cwd>` | Fallback path for disk-usage measurement |

---

## Testing

Unit tests live in `tests/unit/test_context_aggregator.py`. Run with:

```bash
python -m pytest tests/unit/test_context_aggregator.py -v
```

Test coverage includes:
- Aggregator start/stop subscription lifecycle
- Cache freshness logic
- Sub-engine response handler wiring (browser, system, project)
- Project switch cache invalidation
- Sleep / conversation state transitions

---

## Resource Budget

Per the HELIX architecture specs (03_SAD.md + 01_HSD.md):

| Metric | Budget | Notes |
|--------|--------|-------|
| CPU | <5% | ContextLoader is event-driven; SystemMonitor is the only periodic loop (configurable interval) |
| RAM | <500MB | Sub-engine caches are bounded and TTL-managed by the Aggregator |
| Disk | — | No unbounded writes; project catalog is capped JSON; browser history reads copy-only |

Performance tuning defaults for the Context Layer:

| Setting | Default | Tuned Goal |
|---------|---------|-----------|
| `HELIX_CONTEXT_CACHE_TTL_SECONDS` | `30` | `120` |
| `HELIX_SYSTEM_MONITOR_INTERVAL` | `30` | `120` |
| `HELIX_FILE_MAX_DEPTH` | `4` | `4` (unchanged) |
| `HELIX_BROWSER_HISTORY_LIMIT` | `20` | `20` (unchanged) |

---

## Event Flow (End-to-End Example)

**Trigger:** UI calls for updated context.

```
1. orchestrator / UI publishes context.request (session_id="session-abc", correlation_id="corr-1")
       ↓
2. ContextAggregator._handle_request
   → Cache fresh? → Yes → Publish context.provided from cache → Done
   → Cache stale → Fan out parallel requests:
       • context.browser.request
       • system.monitor.request
       • project.list
       • context.file.recent (with project path)
       ↓
3. BrowserEngine._handle_request
   → EnumWin32 windows → [{"title": "README.md", "browser": "Chrome"}, ...]
   → Publishes context.browser.provided (corr-1)
       ↓
4. SystemMonitorEngine._handle_request
   → Collect metrics: cpu=12%, memory=3.1GB, is_idle=False
   → Publishes system.monitor.provided (corr-1)
       ↓
5. ProjectEngine._handle_list
   → Returns active project summary
   → Publishes (implicitly via project.opened cache path or direct list event)
       ↓
6. FileIntelligenceEngine._handle_recent
   → Walks project path up to max_depth
   → Returns recently modified files
   → Publishes context.file.recent.provided (corr-1)
       ↓
7. Aggregator responses arrive via EventBus subscription callbacks
   → _cache updated with timestamps
       ↓
8. Aggregator waits ~0.1s for in-process delivery, publishes context.provided
   Payload:
   {
     "session_id": "session-abc",
     "context": {
       "timestamp": ...,
       "browser": {"tabs": [...]},
       "browser_history": {"history": [...]},
       "system": {"cpu_percent": 12, "memory": {...}, "disk": {...}} ,
       "project": {"name": "...", "path": "...", "project_type": "python"},
       "files": {...},
       "recent_files": [...]
     }
   }
       ↓
9. Downstream consumers (Memory layer, Companion, Action layer) receive context.provided and update their own state.
```

---

## Future Enhancements

- Cross-platform tab enumeration (macOS `AXUIElement`, Linux `libwnck`)
- Browser history for Firefox / Safari / Opera via native DB formats
- File-watch daemon (inotify / FSEvents) instead of poll-recent for instant change detection
- Project auto-switch based on `recent_files` / active window hints
- Aggregated context diffing to publish `context.changed` only when meaningful fields differ
- Per-engine cache TTLs (e.g., system metrics TTL shorter than file TTL)
