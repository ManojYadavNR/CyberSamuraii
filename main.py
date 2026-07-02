import os

# Quiet TensorFlow / ONNX / CUDA noise on CPU-only machines (not errors).
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
os.environ.setdefault("TF_ENABLE_ONEDNN_OPTS", "0")
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")
os.environ.setdefault("ORT_LOG_SEVERITY_LEVEL", "3")

from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.auth_routes import router as auth_router
from api.notifications_routes import router as notifications_router
from api.dashboard_routes import router as dashboard_router
from api.enterprise_routes import router as enterprise_router
from api.routes import router as intel_router
from api.tools_status import router as tools_router
from api.ws import router as ws_router
from tools.registry import registry

load_dotenv()


def _warmup_phone() -> None:
    from services.phone_intelligence.runtime import warmup_phone_stack

    warmup_phone_stack()


@asynccontextmanager
async def lifespan(app: FastAPI):
    import asyncio

    from services.enterprise.db import enterprise_enabled, init_enterprise_db
    from services.enterprise.users import seed_admin_user, seed_demo_users
    from services.image_intelligence.runtime import warmup_ml_stack

    if enterprise_enabled():
        init_enterprise_db()
        seed_admin_user()
        seed_demo_users()

    try:
        from services.phone_intelligence.runtime import ensure_phone_stack

        ensure_phone_stack()
    except Exception:
        pass

    warmup_ml_stack()
    # Preload tensorflow/torch in background so first image run doesn't stall the WS.
    loop = asyncio.get_running_loop()
    loop.run_in_executor(None, lambda: warmup_ml_stack(full=True))
    loop.run_in_executor(None, _warmup_phone)
    registry.reload()
    from services.osint_registry.registry import registry as osint_registry

    osint_registry.reload()
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

app.include_router(auth_router)
app.include_router(notifications_router)
app.include_router(enterprise_router)
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
            "osint_registry": "/api/tools",
            "osint_reload": "/api/tools/reload",
            "username_search": "/api/intel/username-search",
            "email_intel": "/api/intel/email",
            "domain_intel": "/api/intel/domain",
            "infra_intel": "/api/intel/infra",
            "image_intel": "/api/intel/image",
            "image_upload": "/api/intel/image/upload",
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
