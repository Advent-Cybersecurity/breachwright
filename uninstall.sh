#!/usr/bin/env bash
set -e

RED='\033[0;31m'
CYAN='\033[0;36m'
GREEN='\033[0;32m'
BOLD='\033[1m'
NC='\033[0m'

INSTALL_DIR="$HOME/.local/share/breachwright"
BIN_DIR="$HOME/.local/bin"
DESKTOP_DIR="$HOME/.local/share/applications"

echo ""
echo -e "${RED}${BOLD}  Breachwright Uninstaller${NC}"
echo ""

read -p "  Remove Breachwright? Your data will be preserved. (y/N): " confirm
if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
    echo "  Cancelled."
    exit 0
fi

echo ""

# Remove desktop entry
[ -f "$DESKTOP_DIR/breachwright.desktop" ] && rm "$DESKTOP_DIR/breachwright.desktop" && echo -e "  ${CYAN}[*]${NC} Removed desktop entry"

# Remove launcher
[ -f "$BIN_DIR/breachwright" ] && rm "$BIN_DIR/breachwright" && echo -e "  ${CYAN}[*]${NC} Removed launcher"

# Remove app and venv (keep data directory)
[ -d "$INSTALL_DIR/app" ] && rm -rf "$INSTALL_DIR/app" && echo -e "  ${CYAN}[*]${NC} Removed application files"
[ -d "$INSTALL_DIR/venv" ] && rm -rf "$INSTALL_DIR/venv" && echo -e "  ${CYAN}[*]${NC} Removed virtual environment"
[ -f "$INSTALL_DIR/icon.svg" ] && rm "$INSTALL_DIR/icon.svg"

echo ""
echo -e "  ${GREEN}[+]${NC} Uninstall complete."
echo ""
echo -e "  Your data was preserved at: ${CYAN}$INSTALL_DIR/data/${NC}"
echo "  To remove all data: rm -rf $INSTALL_DIR"
echo ""
