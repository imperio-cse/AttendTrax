# =============================================================================
# main.py  –  FastAPI application entry point
# =============================================================================
import os
import time
import logging
import threading
import urllib.request
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from config import get_settings
from database import init_db
from routers import auth_router, faculty_router, student_router, admin_router, leave_router, executive_router
from sheets import warm_up_cache

logger = logging.getLogger("attendtrax.main")
cfg = get_settings()

app = FastAPI(
    title="AttendTrax API",
    description="Student Attendance Management System – FastAPI backend",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

def _render_keep_alive():
    """
    Background daemon that pings the Render service every 9 minutes (540s)
    to prevent free-tier cloud containers from entering idle hibernation.
    Automatically detects RENDER_EXTERNAL_URL if running on Render cloud.
    """
    time.sleep(30)  # Initial grace period after startup
    while True:
        try:
            render_url = os.getenv("RENDER_EXTERNAL_URL")
            target_url = f"{render_url.rstrip('/')}/health" if render_url else "http://127.0.0.1:8000/health"
            req = urllib.request.Request(
                target_url,
                headers={"User-Agent": "AttendTrax-KeepAlive/1.0"}
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                logger.info(f"[KeepAlive] Health ping successful ({target_url}): {resp.status}")
        except Exception as e:
            logger.debug(f"[KeepAlive] Ping exception: {e}")
        time.sleep(540)  # Ping every 9 minutes (Render idle threshold is 15 minutes)

@app.on_event("startup")
async def startup_event():
    # Initialize SQLite/PostgreSQL schema if not already present
    await init_db()
    # Auto-hydrate database if fresh or missing core roles (e.g. on Render container spin-up)
    try:
        from hydrate_db import ensure_hydrated
        await ensure_hydrated()
    except Exception as e:
        print(f"[Hydration Hook Warning] {e}")
    # Warm up Google Sheets cache asynchronously in background thread
    threading.Thread(target=warm_up_cache, daemon=True, name="sheets-warmup").start()
    # Start zero-sleep keep-alive daemon
    threading.Thread(target=_render_keep_alive, daemon=True, name="attendtrax-keepalive").start()

# ── GZip Compression Middleware (Ultra-fast payload delivery) ────────────────
app.add_middleware(GZipMiddleware, minimum_size=500)

# ── Security Headers Middleware ───────────────────────────────────────────────
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        # Prevent MIME-sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"
        # Prevent clickjacking / frame embedding
        response.headers["X-Frame-Options"] = "DENY"
        # Enable browser XSS filter
        response.headers["X-XSS-Protection"] = "1; mode=block"
        # Control referrer information leak
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        # Restrict dangerous browser features
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        return response

app.add_middleware(SecurityHeadersMiddleware)

# ── CORS ──────────────────────────────────────────────────────────────────────
origins = [o.strip() for o in cfg.ALLOWED_ORIGINS.split(",") if o.strip()]
for default_origin in [
    "http://localhost:5500",
    "http://127.0.0.1:5500",
    "http://localhost:3000",
    "https://attendtrax-frontend.vercel.app",
    "https://attendtrax.vercel.app"
]:
    if default_origin not in origins:
        origins.append(default_origin)

# If wildcard is requested, configure origins cleanly
has_wildcard = "*" in origins
if has_wildcard:
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"^https?://.*",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Retry-After"],
    )
else:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_origin_regex=r"https://.*\.vercel\.app",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Retry-After"],
    )

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(auth_router.router)
app.include_router(faculty_router.router)
app.include_router(student_router.router)
app.include_router(admin_router.router)
app.include_router(executive_router.router)
app.include_router(leave_router.router)


@app.get("/")
async def root():
    return {"service": "AttendTrax API", "status": "running"}


@app.get("/health")
async def health():
    return {"status": "ok"}
