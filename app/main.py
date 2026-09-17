from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.routers import applications, auth, events, matches, profile, stats

app = FastAPI(title=settings.PROJECT_NAME)

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


@app.get("/health", tags=["health"])
def health() -> dict:
    return {"status": "ok"}
