from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from api.routes import router
from api.dependencies import get_job_store

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.
    On startup, it attempts to recover any background analysis jobs that were 
    interrupted by a server crash or restart.
    """
    store = get_job_store()
    try:
        store.recover_orphaned_jobs()
        print("[Startup] Recovered orphaned background analysis jobs.")
    except Exception as e:
        print(f"[Startup] Error recovering jobs: {e}")
    yield

app = FastAPI(title="Serinity", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(router)