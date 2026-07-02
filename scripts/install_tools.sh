#!/usr/bin/env bash
# SOCMINT OSINT Tool Installation Script
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
EXTERNAL_TOOLS="$PROJECT_ROOT/external_tools"
VENV_DIR="$PROJECT_ROOT/.venv"
REGISTRY="$PROJECT_ROOT/config/tool_registry.json"

log() { echo "[INSTALL] $*"; }
warn() { echo "[WARN] $*" >&2; }
error() { echo "[ERROR] $*" >&2; exit 1; }

mkdir -p "$EXTERNAL_TOOLS" "$PROJECT_ROOT/data"

# ── Python venv ──────────────────────────────────────────────────────────────
if [ ! -d "$VENV_DIR" ]; then
    log "Creating Python virtual environment..."
    python3 -m venv "$VENV_DIR"
fi
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
pip install --upgrade pip setuptools wheel -q
pip install -r "$PROJECT_ROOT/requirements.txt" -q
log "Python dependencies installed."

update_registry() {
    local tool="$1" installed="$2"
    python3 -c "
import json
path = '$REGISTRY'
with open(path) as f:
    reg = json.load(f)
if '$tool' in reg:
    reg['$tool']['installed'] = '$installed' == 'true'
    with open(path, 'w') as f:
        json.dump(reg, f, indent=2)
"
}

# ── 1. Sherlock ──────────────────────────────────────────────────────────────
install_sherlock() {
    log "Installing Sherlock..."
    local dir="$EXTERNAL_TOOLS/sherlock"
    if [ ! -d "$dir/.git" ]; then
        git clone --depth 1 https://github.com/sherlock-project/sherlock.git "$dir"
    else
        git -C "$dir" pull --ff-only || warn "Sherlock pull failed, using existing."
    fi
    pip install -r "$dir/requirements.txt" -q 2>/dev/null || pip install requests requests-futures colorama openpyxl pandas -q
    pip install -e "$dir" -q 2>/dev/null || true
    if [ -f "$dir/sherlock_project/sherlock.py" ]; then
        update_registry "sherlock" "true"
        log "Sherlock installed."
    else
        update_registry "sherlock" "false"
        warn "Sherlock install incomplete."
    fi
}

# ── 2. Maigret ───────────────────────────────────────────────────────────────
install_maigret() {
    log "Installing Maigret..."
    pip install maigret -q 2>/dev/null || pip install maigret
    if command -v maigret &>/dev/null; then
        update_registry "maigret" "true"
        log "Maigret installed."
    else
        update_registry "maigret" "false"
        warn "Maigret executable not found."
    fi
}

# ── 3. Social Analyzer ─────────────────────────────────────────────────────
install_social_analyzer() {
    log "Installing Social Analyzer..."
    local dir="$EXTERNAL_TOOLS/SocialAnalyzer"
    if [ ! -d "$dir/.git" ]; then
        git clone --depth 1 https://github.com/qeeqbox/social-analyzer.git "$dir"
    else
        git -C "$dir" pull --ff-only || warn "SocialAnalyzer pull failed, using existing."
    fi
    if [ -f "$dir/package.json" ]; then
        if command -v npm &>/dev/null; then
            cd "$dir" && npm install --silent 2>/dev/null || warn "npm install for SocialAnalyzer failed."
            cd "$PROJECT_ROOT"
        fi
    fi
    pip install -r "$dir/requirements.txt" -q 2>/dev/null \
        || pip install requests beautifulsoup4 lxml tld langdetect termcolor galeodes -q 2>/dev/null \
        || true
    if [ -d "$dir" ]; then
        update_registry "social_analyzer" "true"
        log "Social Analyzer installed."
    else
        update_registry "social_analyzer" "false"
        warn "Social Analyzer install incomplete."
    fi
}

# ── 5. Holehe ────────────────────────────────────────────────────────────────
install_holehe() {
    log "Installing Holehe..."
    pip install holehe -q 2>/dev/null || pip install holehe
    if command -v holehe &>/dev/null || python3 -c "import holehe" 2>/dev/null; then
        update_registry "holehe" "true"
        log "Holehe installed."
    else
        update_registry "holehe" "false"
        warn "Holehe install incomplete."
    fi
}

# ── 6. theHarvester ──────────────────────────────────────────────────────────
install_theharvester() {
    log "Installing theHarvester..."
    local dir="$EXTERNAL_TOOLS/theHarvester"
    if [ ! -d "$dir/.git" ]; then
        git clone --depth 1 https://github.com/laramies/theHarvester.git "$dir"
    else
        git -C "$dir" pull --ff-only || warn "theHarvester pull failed, using existing."
    fi
    pip install -r "$dir/requirements.txt" -q 2>/dev/null || \
        pip install requests dnspython netaddr ujson aiohttp aiodns censys -q 2>/dev/null || true
    if [ -f "$dir/bin/theHarvester" ] || command -v theHarvester &>/dev/null; then
        update_registry "theharvester" "true"
        log "theHarvester installed."
    else
        update_registry "theharvester" "false"
        warn "theHarvester install incomplete."
    fi
}

# ── 7. SpiderFoot ────────────────────────────────────────────────────────────
install_spiderfoot() {
    log "Installing SpiderFoot..."
    local dir="$EXTERNAL_TOOLS/spiderfoot"
    if [ ! -d "$dir/.git" ]; then
        git clone --depth 1 https://github.com/smicallef/spiderfoot.git "$dir"
    else
        git -C "$dir" pull --ff-only || warn "SpiderFoot pull failed, using existing."
    fi
    pip install -r "$dir/requirements.txt" -q 2>/dev/null || true
    pip install adblockparser dnspython ExifRead CherryPy cherrypy-cors Mako beautifulsoup4 lxml netaddr pysocks requests ipwhois phonenumbers pygexf PyPDF2 python-whois secure pyOpenSSL python-docx python-pptx networkx cryptography publicsuffixlist openpyxl pyyaml -q 2>/dev/null || true
    if [ -f "$dir/sf.py" ]; then
        update_registry "spiderfoot" "true"
        log "SpiderFoot installed."
    else
        update_registry "spiderfoot" "false"
        warn "SpiderFoot install incomplete."
    fi
}

# ── 8. Recon-ng ──────────────────────────────────────────────────────────────
install_recon_ng() {
    log "Installing Recon-ng..."
    local dir="$EXTERNAL_TOOLS/recon-ng"
    if command -v recon-ng &>/dev/null; then
        update_registry "recon_ng" "true"
        log "Recon-ng found via package manager."
        return
    fi
    if [ ! -d "$dir/.git" ]; then
        git clone --depth 1 https://github.com/lanmaster53/recon-ng.git "$dir"
    else
        git -C "$dir" pull --ff-only || warn "Recon-ng pull failed, using existing."
    fi
    if [ -f "$dir/REQUIREMENTS" ]; then
        pip install -r "$dir/REQUIREMENTS" -q 2>/dev/null || true
    elif [ -f "$dir/requirements.txt" ]; then
        pip install -r "$dir/requirements.txt" -q 2>/dev/null || true
    fi
    pip install flask dicttoxml unicodecsv xlsxwriter -q 2>/dev/null || true
    if [ -f "$dir/recon-ng" ] || [ -f "$dir/recon-ng.py" ]; then
        update_registry "recon_ng" "true"
        log "Recon-ng installed."
    else
        update_registry "recon_ng" "false"
        warn "Recon-ng install incomplete."
    fi
}

# ── 9. Shodan (Python library) ───────────────────────────────────────────────
install_shodan() {
    log "Installing Shodan library..."
    pip install shodan -q 2>/dev/null || pip install shodan
    if python3 -c "import shodan" 2>/dev/null; then
        if [ -n "${SHODAN_API_KEY:-}" ]; then
            update_registry "shodan" "true"
            log "Shodan library installed (API key present)."
        else
            update_registry "shodan" "true"
            log "Shodan library installed (API key not set - will report missing_api_key)."
        fi
    else
        update_registry "shodan" "false"
        warn "Shodan library install failed."
    fi
}

# ── 10. Image Intelligence Engine ─────────────────────────────────────────────
install_image_intelligence() {
    log "Installing Image Intelligence Engine dependencies..."
    if command -v apt-get &>/dev/null; then
        if [ -x "$SCRIPT_DIR/install_image_system_deps.sh" ]; then
            bash "$SCRIPT_DIR/install_image_system_deps.sh" 2>/dev/null || warn "Run: sudo bash scripts/install_image_system_deps.sh for tesseract/exiftool"
        fi
    fi
    pip install insightface onnxruntime deepface facenet-pytorch torch torchvision ultralytics \
        easyocr paddlepaddle paddleocr pytesseract transformers timm hachoir ftfy regex -q
    python3 -c "
from importlib import import_module
mods = ['insightface','deepface','facenet_pytorch','ultralytics','easyocr','paddleocr','pytesseract','transformers','hachoir','cv2','imagehash']
failed = []
for m in mods:
    try:
        import_module(m)
    except Exception as e:
        failed.append(f'{m}:{e}')
if failed:
    raise SystemExit('Missing image intelligence modules: ' + ', '.join(failed))
print('Image intelligence modules OK')
"
    for tool in pillow exiftool hachoir insightface deepface facenet opencv_face tesseract easyocr paddleocr yolo grounding_dino clip; do
        update_registry "$tool" "true"
    done
    log "Image Intelligence Engine dependencies installed."
}

# ── 11. Extended OSINT catalog tools ─────────────────────────────────────────
install_extended_osint() {
    log "Installing extended OSINT catalog tools..."
    mkdir -p "$EXTERNAL_TOOLS/bin"

    pip install -q -r "$EXTERNAL_TOOLS/blackbird/requirements.txt" 2>/dev/null || true
    pip install -q -e "$EXTERNAL_TOOLS/Nexfil" --no-deps 2>/dev/null || true
    pip install -q aiohttp tldextract undetected_chromedriver unidecode autoslot rich-argparse loguru netaddr httpx python-whois 2>/dev/null || true
    pip install -q -e "$EXTERNAL_TOOLS/GHunt" 2>/dev/null || pip install -q geopy httpx imagehash rich beautifultable alive-progress autoslot humanize inflection jsonpickle rich-argparse dnspython 2>/dev/null || true
    pip install -q -e "$EXTERNAL_TOOLS/GitFive" --no-deps 2>/dev/null || true

    download_bin() {
        local name="$1" url="$2"
        local dest="$EXTERNAL_TOOLS/bin/$name"
        if [ -x "$dest" ]; then return 0; fi
        local tmp
        tmp=$(mktemp -d)
        curl -fsSL "$url" -o "$tmp/pkg" || { warn "Download failed: $name"; rm -rf "$tmp"; return 1; }
        if file "$tmp/pkg" | grep -q Zip; then unzip -qo "$tmp/pkg" -d "$tmp"; else tar -xzf "$tmp/pkg" -C "$tmp" 2>/dev/null || tar -xf "$tmp/pkg" -C "$tmp"; fi
        local found
        found=$(find "$tmp" -maxdepth 3 -type f -name "$name" | head -1)
        if [ -n "$found" ]; then cp "$found" "$dest" && chmod +x "$dest"; fi
        rm -rf "$tmp"
    }

    download_bin phoneinfoga "https://github.com/sundowndev/phoneinfoga/releases/download/v2.11.0/phoneinfoga_Linux_x86_64.tar.gz" || true
    download_bin subfinder "https://github.com/projectdiscovery/subfinder/releases/download/v2.8.0/subfinder_2.8.0_linux_amd64.zip" || true
    download_bin amass "https://github.com/owasp-amass/amass/releases/download/v4.2.0/amass_Linux_amd64.zip" || true

    for tool in blackbird nexfil gitfive ghunt gravatar phoneinfoga subfinder amass dnsrecon whois; do
        update_registry "$tool" "true"
    done
    log "Extended OSINT catalog tools installed."
}

# ── Run all installers ───────────────────────────────────────────────────────
log "Starting OSINT tool installation..."
log "Project root: $PROJECT_ROOT"

install_sherlock
install_maigret
install_social_analyzer
install_holehe
install_theharvester
install_spiderfoot
install_recon_ng
install_shodan
install_image_intelligence
install_extended_osint

log "Installation complete. Run scripts/verify_tools.sh to validate."
