import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.dashboard_routes import router as dashboard_router
from api.routes import router as intel_router
from api.tools_status import router as tools_router
from api.ws import router as ws_router
from tools.registry import registry

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    registry.reload()
    yield


app = FastAPI(
    title="SOCMINT Intelligence Platform",
    description="Production-grade OSINT collection, normalization, and tool fusion backend",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tools_router)
app.include_router(intel_router)
app.include_router(dashboard_router)
app.include_router(ws_router)


@app.get("/")
async def root():
    return {
        "service": "SOCMINT Intelligence Platform",
        "version": "1.0.0",
        "endpoints": {
            "tool_status": "/api/tools/status",
            "username_search": "/api/intel/username-search",
            "email_intel": "/api/intel/email",
            "domain_intel": "/api/intel/domain",
            "infra_intel": "/api/intel/infra",
            "image_intel": "/api/intel/image",
            "correlate": "/api/intel/correlate",
            "graph": "/api/intel/graph",
            "investigate": "/api/dashboard/investigate",
            "copilot": "/api/dashboard/copilot",
            "export": "/api/dashboard/export",
            "websocket": "/ws/investigate",
        },
    }


@app.get("/health")
async def health():
    return {"status": "ok"}
