#!/usr/bin/env bash
# Verify Identity Correlation Engine dependencies and smoke tests
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_DIR="$PROJECT_ROOT/.venv"

if [ -d "$VENV_DIR" ]; then
    # shellcheck disable=SC1091
    source "$VENV_DIR/bin/activate"
fi

export PYTHONPATH="$PROJECT_ROOT:${PYTHONPATH:-}"

echo "============================================"
echo "  Identity Correlation Engine Verification"
echo "============================================"

python3 << 'PYEOF'
import sys

checks = {}

try:
    from rapidfuzz.distance import Levenshtein, JaroWinkler
    checks["rapidfuzz"] = True
except ImportError:
    checks["rapidfuzz"] = False

try:
    import Levenshtein as lev
    checks["python-Levenshtein"] = True
except ImportError:
    checks["python-Levenshtein"] = False

try:
    import imagehash
    checks["imagehash"] = True
except ImportError:
    checks["imagehash"] = False

try:
    import cv2
    checks["opencv"] = True
except ImportError:
    checks["opencv"] = False

try:
    from sentence_transformers import SentenceTransformer
    checks["sentence-transformers"] = True
except ImportError:
    checks["sentence-transformers"] = False

try:
    import insightface
    checks["insightface"] = True
except ImportError:
    checks["insightface"] = False

print("\nDependency status:")
required = ["rapidfuzz", "imagehash"]
optional = ["python-Levenshtein", "opencv", "sentence-transformers", "insightface"]
fail = False
for name in required:
    ok = checks.get(name, False)
    print(f"  {'✓' if ok else '✗'} {name} (required)")
    if not ok:
        fail = True
for name in optional:
    ok = checks.get(name, False)
    print(f"  {'✓' if ok else '⚠'} {name} (optional — fallback available)")

from services.correlation.engine import correlation_engine
from schemas.fusion import Entity, FusionOutput
import asyncio

entities = [
    Entity(type="account", value="github.com/manojyadavnr", sources=["sherlock", "maigret"],
           metadata={"platform": "github.com", "verified": True, "url": "https://github.com/manojyadavnr"},
           fusion_score=0.95),
    Entity(type="account", value="twitter.com/manojyadavnr", sources=["sherlock"],
           metadata={"platform": "twitter.com", "verified": True, "url": "https://twitter.com/manojyadavnr"},
           fusion_score=0.92),
]
fusion = FusionOutput(deduplicated_entities=entities, entities=entities)
result = asyncio.run(correlation_engine.correlate(fusion, seed_query="manojyadavnr"))

print("\nSmoke test:")
print(f"  accounts analyzed: {result.total_accounts_analyzed}")
print(f"  clusters: {result.total_clusters}")
if result.clusters:
    c = result.clusters[0]
    print(f"  top cluster confidence: {c.confidence_score}")
    print(f"  linked accounts: {len(c.linked_accounts)}")
    print(f"  evidence types: {[e.type for e in c.evidence]}")
print(f"  signal availability: {result.signal_availability}")

if fail:
    print("\nSTATUS: MISSING REQUIRED DEPENDENCIES")
    sys.exit(1)

print("\nSTATUS: CORRELATION ENGINE VERIFIED")
PYEOF

echo ""
echo "Running unit tests..."
python3 -m unittest tests.test_correlation_engine -v
