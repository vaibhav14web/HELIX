# BUG-001: CORS Preflight OPTIONS Returning 400 Bad Request

**Date Found:** 2026-06-24
**Status:** Fixed
**Severity:** Medium (non-blocking, all real requests worked)
**Module:** `backend/server.py`
**Found By:** Test run — frontend health check + chat preflight requests

---

## Symptom

Backend logs showed:

```
INFO:     127.0.0.1:51845 - "OPTIONS /health HTTP/1.1" 400 Bad Request
INFO:     127.0.0.1:53916 - "OPTIONS /health HTTP/1.1" 400 Bad Request
INFO:     127.0.0.1:53216 - "OPTIONS /chat HTTP/1.1" 400 Bad Request
```

Three different clients were getting `400` on OPTIONS requests to both `/health` and `/chat`. The first preflight (from browser) returned `200` correctly.

---

## Root Cause

Starlette's `CORSMiddleware` rejects preflight requests that are missing the `Access-Control-Request-Method` header with a `400` response. Some HTTP clients and browser extensions send bare OPTIONS requests without this header, expecting a `200` regardless.

The relevant Starlette source logic:

```python
if method == "OPTIONS" and "access-control-request-method" in headers:
    # Handle preflight → set CORS headers, return 200
else:
    # Not a preflight → pass through to handler
```

When the header was missing, Starlette treated it as a non-preflight OPTIONS and passed it to the route handler. Since no explicit OPTIONS handler existed for `/health` or `/chat`, FastAPI returned `405 Method Not Allowed`, and CORSMiddleware converted this to `400`.

---

## Fix Applied

Two changes were made to `backend/server.py`:

### 1. CatchAllOptionsMiddleware (ASGI-level)

A custom ASGI middleware was added that intercepts **all** OPTIONS requests **before** they reach CORSMiddleware:

```python
class CatchAllOptionsMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["method"] == "OPTIONS":
            headers = dict(scope.get("headers", []))
            has_origin = b"origin" in headers
            has_cors_method = b"access-control-request-method" in headers
            if has_origin and has_cors_method:
                # Proper browser preflight → let CORSMiddleware handle it
                await self.app(scope, receive, send)
                return
            # Malformed/bare OPTIONS → return 200 without CORS headers
            response = Response(status_code=200)
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)
```

**Logic:**
- Proper preflights (Origin + Access-Control-Request-Method) → pass through to CORSMiddleware which sets correct CORS headers
- Bare OPTIONS (browser extensions, CLI tools, etc.) → return 200 immediately

### 2. data-testid Attributes Added to Chat Page

For better testability, `data-testid="send-btn"` and `data-testid="chat-input"` were added to `ui/app/chat/page.tsx`.

---

## Verification

### Before fix
```
$ curl -s -o NUL -w "%{http_code}" -X OPTIONS http://localhost:8000/health
400
```

### After fix
```
$ curl -s -o NUL -w "%{http_code}" -X OPTIONS http://localhost:8000/health
200
$ curl -s -o NUL -w "%{http_code}" -X OPTIONS http://localhost:8000/chat
200
$ curl -s -o NUL -w "%{http_code}" -X OPTIONS http://localhost:8000/nonexistent
200
```

### CORS headers preserved for proper preflights
```python
def test_cors_preflight():
    resp = requests.options(
        f"{BASE_URL}/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] == "http://localhost:3000"
```

### Full test suite passes
```
Frontend E2E:  18/18 passed
Backend API:    3/3  passed
Unit tests:    79/79 passed
```

---

## Files Changed

| File | Change |
|------|--------|
| `backend/server.py` | Added `CatchAllOptionsMiddleware`, imported `Response` from `starlette.responses` |
| `ui/app/chat/page.tsx` | Added `data-testid="send-btn"` and `data-testid="chat-input"` |
| `ui/playwright.config.ts` | New — Playwright E2E config |
| `ui/e2e/chat.spec.ts` | New — 8 chat page tests |
| `ui/e2e/smoke.spec.ts` | New — 10 page load smoke tests |
| `ui/e2e/fixtures/test-data.ts` | New — mock API responses |
| `tests/e2e/test_backend_api.py` | New — 3 backend API tests |
| `ui/package.json` | Added `test:e2e`, `test:e2e:ui`, `test:e2e:debug` scripts |
| `ui/.gitignore` | Added `playwright-report/` and `test-results/` |
