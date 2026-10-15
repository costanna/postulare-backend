from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.routers import applications, auth, events, matches, profile, stats
from app.routers.outreach import cv_router, router as outreach_router
from app.services.keep_awake import keep_awake_configured, start_keep_awake


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Keep-awake estilo woke-dyno (solo si KEEP_AWAKE_ENABLED + KEEP_AWAKE_URL).
    if keep_awake_configured(settings.KEEP_AWAKE_ENABLED, settings.KEEP_AWAKE_URL):
        start_keep_awake(settings.KEEP_AWAKE_URL, settings.KEEP_AWAKE_MINUTES)
    yield


app = FastAPI(title=settings.PROJECT_NAME, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(profile.router)
app.include_router(applications.router)
app.include_router(events.router)
app.include_router(matches.router)
app.include_router(stats.router)
app.include_router(outreach_router)
app.include_router(cv_router)


@app.api_route("/health", methods=["GET", "HEAD"], tags=["health"])
def health() -> dict:
    return {"status": "ok"}


# Same handler as /health, under a second path: some ad blockers and antivirus
# web shields treat "/health" as a tracking/telemetry beacon and silently drop
# the request (net::ERR_BLOCKED_BY_CLIENT), which stalls the frontend's wake-up
# ping. /health stays as-is because Render's own healthCheckPath (render.yaml)
# points at it; the frontend pings this one instead.
@app.api_route("/warmup", methods=["GET", "HEAD"], tags=["health"])
def warmup() -> dict:
    return {"status": "ok"}
