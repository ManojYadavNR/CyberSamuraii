# Backend ↔ Frontend Coverage Matrix

## All Backend Endpoints

| Backend Endpoint | Frontend UI | Component |
|------------------|-------------|-----------|
| `GET /health` | ✅ | `SystemStatus` (header) |
| `GET /` | — | API info only (no UI needed) |
| `GET /api/tools/status` | ✅ | `SystemStatus`, `ToolsPanel` |
| `GET /api/tools/status/{tool}` | ✅ | `ToolsPanel` (click tool) |
| `WS /ws/investigate` | ✅ | `SearchBar` → `investigate.ts` |
| `POST /api/dashboard/investigate` | ✅ | Used by WS (sync alt exists) |
| `GET /api/dashboard/investigations/{id}` | ✅ | `LoadInvestigation` |
| `POST /api/dashboard/review` | ✅ | `ReviewPanel` |
| `GET /api/dashboard/review/{id}` | ✅ | `ReviewPanel` (auto-load) |
| `POST /api/dashboard/copilot` | ✅ | `CopilotChat` |
| `POST /api/dashboard/export` | ✅ | `ExportPanel` |
| `POST /api/intel/username-search` | ✅ | Via WS investigate |
| `POST /api/intel/email` | ✅ | Via WS investigate |
| `POST /api/intel/domain` | ✅ | Via WS investigate |
| `POST /api/intel/infra` | ✅ | Via WS investigate (phone/infra) |
| `POST /api/intel/image` | ✅ | Via WS investigate |
| `POST /api/intel/correlate` | ✅ | `EvidencePanel` → Re-correlate |
| `POST /api/intel/graph` | ✅ | `GraphView` → Rebuild Graph |

## Backend Response Fields → UI

| Field | UI Location |
|-------|-------------|
| `tool_results[]` + `data` | `EvidencePanel` → Tool Hits |
| `fusion.deduplicated_entities` | `EvidencePanel` → Entities |
| `fusion.evidence_map` | `EvidencePanel` → Provenance |
| `fusion.raw_evidence_index` | `EvidencePanel` → Provenance |
| `correlation.clusters` | `ResultsPanel`, `GraphView` |
| `correlation.signal_availability` | `ResultsPanel` |
| `correlation.warnings` | `ResultsPanel` |
| `correlation.explainability` | `InvestigatorPanel` |
| `graph.influence_scores` | `GraphView` → Influence tab |
| `graph.clusters` (Louvain) | `GraphView` → Communities tab |
| `graph.suspicious_networks` | `InvestigatorPanel`, `GraphView` |
| `graph.neo4j_exported` | `GraphView` footer |
| `confirmed_findings` | `EvidencePanel` → Email Intel |
| `public_profile_data` | `EvidencePanel` → Email Intel |
| `investigation_leads` | `EvidencePanel` → Email Intel |
| `scan_summary` | `EvidencePanel` → Email Intel |
| `merged_results` | `EvidencePanel` → Tool Hits |
| `warnings` / `query_normalized` | `ResultsPanel` |
| `confidence_raw_inputs` | `InvestigatorPanel` |
| `total_execution_time_ms` | `ResultsPanel` |

## Optional Backend (no UI required)

| Feature | Notes |
|---------|-------|
| PostgreSQL `DATABASE_URL` | Server-side persistence; investigation reload via ID |
| Neo4j `NEO4J_URI` | Auto-export; status shown in Graph tab |
