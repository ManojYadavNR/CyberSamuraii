#!/usr/bin/env bash
# SOCMINT OSINT Tool Verification Script
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
EXTERNAL_TOOLS="$PROJECT_ROOT/external_tools"
VENV_DIR="$PROJECT_ROOT/.venv"

PASS=0
FAIL=0
WARN=0

log() { echo "[VERIFY] $*"; }
pass() { echo "  ✓ $1"; PASS=$((PASS + 1)); }
fail() { echo "  ✗ $1"; FAIL=$((FAIL + 1)); }
warn() { echo "  ⚠ $1"; WARN=$((WARN + 1)); }

if [ -d "$VENV_DIR" ]; then
    if [ -f "$VENV_DIR/Scripts/activate" ]; then
        # shellcheck disable=SC1091
        source "$VENV_DIR/Scripts/activate"
    elif [ -f "$VENV_DIR/bin/activate" ]; then
        # shellcheck disable=SC1091
        source "$VENV_DIR/bin/activate"
    fi
fi

if command -v python3 &>/dev/null; then
    PYTHON=python3
else
    PYTHON=python
fi

export PYTHONPATH="$PROJECT_ROOT:${PYTHONPATH:-}"

echo "============================================"
echo "  SOCMINT Tool Verification"
echo "  Project: $PROJECT_ROOT"
echo "============================================"
echo

# ── Sherlock ─────────────────────────────────────────────────────────────────
log "Sherlock"
if [ -f "$EXTERNAL_TOOLS/sherlock/sherlock_project/sherlock.py" ]; then
    if python3 "$EXTERNAL_TOOLS/sherlock/sherlock_project/sherlock.py" --help &>/dev/null; then
        pass "Sherlock executable responds to --help"
    else
        fail "Sherlock executable failed --help check"
    fi
else
    fail "Sherlock not found at external_tools/sherlock"
fi

# ── Maigret ──────────────────────────────────────────────────────────────────
log "Maigret"
if command -v maigret &>/dev/null; then
    if maigret --help &>/dev/null || maigret --version &>/dev/null; then
        pass "Maigret CLI available"
    else
        warn "Maigret found but --help failed"
    fi
else
    fail "Maigret executable not in PATH"
fi

# ── Social Analyzer ──────────────────────────────────────────────────────────
log "Social Analyzer"
if [ -d "$EXTERNAL_TOOLS/SocialAnalyzer" ]; then
    pass "Social Analyzer repository present"
else
    fail "Social Analyzer not cloned"
fi

# ── Holehe ───────────────────────────────────────────────────────────────────
log "Holehe"
if command -v holehe &>/dev/null; then
    if holehe --help &>/dev/null || python3 -c "import holehe" &>/dev/null; then
        pass "Holehe available"
    else
        warn "Holehe found but verification inconclusive"
    fi
elif python3 -c "import holehe" &>/dev/null; then
    pass "Holehe Python module importable"
else
    fail "Holehe not installed"
fi

# ── theHarvester ─────────────────────────────────────────────────────────────
log "theHarvester"
if [ -f "$EXTERNAL_TOOLS/theHarvester/bin/theHarvester" ] || command -v theHarvester &>/dev/null; then
    HARVEST_BIN="${EXTERNAL_TOOLS}/theHarvester/bin/theHarvester"
    if [ -f "$HARVEST_BIN" ]; then
        if python3 "$HARVEST_BIN" -h &>/dev/null; then
            pass "theHarvester executable responds to -h"
        else
            warn "theHarvester present but -h check failed"
        fi
    elif theHarvester -h &>/dev/null; then
        pass "theHarvester CLI available via PATH"
    fi
else
    fail "theHarvester not found"
fi

# ── SpiderFoot ───────────────────────────────────────────────────────────────
log "SpiderFoot"
if [ -f "$EXTERNAL_TOOLS/spiderfoot/sf.py" ]; then
    if python3 "$EXTERNAL_TOOLS/spiderfoot/sf.py" -h &>/dev/null; then
        pass "SpiderFoot executable responds to -h"
    else
        warn "SpiderFoot present but -h check failed"
    fi
else
    fail "SpiderFoot not found"
fi

# ── Recon-ng ─────────────────────────────────────────────────────────────────
log "Recon-ng"
RECON_OK=false
if command -v recon-ng &>/dev/null; then
    RECON_OK=true
    pass "Recon-ng available via PATH"
elif [ -f "$EXTERNAL_TOOLS/recon-ng/recon-ng" ] || [ -f "$EXTERNAL_TOOLS/recon-ng/recon-ng.py" ]; then
    RECON_OK=true
    pass "Recon-ng source present"
fi
if [ "$RECON_OK" = false ]; then
    fail "Recon-ng not installed"
fi

# ── Shodan ───────────────────────────────────────────────────────────────────
log "Shodan"
if python3 -c "import shodan" &>/dev/null; then
    if [ -n "${SHODAN_API_KEY:-}" ]; then
        pass "Shodan library installed with API key set"
    else
        warn "Shodan library installed but SHODAN_API_KEY not set"
    fi
else
    fail "Shodan Python library not installed"
fi

# ── Python API health check ──────────────────────────────────────────────────
log "FastAPI Application"
if python3 -c "
from tools.registry import registry
registry.reload()
health = registry.check_all_health()
for name, status in health.items():
    print(f'  {name}: {status.value}')
" 2>/dev/null; then
    pass "Tool registry health check executed"
else
    fail "Tool registry import failed"
fi

# ── Update registry from verification results ──────────────────────────────
python3 << PYEOF
import json
import os
import shutil
from pathlib import Path

PROJECT_ROOT = Path("$PROJECT_ROOT")

def importable(mod):
    try:
        __import__(mod)
        return True
    except ImportError:
        return False

registry_path = PROJECT_ROOT / "config" / "tool_registry.json"
external = PROJECT_ROOT / "external_tools"

with open(registry_path) as f:
    reg = json.load(f)

checks = {
    "sherlock": (external / "sherlock" / "sherlock_project" / "sherlock.py").exists(),
    "maigret": shutil.which("maigret") is not None,
    "social_analyzer": (external / "SocialAnalyzer").is_dir(),
    "holehe": shutil.which("holehe") is not None or importable("holehe"),
    "theharvester": (
        (external / "theHarvester" / "bin" / "theHarvester").exists()
        or shutil.which("theHarvester") is not None
    ),
    "spiderfoot": (external / "spiderfoot" / "sf.py").exists(),
    "recon_ng": (
        shutil.which("recon-ng") is not None
        or (external / "recon-ng" / "recon-ng").exists()
        or (external / "recon-ng" / "recon-ng.py").exists()
    ),
    "shodan": importable("shodan"),
    "image_intel": True,
}

for tool, ok in checks.items():
    if tool in reg:
        reg[tool]["installed"] = ok

with open(registry_path, "w") as f:
    json.dump(reg, f, indent=2)

print("Registry updated from verification.")
PYEOF

echo
echo "============================================"
echo "  Results: $PASS passed, $FAIL failed, $WARN warnings"
echo "============================================"

if [ "$FAIL" -gt 0 ]; then
    echo "STATUS: SOME TOOLS FAILED VERIFICATION"
    exit 1
fi

echo "STATUS: ALL TOOLS VERIFIED"
exit 0
