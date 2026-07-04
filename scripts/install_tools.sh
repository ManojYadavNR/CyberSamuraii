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

# Git Bash on Windows passes /d/... paths to python.exe, which cannot open them.
# Always run pip/python file operations from PROJECT_ROOT with relative paths.
in_project() {
    (cd "$PROJECT_ROOT" && "$@")
}

pip_install() {
    in_project "$PYTHON" -m pip install "$@"
}

mkdir -p "$EXTERNAL_TOOLS" "$PROJECT_ROOT/data" "$PROJECT_ROOT/config"
if [ ! -f "$REGISTRY" ]; then
    error "Missing config/tool_registry.json — restore it from the repo before running this script."
fi

# ── Python venv (Windows Git Bash uses Scripts/activate; Linux/macOS use bin/) ─
resolve_python() {
    if command -v python3 &>/dev/null; then
        echo python3
    elif command -v python &>/dev/null; then
        echo python
    else
        error "Python not found — install Python 3.10+ and retry."
    fi
}

activate_venv() {
    if [ -f "$VENV_DIR/Scripts/activate" ]; then
        # shellcheck disable=SC1091
        source "$VENV_DIR/Scripts/activate"
    elif [ -f "$VENV_DIR/bin/activate" ]; then
        # shellcheck disable=SC1091
        source "$VENV_DIR/bin/activate"
    else
        error "Virtual environment activate script not found in $VENV_DIR"
    fi
}

PYTHON_BOOT="$(resolve_python)"

if [ ! -d "$VENV_DIR" ]; then
    log "Creating Python virtual environment..."
    "$PYTHON_BOOT" -m venv "$VENV_DIR"
fi
activate_venv
PYTHON="${PYTHON_BOOT:-python}"
if ! command -v python3 &>/dev/null && command -v python &>/dev/null; then
    PYTHON=python
fi
pip_install --upgrade pip "setuptools<82" wheel -q
pip_install -r requirements.txt -q
log "Python dependencies installed."

update_registry() {
    local tool="$1" installed="$2"
    in_project "$PYTHON" -c "
import json
from pathlib import Path
path = Path('config/tool_registry.json')
with open(path, encoding='utf-8') as f:
    reg = json.load(f)
if '$tool' in reg:
    reg['$tool']['installed'] = '$installed' == 'true'
    with open(path, 'w', encoding='utf-8') as f:
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
    pip_install -r external_tools/sherlock/requirements.txt -q 2>/dev/null \
        || pip_install requests requests-futures colorama openpyxl pandas -q
    pip_install -e external_tools/sherlock -q 2>/dev/null || true
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
    pip_install maigret -q 2>/dev/null || pip_install maigret
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
    # Python CLI (app.py) is what adapters invoke — npm is optional for the web UI only.
    if [ -f "$dir/package.json" ] && command -v npm &>/dev/null; then
        (cd "$dir" && npm install --legacy-peer-deps --silent) 2>/dev/null \
            || warn "npm install for SocialAnalyzer UI failed (Python CLI still works)."
    fi
    pip_install -r external_tools/SocialAnalyzer/requirements.txt -q 2>/dev/null \
        || pip_install requests beautifulsoup4 lxml tld langdetect termcolor galeodes -q 2>/dev/null \
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
    pip_install holehe -q 2>/dev/null || pip_install holehe
    if command -v holehe &>/dev/null || "$PYTHON" -c "import holehe" 2>/dev/null; then
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
    pip_install -r external_tools/theHarvester/requirements.txt -q 2>/dev/null || \
        pip_install requests dnspython netaddr ujson aiohttp aiodns censys -q 2>/dev/null || true
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
    pip_install -r external_tools/spiderfoot/requirements.txt -q 2>/dev/null || true
    pip_install adblockparser dnspython ExifRead CherryPy cherrypy-cors Mako beautifulsoup4 lxml netaddr pysocks requests ipwhois phonenumbers pygexf PyPDF2 python-whois secure pyOpenSSL python-docx python-pptx networkx cryptography publicsuffixlist openpyxl pyyaml -q 2>/dev/null || true
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
        pip_install -r external_tools/recon-ng/REQUIREMENTS -q 2>/dev/null || true
    elif [ -f "$dir/requirements.txt" ]; then
        pip_install -r external_tools/recon-ng/requirements.txt -q 2>/dev/null || true
    fi
    pip_install flask dicttoxml unicodecsv xlsxwriter -q 2>/dev/null || true
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
    pip_install shodan -q 2>/dev/null || pip_install shodan
    if "$PYTHON" -c "import shodan" 2>/dev/null; then
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
    pip_install insightface onnxruntime deepface facenet-pytorch torch torchvision ultralytics \
        easyocr paddlepaddle paddleocr pytesseract transformers timm hachoir ftfy regex -q
    in_project "$PYTHON" -c "
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

# ── Clone helper ─────────────────────────────────────────────────────────────
clone_tool() {
    local name="$1" url="$2" dir="$3"
    if [ -d "$dir/.git" ]; then
        git -C "$dir" pull --ff-only || warn "$name pull failed, using existing."
        return 0
    fi
    if [ -d "$dir" ] && [ -n "$(ls -A "$dir" 2>/dev/null)" ]; then
        return 0
    fi
    log "Cloning $name..."
    git clone --depth 1 "$url" "$dir" || {
        warn "Failed to clone $name"
        return 1
    }
}

# ── 11. Extended OSINT catalog tools ─────────────────────────────────────────
install_extended_osint() {
    log "Installing extended OSINT catalog tools..."
    mkdir -p "$EXTERNAL_TOOLS/bin"

    clone_tool "blackbird" "https://github.com/p1ngul1n0/blackbird.git" "$EXTERNAL_TOOLS/blackbird" || true
    clone_tool "Nexfil" "https://github.com/thewhiteh4t/nexfil.git" "$EXTERNAL_TOOLS/Nexfil" || true
    clone_tool "GHunt" "https://github.com/mxrch/GHunt.git" "$EXTERNAL_TOOLS/GHunt" || true
    clone_tool "GitFive" "https://github.com/mxrch/GitFive.git" "$EXTERNAL_TOOLS/GitFive" || true
    clone_tool "dnsrecon" "https://github.com/darkoperator/dnsrecon.git" "$EXTERNAL_TOOLS/dnsrecon" || true

    if [ -f "$EXTERNAL_TOOLS/blackbird/requirements.txt" ]; then
        pip_install -q -r external_tools/blackbird/requirements.txt 2>/dev/null || true
    fi
    if [ -d "$EXTERNAL_TOOLS/Nexfil" ]; then
        pip_install -q -e external_tools/Nexfil --no-deps 2>/dev/null || true
    fi
    pip_install -q aiohttp tldextract undetected_chromedriver unidecode autoslot rich-argparse loguru netaddr httpx python-whois dnspython 2>/dev/null || true
    if [ -d "$EXTERNAL_TOOLS/GHunt" ]; then
        pip_install -q -e external_tools/GHunt 2>/dev/null \
            || pip_install -q geopy httpx imagehash rich beautifultable alive-progress autoslot humanize inflection jsonpickle rich-argparse dnspython 2>/dev/null \
            || true
    fi
    if [ -d "$EXTERNAL_TOOLS/GitFive" ]; then
        pip_install -q -e external_tools/GitFive --no-deps 2>/dev/null || true
    fi
    if [ -f "$EXTERNAL_TOOLS/dnsrecon/requirements.txt" ]; then
        pip_install -q -r external_tools/dnsrecon/requirements.txt 2>/dev/null || true
    fi

    download_bin() {
        local name="$1" url="$2"
        local dest="$EXTERNAL_TOOLS/bin/$name"
        local dest_exe="$EXTERNAL_TOOLS/bin/${name}.exe"
        if [ -f "$dest" ] || [ -f "$dest_exe" ]; then
            log "$name binary already present."
            return 0
        fi
        local tmp
        tmp=$(mktemp -d)
        log "Downloading $name..."
        curl -fsSL "$url" -o "$tmp/pkg" || { warn "Download failed: $name ($url)"; rm -rf "$tmp"; return 1; }
        # Detect archive type by extension / magic, not only `file` (missing on some Git Bash installs).
        case "$url" in
            *.zip)
                unzip -qo "$tmp/pkg" -d "$tmp" || { warn "Unzip failed: $name"; rm -rf "$tmp"; return 1; }
                ;;
            *.tar.gz|*.tgz)
                tar -xzf "$tmp/pkg" -C "$tmp" || { warn "Tar extract failed: $name"; rm -rf "$tmp"; return 1; }
                ;;
            *)
                if file "$tmp/pkg" 2>/dev/null | grep -qi zip; then
                    unzip -qo "$tmp/pkg" -d "$tmp"
                else
                    tar -xzf "$tmp/pkg" -C "$tmp" 2>/dev/null || tar -xf "$tmp/pkg" -C "$tmp"
                fi
                ;;
        esac
        local found
        found=$(find "$tmp" -maxdepth 4 -type f \( -name "$name" -o -name "${name}.exe" \) | head -1)
        if [ -z "$found" ]; then
            warn "Binary not found inside archive: $name"
            rm -rf "$tmp"
            return 1
        fi
        # Always install as name.exe on Windows so Python can resolve it.
        case "$(uname -s 2>/dev/null)" in
            MINGW*|MSYS*|CYGWIN*|Windows*)
                cp "$found" "$dest_exe"
                chmod +x "$dest_exe" 2>/dev/null || true
                # Also copy bare name for registry paths that omit .exe
                cp "$found" "$dest" 2>/dev/null || true
                ;;
            *)
                cp "$found" "$dest"
                chmod +x "$dest"
                ;;
        esac
        rm -rf "$tmp"
        log "$name binary installed."
    }

    case "$(uname -s 2>/dev/null)" in
        MINGW*|MSYS*|CYGWIN*|Windows*)
            log "Windows detected — downloading Windows CLI binaries."
            # PhoneInfoga ships Windows builds as .tar.gz (not .zip).
            download_bin phoneinfoga "https://github.com/sundowndev/phoneinfoga/releases/download/v2.11.0/phoneinfoga_Windows_x86_64.tar.gz" || true
            download_bin subfinder "https://github.com/projectdiscovery/subfinder/releases/download/v2.8.0/subfinder_2.8.0_windows_amd64.zip" || true
            download_bin amass "https://github.com/owasp-amass/amass/releases/download/v4.2.0/amass_Windows_amd64.zip" || true
            ;;
        *)
            download_bin phoneinfoga "https://github.com/sundowndev/phoneinfoga/releases/download/v2.11.0/phoneinfoga_Linux_x86_64.tar.gz" || true
            download_bin subfinder "https://github.com/projectdiscovery/subfinder/releases/download/v2.8.0/subfinder_2.8.0_linux_amd64.zip" || true
            download_bin amass "https://github.com/owasp-amass/amass/releases/download/v4.2.0/amass_Linux_amd64.zip" || true
            ;;
    esac

    # Mark installed only when artifacts actually exist.
    mark_if_present() {
        local tool="$1" path="$2"
        if [ -f "$path" ] || [ -f "${path}.exe" ] || [ -d "$path" ]; then
            update_registry "$tool" "true"
        else
            update_registry "$tool" "false"
            warn "$tool not present at $path — marked not installed"
        fi
    }

    mark_if_present "blackbird" "$EXTERNAL_TOOLS/blackbird/blackbird.py"
    mark_if_present "nexfil" "$EXTERNAL_TOOLS/Nexfil"
    mark_if_present "gitfive" "$EXTERNAL_TOOLS/GitFive/main.py"
    mark_if_present "ghunt" "$EXTERNAL_TOOLS/GHunt/main.py"
    mark_if_present "dnsrecon" "$EXTERNAL_TOOLS/dnsrecon/dnsrecon.py"
    mark_if_present "phoneinfoga" "$EXTERNAL_TOOLS/bin/phoneinfoga"
    mark_if_present "subfinder" "$EXTERNAL_TOOLS/bin/subfinder"
    mark_if_present "amass" "$EXTERNAL_TOOLS/bin/amass"
    update_registry "gravatar" "true"
    update_registry "whois" "true"
    update_registry "google_dorking" "true"
    update_registry "platform_probe" "true"
    update_registry "phone_social_intel" "true"
    update_registry "image_intel" "true"

    if [ -f "$PROJECT_ROOT/samurai/main.py" ]; then
        update_registry "samurai" "true"
    else
        update_registry "samurai" "false"
        warn "samurai/ package missing — Instagram/Facebook deep intel unavailable (not in this repo)."
    fi

    log "Extended OSINT catalog tools installed."
}

# ── Pin shared deps so Maigret + graph stack stay compatible ─────────────────
pin_shared_deps() {
    log "Pinning shared dependencies (networkx, lxml, setuptools, httpx)..."
    # Prefer ddgs/google_dorking httpx range; GHunt/GitFive may warn but still run.
    pip_install -q "networkx>=2.6.3,<3.0.0" "lxml>=6.0.2,<7.0" "setuptools<82" \
        "httpx[brotli,http2,socks]>=0.28.1" || true
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
pin_shared_deps

log "Installation complete. Run scripts/verify_tools.sh to validate."
