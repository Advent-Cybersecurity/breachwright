# Breachwright on WSL (Windows Subsystem for Linux)

Breachwright was created by Advent Cybersecurity and is fully open source. WSL
is useful for testing its Linux build on a Windows computer. It is optional for
Windows users, who can use the native Windows archive.

## Prerequisites

- Windows 11 with WSL 2 and WSLg for the desktop window
- A current Ubuntu, Debian, or Kali WSL distribution

To install Ubuntu from an administrator PowerShell window:

```powershell
wsl --install -d Ubuntu
```

## Install the Linux release

Download the `breachwright-*-linux-x64.tar.gz` archive from the matching
GitHub release. Inside the WSL terminal, install the desktop dependencies and
then run the included installer:

```bash
sudo apt-get update
sudo apt-get install -y python3-gi python3-gi-cairo \
  gir1.2-gtk-3.0 gir1.2-webkit2-4.1

tar -xzf breachwright-*-linux-x64.tar.gz
cd Breachwright
./install.sh
breachwright
```

Breachwright opens directly into the local owner workspace. There is no
account, password, or setup command.

## Browser mode

When a desktop window is unavailable, run:

```bash
breachwright --headless
```

Then open `http://127.0.0.1:13370` in a Windows browser. Breachwright binds to
localhost only and must not be exposed to the network because it has no
application login.

## Optional security tools

The Tool Runner uses programs installed inside the WSL distribution. Install
only the tools you intend to run and review their own documentation first. For
example:

```bash
sudo apt-get install -y nmap nikto
```

## Data and configuration

- Application data is stored under
  `${XDG_DATA_HOME:-$HOME/.local/share}/breachwright/data` inside WSL.
- Configure optional AI providers from **Settings** after launch. AI is not
  required for scanning, findings, evidence, reports, or project transfer.
- Back up the workspace from **Settings > Data Safety** before upgrading or
  removing the WSL distribution.
- For the native Windows installation and full Linux instructions, read
  [INSTALL.md](INSTALL.md).
