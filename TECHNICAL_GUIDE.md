# SOCMINT Intelligence Platform — Technical Guide

Deep reference for architecture, concepts, and what happens in the backend for each input type. Use this for technical interviews and system walkthroughs.

---

## 1. What this platform is

SOCMINT (Social Media Intelligence) is an **investigation platform** for law-enforcement-style OSINT:

- Investigators submit a **target** (username, email, phone, domain, image, or multi-field).
- The backend **routes** the target to a **feature** (e.g. `username_search`, `image_intel`).
- A **registry** selects **tools** (Maigret, Sherlock, PhoneInfoga, InsightFace, etc.).
- Tools run **in parallel** with timeouts and failure isolation.
- Results are **normalized**, **fused** into entities, **correlated**, and optionally **expanded** via discovery hops.
- Live progress streams over **WebSocket**; the UI shows fusion, evidence, graph, and audit.

It is **not** a single scraper. It is an **orchestration + fusion** system over many OSINT and ML tools.

---

## 2. High-level architecture

```
┌─────────────┐     REST / WS      ┌──────────────────┐
│  React UI   │ ◄────────────────► │  FastAPI (main)  │
│  Vite :5173 │                    │  uvicorn :8000   │
└─────────────┘                    └────────┬─────────┘
                                            │
                    ┌───────────────────────┼───────────────────────┐
                    ▼                       ▼                       ▼
            InvestigationRunner      Enterprise (RBAC)         Tool Registry
                    │                  Auth / Cases / Audit      OSINT catalog
                    ▼
            ToolOrchestratorEngine
                    │
        ┌───────────┼───────────┬────────────┬────────────┐
        ▼           ▼           ▼            ▼            ▼
   Adapters    Fusion      Evidence     Correlation    Discovery
   (tools)     Engine      Engine       / Graph        (hops)
```

### Main layers

| Layer | Role | Key paths |
|---|---|---|
| **Frontend** | Login, cases, investigate UI, live progress | `frontend/src/` |
| **API** | REST + WebSocket entrypoints | `api/` |
| **Investigation runner** | End-to-end investigation lifecycle | `services/investigation_runner.py` |
| **Orchestrator** | Parallel tool execution, timeouts | `orchestrator/` |
| **Adapters** | One adapter per external/builtin tool | `adapters/` |
| **Services** | Fusion, evidence, image ML, phone, discovery | `services/` |
| **Schemas** | Pydantic models for API/results | `schemas/` |
| **Config** | RBAC, demo users, OSINT catalog | `config/` |
| **Enterprise** | Users, cases, assignments, audit | `services/enterprise/` |

---

## 3. Core concepts (interview vocabulary)

### 3.1 Input type vs feature

- **Input type**: what the user typed/uploaded (`username`, `email`, `phone`, `domain`, `image`, `infra`, `multi`).
- **Feature**: which investigation pipeline runs (`username_search`, `email_intel`, `infra_intel`, `domain_intel`, `image_intel`).

Mapping (`services/osint_registry/router.py`):

| Input | Feature |
|---|---|
| username | `username_search` |
| email | `email_intel` |
| phone / infra | `infra_intel` |
| domain | `domain_intel` |
| image | `image_intel` |

### 3.2 Tool / adapter

- A **tool** is an OSINT or ML capability (e.g. `maigret`, `insightface`).
- An **adapter** (`adapters/*.py`) wraps a tool: verify install, run with timeout, return a uniform `ToolResult`.
- Adapters implement `BaseAdapter.run()` → `_execute(query)`.

### 3.3 ToolResult → Entity → Fusion

1. Each tool returns `ToolResult` (`success`, `data[]`, `error`, `execution_time_ms`).
2. **Normalization** turns tool rows into comparable records.
3. **Fusion** merges rows into **entities** (account, email, phone, image, document, …) with sources, confidence, evidence.
4. **Deduplication** merges the same identity seen from multiple tools.
5. **Fusion score** summarizes overall confidence.

### 3.4 Wall clock / batch budget

Tools do **not** run forever:

- **Per-tool wall**: max time once a tool starts.
- **Batch wall**: max time for the whole tool group.
- On timeout: tool is marked failed/partial; investigation continues with what it has.

This prevents one hung model download from freezing the whole run (especially important for image ML).

### 3.5 Investigation modes

| Mode | Intent |
|---|---|
| **fast (Quick)** | Fewer tools, shorter budgets |
| **standard** | Default balanced run |
| **deep** | More tools, more discovery hops |
| **samurai** | Social-deep path (Instagram/Facebook via Samurai) |

Modes affect tool lists, timeouts, and whether **discovery expansion** runs.

### 3.6 Discovery / hops

After the seed investigation, **RecursiveDiscoveryEngine** can:

1. Extract **leads** from entities (emails, domains, avatars, handles).
2. **Route** each lead to a feature.
3. Run limited **hop** investigations (smaller tool sets, shorter walls).
4. Merge results back into the seed investigation.

Example: username → finds email → hop runs `email_intel` → finds more accounts.

### 3.7 Correlation & graph

- **Correlation**: links entities that likely belong to the same person (shared handles, emails, face embeddings, hashes).
- **Graph intelligence**: builds a knowledge graph (nodes = entities, edges = relationships) for the Intelligence Graph UI.

### 3.8 Evidence extraction

Post-fusion pass that:

- Pulls structured fields (bio, location, website, phones).
- Optionally runs **linguistic analysis** (language, sentiment, NER) on text artifacts.
- Builds an **identity profile** for the investigator UI.

### 3.9 RBAC (enterprise)

- Ranks **are** roles: DGP, ADGP, IGP, DIG, SP, DSP, PI, PSI, HC, PC (+ `SUPER_ADMIN`).
- Permissions come from `config/rbac.json` (permission matrix × case relationship).
- Case assignments define who is IO / supervisor / assistant on a case.
- Auth: JWT access + refresh tokens; audit log for actions.

### 3.10 Resource guard

Only one heavy investigation at a time by default (`MAX_CONCURRENT_INVESTIGATIONS`), with subprocess caps so laptops do not OOM.

---

## 4. End-to-end request flow

### 4.1 Live investigation (primary UI path)

```
UI SearchBar
  → WebSocket /ws/investigate  { query, query_type, investigation_mode, image_profile, access_token }
  → Auth check (start_investigation permission)
  → InvestigationRunner.run(...)
  → emit progress events (tool running/done, fusion, evidence, …)
  → final FeatureResult dumped to client
```

REST alternatives exist (`/api/intel/username-search`, `/api/intel/email`, `/api/intel/image`, …) for non-streaming calls.

### 4.2 Runner pipeline (all input types)

```
1. Parse input          parse_investigation_input / detect_query_type
2. Resolve mode         standard | fast | deep | samurai
3. Select feature       username_search | email_intel | …
4. Select tools         registry + profile (fast/deep/hop)
5. Run tools parallel   execute_tools_parallel (walls + concurrency)
6. Normalize + fuse     fuse_results / build_fusion_output
7. Feature-specific     image ML merge, email enrichment, phone merge, …
8. Evidence + identity  evidence_engine.extract, build_identity_profile
9. Correlation + graph  correlation_engine, graph_engine
10. Discovery (optional) RecursiveDiscoveryEngine.expand
11. Persist / cache     investigation record, optional Postgres
```

Progress events (examples): `start`, `tool`, `fusion`, `image_intelligence`, `reverse_image_discovery`, `evidence_extraction`, `discovery`, `done`, `error`, `cancelled`.

---

## 5. What happens for each input type

### 5.1 Username

**Detection:** handle-like token (not email/phone/domain/image path).

**Feature:** `username_search`

**Typical tools (standard/deep):**

| Tool | Purpose |
|---|---|
| `platform_probe` | Fast existence checks on priority platforms |
| `maigret` | Large site inventory username scan |
| `sherlock` | Classic username presence scanner |
| `social_analyzer` | Broader social footprint |
| `samurai` | Deep Instagram/Facebook (needs session cookies) |
| `google_dorking` | Search-engine dorks for the handle |

**Fast mode tools:** `platform_probe`, `maigret`, `sherlock` only.

**Backend steps:**

1. Normalize username (strip `@`, warnings for invalid shapes).
2. Run scanners in parallel with site caps (`MAIGRET_MAX_SITES`, `SHERLOCK_MAX_SITES`) to avoid OOM.
3. Stream partial hits (`scan_progress`, `collection_partial`).
4. Fuse accounts; **profile verification** may refine live URLs.
5. Evidence extraction + optional linguistic analysis on bios.
6. Discovery may pivot to emails, domains, avatars found on profiles.

**Output shape:** accounts with platform, URL, verification flags, sources, fusion scores.

---

### 5.2 Email

**Detection:** `user@domain.tld` pattern.

**Feature:** `email_intel`

**Typical tools:**

| Tool | Purpose |
|---|---|
| `holehe` | Which sites have an account for this email |
| `theharvester` | Public harvest (domains, names, related emails) |
| `spiderfoot` | Broader OSINT modules |
| `google_dorking` | Email-specific dorks |
| Gravatar / profile resolvers | Public profile photos and display names (service layer) |

**Backend steps:**

1. Run email tools in parallel.
2. `build_email_investigation` merges registrations, public profiles, breaches-style signals (as available).
3. Enrich confirmed findings (profile URLs, avatars).
4. Fuse into email + account entities.
5. Discovery may hop to usernames extracted from profiles.

**Output shape:** email entity, registered platforms, linked accounts, public profile metadata.

---

### 5.3 Phone number

**Detection:** digit-heavy phone-like string (region default often `IN` via `PHONE_DEFAULT_REGION`).

**Feature:** `infra_intel` (phone branch)

**Typical tools:**

| Tool | Purpose |
|---|---|
| `phoneinfoga` | Carrier/line-type/local formatting + scanners (local, googlesearch, googlecse) |
| `phone_social_intel` | Social footprint (ignorant, profile resolver, web search) |
| `google_dorking` | Phone dorks |

**PhoneInfoga stack:**

- Binary/API under `phoneNumber/phoneinfoga/`.
- Keys from `phoneNumber/phoneinfoga/.env` (e.g. `NUMVERIFY_API_KEY`) merged with project `.env`.
- Optional autostart (`PHONEINFOGA_AUTOSTART`).

**Backend steps:**

1. Normalize number (E.164-ish via phonenumbers).
2. PhoneInfoga local + optional Numverify + Google CSE.
3. Social/ignorant checks for messengers/social presence.
4. Web search for public mentions.
5. Longer walls (`PHONE_WALL_SEC`, `PHONE_SOCIAL_INTEL_WALL_SEC`) because phone OSINT is slow.

**Output shape:** line metadata (carrier, country, type), social hits, web mentions, entities with `source_tool` provenance.

---

### 5.4 Domain / infrastructure

**Detection:** domain-like hostname, or infra IP/host for infra path.

**Feature:** `domain_intel` or `infra_intel` (non-phone)

**Typical tools:**

| Tool | Purpose |
|---|---|
| `theharvester` | Emails/hosts related to domain |
| `spiderfoot` | Passive recon modules |
| `recon_ng` | Recon framework modules |
| `shodan` | Internet-facing services (needs `SHODAN_API_KEY`) |
| `google_dorking` | Domain dorks |
| Optional: `subfinder`, `amass`, `dnsrecon`, `whois` | Subdomains / DNS / WHOIS |

**Backend steps:**

1. Select domain vs infra tools from registry.
2. Parallel recon with feature walls.
3. Fuse hosts, emails, services, certificates (as tools provide).
4. Discovery may pivot to emails/usernames found on the domain.

---

### 5.5 Image

**Detection:**

- Local file path ending in `.jpg/.jpeg/.png/.gif/.webp` (must not be split on `/`).
- Or explicit `query_type: "image"` from upload API.

**Feature:** `image_intel`

**Upload path:** `POST /api/intel/image/upload` stores file → investigation uses local path.

#### Image tool groups (techniques)

| Group | Tools | What they extract |
|---|---|---|
| **Metadata** | `pillow`, `exiftool`, `hachoir`, `image_intel` | Size, format, EXIF, GPS flags |
| **Face** | `opencv_face`, `insightface`, `facenet`, (`deepface` in deep) | Face boxes, embeddings, age/gender signals |
| **OCR** | `tesseract`, `easyocr`, (`paddleocr` in deep) | Visible text → emails, phones, usernames, names |
| **Objects** | `yolo`, `clip`, (`grounding_dino` in deep) | Objects, scene labels, logos/uniforms cues |
| **Reverse image** | `google_lens`, `bing_visual`, `yandex_images`, `tineye` | Similar images / pages on the web |

#### Fast vs deep image profile

- **Fast:** metadata + primary face + OCR + YOLO/CLIP + reverse (DDGS-first, not only browser).
- **Deep:** full set including DeepFace, PaddleOCR, GroundingDINO, browser reverse uploads when needed.

#### Backend steps (image)

```
1. Resolve image source (local path or download URL)
2. Run image adapters in parallel
   - IO tools (metadata, reverse) concurrent
   - ML tools serialized on a single ML executor (RAM safety)
3. Each ML call has a hard timeout; stuck executor is reset
4. Fuse tool rows into findings/entities
5. ImageIntelligenceEngine merges findings (no re-run of modules already attempted)
6. ReverseImageDiscoveryEngine runs multi-source reverse search (capped)
7. Image correlation (hashes, face embeddings, matches)
8. Evidence extraction (OCR emails/phones become pivotable entities)
9. Discovery hops (standard/deep only; disabled in quick image mode)
```

**Why image used to “hang”:** ML models share one thread; asyncio timeout alone did not free that thread; image paths were mis-parsed as multi-username. Fixed with wall-clock runner, executor reset, and local-path parsing.

**Output shape:** image entity, OCR documents/emails, face embeddings/crops, object labels, reverse matches, perceptual hashes.

---

### 5.6 Multi-input

**Detection:** more than one identity signal (e.g. `alice | alice@mail.com` or `username + email`).

**Behavior:**

- Parse fields: username, email, phone, domain, name, occupation.
- Run **parallel branches** (username + email, etc.) under dual-mode budgets.
- Merge branch results into one investigation record.

Image-only uploads are **not** multi (even though the path may sit in `extras`).

---

## 6. Fusion, confidence, and provenance

### Fusion ideas (explain in interviews)

- **Multi-source corroboration:** same account from Maigret + Sherlock → higher trust.
- **Tool reliability tiers:** some tools are scanners, some APIs, some heuristics.
- **Entity types:** account, email, phone, domain, image, person, document, …
- **Provenance:** every field keeps `source_tool`, evidence payloads, timestamps.
- **Partial results:** if a tool times out, partial hits can still be kept.

### Confidence is not “truth”

Scores estimate **support from available OSINT**, not legal certainty. Always present as investigative leads.

---

## 7. Parallelism and safety model

```
Investigation slot (usually 1 at a time)
  └── Feature batch (execute_tools_parallel)
        ├── Concurrency limit (per feature)
        ├── Per-tool wall (starts when tool leaves queue)
        └── Batch wall (total time for the group)
              └── Image ML semaphore (1) + IO semaphore (N)
                    └── Dedicated ML thread pool (reset on timeout)
```

Environment knobs (see `.env.example`):

- `INVESTIGATION_WALL_SECONDS`
- `IMAGE_STAGE_WALL_SECONDS`, `IMAGE_ML_TOOL_WALL_SEC`, `IMAGE_IO_TOOL_WALL_SEC`
- `MAIGRET_MAX_SITES`, `SHERLOCK_MAX_SITES`
- `PHONE_WALL_SEC`, `GLOBAL_TOOL_SUBPROCESS_CAP`

---

## 8. Enterprise / security concepts

### Auth

- Login → JWT access token + refresh token.
- WebSocket and intel routes require `start_investigation` (when enterprise auth enabled).
- `ENTERPRISE_AUTH=false` is legacy open mode (demo only).

### RBAC

- Rank codes map to permission lists in `config/rbac.json`.
- Case-scoped checks: relationship (IO, supervisor, team, …) × permission matrix.
- Admin IAM UI manages users; demo ranks seeded from `config/demo_users.json`.

### Audit

- Logins, user admin actions, investigations are audit-logged.
- Active sessions view derives from audit trail.

### Cases

- Investigations can be linked to cases.
- Assignments define team roles for authorization.

---

## 9. Frontend concepts (brief)

| Piece | Role |
|---|---|
| `LoginPage` / CyberSamurai design | Auth UI (design preview optional) |
| `SearchBar` | Query + mode (Quick/Standard/Deep/Samurai) + image upload |
| `investigationStore` | Live state from WebSocket events |
| `ProgressTracker` | Tool/phase progress |
| Case workspace | Case-scoped intel, team, evidence |
| Admin IAM | Users, ranks, sessions |

Frontend does **not** run OSINT tools; it only displays orchestrated results.

---

## 10. Data stores

| Store | Use |
|---|---|
| SQLite `data/socmint_enterprise.db` (default) | Users, cases, audit (enterprise) |
| Optional Postgres `DATABASE_URL` | Investigations/entities persistence |
| Optional Neo4j | Graph export |
| In-memory / file cache | Running investigations, intelligence cache |
| `data/` uploads | Image uploads, face crops |

---

## 11. Key files cheat sheet

| Concern | File |
|---|---|
| App entry | `main.py` |
| Live investigate | `api/ws.py`, `services/investigation_runner.py` |
| Tool parallel runner | `orchestrator/parallel_runner.py` |
| Tool map / timeouts | `orchestrator/config.py`, `orchestrator/parallel_config.py` |
| Input parsing | `services/multi_input.py`, `services/query_detector.py` |
| Registry routing | `services/osint_registry/router.py`, `config/osint_catalog.json` |
| Fusion | `services/fusion.py`, `services/fusion_engine.py` |
| Image ML | `services/image_intelligence/`, `adapters/image_tools.py` |
| Reverse image | `services/reverse_image/` |
| Phone | `services/phone_intelligence/`, `adapters/phone_social_intel.py` |
| Discovery | `services/discovery/`, `services/pivot/` |
| RBAC | `config/rbac.json`, `services/enterprise/rbac.py` |
| Modes | `schemas/investigation_mode.py` |

---

## 12. Technical Q&A (practice)

### Q: How does the system decide which tools to run?

**A:** Detect input type → map to feature → OSINT registry selects tools for that input/feature/profile → mode may override (e.g. fast username list). Image uses an explicit profile tool list so slow ML tools are not dropped.

### Q: What if one tool crashes or hangs?

**A:** Adapters isolate failures (`ToolResult.success=False`). Parallel runner applies per-tool and batch walls. Image ML uses a dedicated executor that is **reset** on timeout so later tools still run. Investigation returns partial fusion.

### Q: How do you avoid duplicate accounts from Maigret and Sherlock?

**A:** Normalization + fusion dedupe by platform/URL/handle; corroboration increases confidence when multiple tools agree.

### Q: How is image intelligence different from username search?

**A:** Username search is mostly network scanners. Image intelligence mixes **metadata**, **computer vision** (face/OCR/objects), and **reverse image search**, then converts OCR/faces/matches into entities that can pivot to username/email hops.

### Q: Why serialize ML image tools?

**A:** Models (InsightFace, EasyOCR, YOLO, Torch) are memory-heavy and not always thread-safe on import. One ML worker avoids RAM spikes and import races; IO/reverse tools still run in parallel.

### Q: How does live UI stay updated?

**A:** WebSocket progress callbacks from `InvestigationRunner` emit phase/tool events; frontend store merges partial fusion snapshots.

### Q: How does RBAC interact with investigations?

**A:** Starting an investigation requires `start_investigation`. Case-linked actions use `can_on_case(permission)` against rank × relationship matrix. Auth does not change tool algorithms—only authorization.

### Q: What is discovery and when is it disabled?

**A:** Discovery expands leads found in the seed result. Disabled for phone (non-deep), samurai mode, and **quick image** mode so image tools finish without username-hop side quests.

### Q: How are secrets handled?

**A:** `.env` (not committed) for API keys, JWT secret, admin password. PhoneInfoga keys can live in `phoneNumber/phoneinfoga/.env`. Demo passwords are for local/demo only.

### Q: Walk me through “user uploads a photo of an ID card.”

**A:**

1. Upload API saves image → path.
2. WS investigate with `query_type=image`.
3. Metadata tools read EXIF.
4. OCR tools extract printed email/phone/name.
5. Face tools embed any face present.
6. Reverse search looks for the same image online.
7. Fusion creates document/email/phone/image entities.
8. Evidence panel shows extracted fields.
9. In standard/deep mode, discovery may investigate the extracted email/username next.

### Q: Walk me through “investigate username `alice`.”

**A:**

1. Detect username → `username_search`.
2. Platform probe + Maigret + Sherlock (+ others by mode) run in parallel.
3. Partial hits stream to UI.
4. Fusion builds account entities with sources.
5. Profile verification / evidence enrichment.
6. Discovery may follow emails/websites/avatars found on profiles.

---

## 13. Mental model (one paragraph)

> The platform is a **feature-routed OSINT orchestrator**: it classifies the target, selects tools from a registry, runs them under **time and concurrency budgets**, converts heterogeneous tool output into **provenance-rich entities**, **fuses** and **correlates** them, optionally **expands** via discovery hops, and streams progress to a case-aware UI protected by **rank-based RBAC**.

---

## 14. Run locally (quick)

```bash
# Backend
source .venv/bin/activate
uvicorn main:app --reload --host 127.0.0.1 --port 8000

# Frontend
cd frontend && npm run dev
```

Open `http://localhost:5173`, sign in (see `.env` / demo ranks), submit a target.

For full tool install on Linux: `bash scripts/install_tools.sh`.

---

*This document describes the system as implemented in this repository. Tool availability depends on local installs, API keys, and mode/profile settings.*
