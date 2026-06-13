# SOCMINT Investigator Dashboard

Professional CID-facing UI for the SOCMINT Intelligence Platform.

## Stack

- React 19 + Vite + TypeScript
- TailwindCSS v4
- Zustand (state)
- Cytoscape.js (relationship graph)
- WebSocket live tool progress

## Quick Start

```bash
# Terminal 1 — Backend
cd /home/ai/Desktop/hackathon
source .venv/bin/activate
uvicorn main:app --reload --host 127.0.0.1 --port 8000

# Terminal 2 — Frontend
cd frontend
npm run dev
```

Open http://localhost:5173

## Backend Integration

| UI Feature | Backend Endpoint |
|------------|------------------|
| Start Investigation | `WS /ws/investigate` |
| Tool Status | `GET /api/tools/status` |
| Human Review | `POST /api/dashboard/review` |
| AI Copilot | `POST /api/dashboard/copilot` |
| Evidence Export | `POST /api/dashboard/export` |
| Sync Investigate | `POST /api/dashboard/investigate` |

Legacy intel endpoints (`/api/intel/*`) remain available for Postman/API use.

## Environment

Optional `.env` in project root:

```
HF_TOKEN=hf_xxx          # Faster HuggingFace model downloads (text similarity)
CORS_ORIGINS=http://localhost:5173
```

## Production Build

```bash
npm run build
npm run preview
```
