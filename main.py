from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
import asyncio
from api.routes import router
from api.routers.auth import router as auth_router
from api.dependencies import patient_service

async def session_sweeper_task():
    """Background task to sweep idle sessions every 5 minutes."""
    while True:
        try:
            # Sweep sessions inactive for 30 minutes
            patient_service.sweep_abandoned_sessions(timeout_minutes=30)
        except Exception as e:
            print(f"[Sweeper Error] {e}")
        # Sleep for 5 minutes
        await asyncio.sleep(300)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Start the background sweeper
    sweeper = asyncio.create_task(session_sweeper_task())
    yield
    # Shutdown: Cancel the task
    sweeper.cancel()
    try:
        await sweeper
    except asyncio.CancelledError:
        pass

app = FastAPI(title="Serinity", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(auth_router)
app.include_router(router)