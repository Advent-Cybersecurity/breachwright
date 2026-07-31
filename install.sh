#!/usr/bin/env bash
set -e

# ================================================================
#  BREACHWRIGHT INSTALLER
#  An Advent Cybersecurity Product
#
#  Detects whether it's running from:
#    A) A pre-built binary bundle (dist/Breachwright/ exists)
#    B) Source code (backend/ + frontend/ exist)
#  And installs accordingly.
# ================================================================

RED='\033[0;31m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[0;33m'
BOLD='\033[1m'
NC='\033[0m'

XDG_DATA_ROOT="${XDG_DATA_HOME:-$HOME/.local/share}"
INSTALL_DIR="$XDG_DATA_ROOT/breachwright"
DATA_DIR="$INSTALL_DIR/data"
LEGACY_INSTALL_DIR="$HOME/.local/share/breachwright"
BIN_DIR="$HOME/.local/bin"
DESKTOP_DIR="$XDG_DATA_ROOT/applications"

banner() {
    echo ""
    echo -e "${RED}${BOLD}"
    echo "  ╔══════════════════════════════════════════════╗"
    echo "  ║            BREACHWRIGHT INSTALLER            ║"
    echo "  ║         An Advent Cybersecurity Product       ║"
    echo "  ╚══════════════════════════════════════════════╝"
    echo -e "${NC}"
    echo ""
}

info()    { echo -e "  ${CYAN}[*]${NC} $1"; }
success() { echo -e "  ${GREEN}[+]${NC} $1"; }
warn()    { echo -e "  ${YELLOW}[!]${NC} $1"; }
fail()    { echo -e "  ${RED}[!]${NC} $1"; exit 1; }

banner

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Detect install mode ──
BINARY_DIR=""
if [ -f "$SCRIPT_DIR/Breachwright" ] && [ -d "$SCRIPT_DIR/_internal" ]; then
    # We're inside an extracted binary bundle
    BINARY_DIR="$SCRIPT_DIR"
    info "Detected: pre-built binary bundle"
elif [ -d "$SCRIPT_DIR/dist/Breachwright" ] && [ -f "$SCRIPT_DIR/dist/Breachwright/Breachwright" ]; then
    # We're in the project root with a built dist/
    BINARY_DIR="$SCRIPT_DIR/dist/Breachwright"
    info "Detected: built binary in dist/"
elif [ -d "$SCRIPT_DIR/backend" ] && [ -d "$SCRIPT_DIR/frontend" ]; then
    info "Detected: source install"
else
    fail "Cannot determine install mode. Run from project root or extracted binary."
fi

# Older installers did not honor XDG_DATA_HOME. Move that installation only
# when the new target does not already exist, so no data is overwritten.
if [ "$INSTALL_DIR" != "$LEGACY_INSTALL_DIR" ] \
    && [ -d "$LEGACY_INSTALL_DIR" ] \
    && [ ! -e "$INSTALL_DIR" ]; then
    mkdir -p "$(dirname "$INSTALL_DIR")"
    mv "$LEGACY_INSTALL_DIR" "$INSTALL_DIR"
    warn "Migrated the previous installation to $INSTALL_DIR"
fi

# ── Create directories ──
mkdir -p "$INSTALL_DIR" "$BIN_DIR" "$DESKTOP_DIR"
mkdir -p "$DATA_DIR"

# Move data written by older launchers into the intended preserved directory.
migration_safety=""
for item in breachwright.db .env .secret_key uploads reports backups logs evidence jobs; do
    if [ -e "$INSTALL_DIR/$item" ]; then
        if [ -e "$DATA_DIR/$item" ]; then
            if [ -z "$migration_safety" ]; then
                migration_safety="$DATA_DIR/migration-safety-$(date +%Y%m%d-%H%M%S)-$$"
                mkdir -p "$migration_safety"
                warn "Preserving pre-existing data-folder contents in $migration_safety"
            fi
            mv "$DATA_DIR/$item" "$migration_safety/$item"
        fi
        mv "$INSTALL_DIR/$item" "$DATA_DIR/$item"
    fi
done
mkdir -p "$DATA_DIR/uploads"
mkdir -p "$DATA_DIR/reports"
mkdir -p "$DATA_DIR/backups"
mkdir -p "$DATA_DIR/logs"

# ================================================================
#  BINARY INSTALL
# ================================================================
if [ -n "$BINARY_DIR" ]; then
    info "Installing binary to $INSTALL_DIR/bin/"

    # Copy binary bundle
    rm -rf "$INSTALL_DIR/bin"
    mkdir -p "$INSTALL_DIR/bin"
    cp -a "$BINARY_DIR/." "$INSTALL_DIR/bin/"
    chmod +x "$INSTALL_DIR/bin/Breachwright"

    success "Binary installed ($(du -sh "$INSTALL_DIR/bin" | cut -f1))"

    # Create launcher
    cat > "$BIN_DIR/breachwright" << LAUNCHER
#!/usr/bin/env bash
export DATA_DIR="\${DATA_DIR:-$DATA_DIR}"
exec "$INSTALL_DIR/bin/Breachwright" "\$@"
LAUNCHER
    chmod +x "$BIN_DIR/breachwright"
    success "Launcher: $BIN_DIR/breachwright"

# ================================================================
#  SOURCE INSTALL (fallback)
# ================================================================
else
    info "Installing from source to $INSTALL_DIR/app/"

    # Pre-flight
    command -v python3 >/dev/null 2>&1 || fail "python3 not found"
    command -v node >/dev/null 2>&1 || fail "node not found"
    command -v npm >/dev/null 2>&1 || fail "npm not found"

    # System deps for native window
    if command -v apt >/dev/null 2>&1; then
        info "Installing system dependencies..."
        sudo apt install -y -qq \
            python3-venv python3-gi python3-gi-cairo \
            gir1.2-webkit2-4.1 libgirepository1.0-dev \
            gcc libcairo2-dev pkg-config python3-dev 2>/dev/null || {
                warn "Some system packages may not have installed."
                warn "The app will fall back to browser mode if the native window fails."
            }
    fi

    # Copy app files
    VENV_DIR="$INSTALL_DIR/venv"
    APP_DIR="$INSTALL_DIR/app"

    rm -rf "$APP_DIR"
    mkdir -p "$APP_DIR"
    cp -r "$SCRIPT_DIR/backend" "$APP_DIR/backend"
    cp -r "$SCRIPT_DIR/frontend" "$APP_DIR/frontend"
    cp "$SCRIPT_DIR/run.py" "$APP_DIR/run.py"
    [ -f "$SCRIPT_DIR/.env" ] && cp "$SCRIPT_DIR/.env" "$APP_DIR/.env"

    # Python venv
    info "Creating Python virtual environment..."
    python3 -m venv "$VENV_DIR" --system-site-packages
    source "$VENV_DIR/bin/activate"
    pip install --quiet --upgrade pip
    pip install --quiet -r "$APP_DIR/backend/requirements.txt"
    success "Python dependencies installed"

    # Build frontend
    info "Building frontend..."
    cd "$APP_DIR/frontend"
    npm install --silent --no-fund --no-audit 2>/dev/null
    npm run build 2>/dev/null
    rm -rf "$APP_DIR/frontend/node_modules"
    success "Frontend built"
    cd "$SCRIPT_DIR"

    # Create launcher
    cat > "$BIN_DIR/breachwright" << LAUNCHER
#!/usr/bin/env bash
export DATA_DIR="\${DATA_DIR:-$DATA_DIR}"
source "$VENV_DIR/bin/activate"
cd "$APP_DIR"
exec python run.py "\$@"
LAUNCHER
    chmod +x "$BIN_DIR/breachwright"
    success "Launcher: $BIN_DIR/breachwright"
fi

# ================================================================
#  COMMON SETUP (both modes)
# ================================================================

# .env file
if [ ! -f "$DATA_DIR/.env" ]; then
    if [ -f "$SCRIPT_DIR/.env" ]; then
        cp "$SCRIPT_DIR/.env" "$DATA_DIR/.env"
    elif [ -f "$SCRIPT_DIR/.env.example" ]; then
        cp "$SCRIPT_DIR/.env.example" "$DATA_DIR/.env"
    fi
fi

# Icon
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -f "$SCRIPT_DIR/icon.png" ]; then
    cp "$SCRIPT_DIR/icon.png" "$INSTALL_DIR/icon.png"
elif [ -f "$INSTALL_DIR/bin/_internal/icon.png" ]; then
    cp "$INSTALL_DIR/bin/_internal/icon.png" "$INSTALL_DIR/icon.png"
fi

# Desktop entry
cat > "$DESKTOP_DIR/breachwright.desktop" << DESKTOPEOF
[Desktop Entry]
Name=Breachwright
Comment=AI-Powered Penetration Testing Assistant
Exec=$BIN_DIR/breachwright
Icon=$INSTALL_DIR/icon.png
Terminal=false
Type=Application
Categories=Security;Network;Utility;
Keywords=pentest;security;vulnerability;offensive;
StartupNotify=true
StartupWMClass=breachwright
DESKTOPEOF
chmod +x "$DESKTOP_DIR/breachwright.desktop"
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true

# Ensure ~/.local/bin is in PATH
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
    info "Adding $BIN_DIR to PATH..."
    for rc in "$HOME/.bashrc" "$HOME/.zshrc"; do
        if [ -f "$rc" ]; then
            if ! grep -q '\.local/bin' "$rc"; then
                echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$rc"
            fi
        fi
    done
    export PATH="$BIN_DIR:$PATH"
fi

# ── Done ──
echo ""
echo -e "${GREEN}${BOLD}  ================================================================"
echo "  INSTALLATION COMPLETE"
echo -e "  ================================================================${NC}"
echo ""
if [ -n "$BINARY_DIR" ]; then
    echo "  Installed from: pre-built binary"
else
    echo "  Installed from: source"
fi
echo ""
echo -e "  ${BOLD}Launch:${NC}"
echo -e "     ${CYAN}breachwright${NC}"
echo "     Breachwright opens directly into your local workspace."
echo ""
echo "  Or find it in your application menu under 'Security'."
echo ""
echo -e "  Data stored in: ${CYAN}$DATA_DIR/${NC}"
echo ""
