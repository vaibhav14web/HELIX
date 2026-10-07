# HELIX — Elevated Helper Policy & Privilege Boundary Architecture

> **Policy:** HELIX main PCOS process MUST always run as a restricted user (`asInvoker`). It must never request or require Administrator elevation (`requireAdministrator`).

---

## 1. Core Principles

1. **Least Privilege by Default**: The primary backend API server (`api/main.py`), memory modules, context engines, and action engines run under standard user rights without elevated UAC permissions.
2. **No Inline Elevation**: No action type in `action_executor` or `automation_engine` may use inline UAC prompts (`runas` verb or elevated PowerShell invocation) to elevate the main backend process.
3. **Helper-Process Pattern**: If a specific system action strictly requires elevated Administrator privileges in the future:
   - The action MUST spawn a separate, minimal, explicitly-scoped helper process (e.g. `HELIX_ElevatedHelper.exe`).
   - The helper process MUST validate inputs, execute only the single requested operation with least privilege, and terminate immediately.
   - The main HELIX PCOS process remains strictly un-elevated at all times.

---

## 2. Windows Application Manifest Compliance

The main process manifest is located at `deployment/helix.manifest` with:
```xml
<requestedExecutionLevel level="asInvoker" uiAccess="false"/>
```
This guarantees that Windows OS launch will never prompt for UAC elevation or run the main process as Administrator.
