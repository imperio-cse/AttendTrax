# =============================================================================
# main.py  –  FastAPI application entry point
# =============================================================================
import threading
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from config import get_settings
from database import init_db
from routers import auth_router, faculty_router, student_router, admin_router, leave_router, executive_router
from sheets import warm_up_cache

cfg = get_settings()

app = FastAPI(
    title="AttendTrax API",
    description="Student Attendance Management System – FastAPI backend",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

@app.on_event("startup")
async def startup_event():
    # Initialize SQLite/PostgreSQL schema if not already present
    await init_db()
    # Warm up Google Sheets cache asynchronously in background thread
    threading.Thread(target=warm_up_cache, daemon=True).start()

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

