# Breachwright on WSL (Windows Subsystem for Linux)

## Prerequisites

- Windows 11 with WSL2 (WSLg for GUI support)
- Kali Linux or Ubuntu WSL distribution

## Install WSL2 + Kali (if not already installed)

```powershell
# In PowerShell as Administrator
wsl --install -d kali-linux
```

## Install Breachwright

```bash
# Inside your WSL terminal

# Install prerequisites
sudo apt update
sudo apt install -y python3 python3-venv python3-pip nodejs npm \
  python3-gi gir1.2-webkit2-4.1

# Download and extract
cd ~
unzip breachwright-v1.0.zip
cd breachwright
chmod +x install.sh
./install.sh

# Configure
nano ~/.local/share/breachwright/app/.env
# Add: ANTHROPIC_API_KEY=sk-ant-api03-...

# Create admin account
breachwright --setup

# Launch
breachwright
```

## GUI on WSL

**Windows 11 (WSLg):** GUI works automatically. The pywebview window opens natively through WSLg.

**Windows 10 or no WSLg:** Breachwright falls back to opening in your Windows browser at `http://127.0.0.1:13370`. Run in headless mode:

```bash
breachwright --headless
```

Then open `http://127.0.0.1:13370` in your Windows browser (Edge, Chrome, etc.).

## Security Tools

Install the tools you want to use with the Tool Runner:

```bash
sudo apt install -y nmap nikto
sudo apt install -y subfinder httpx-toolkit feroxbuster

# gowitness (optional)
sudo apt install -y golang-go
go install github.com/sensepost/gowitness@latest
export PATH=$PATH:$(go env GOPATH)/bin
```

## Notes

- Data is stored in `~/.local/share/breachwright/` inside WSL
- The app binds to `127.0.0.1:13370` (localhost only, not exposed to your network)
- Tool Runner executes tools inside WSL, so all Linux pentest tools work normally
