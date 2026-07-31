# Installing Breachwright

Breachwright releases use separate Windows and Linux archives built from the
same source. Both contain the complete open-source feature set.

## Before installing

Download the archive for your operating system from the GitHub release. Check
its SHA-256 value against the checksum published with that release before
running it.

Windows PowerShell:

```powershell
Get-FileHash .\breachwright-*-windows-x64.zip -Algorithm SHA256
```

Linux:

```bash
sha256sum breachwright-*-linux-x64.tar.gz
```

Extract the complete archive. Breachwright must remain beside its `_internal`
directory and installer files.

## Windows x64

1. Extract the ZIP.
2. Open the extracted `Breachwright` folder.
3. Run `install-windows.bat`.
4. Start Breachwright from the desktop or Start menu shortcut.
5. Follow the first-run screen to create the administrator account.

Application files are installed in `%LOCALAPPDATA%\Breachwright`. Assessment
data, reports, evidence, backups, configuration, and logs are stored separately
in `%APPDATA%\Breachwright`, so an application upgrade does not replace them.

The command-line companion is installed as:

```text
%LOCALAPPDATA%\Breachwright\BreachwrightCLI.exe
```

Run `%LOCALAPPDATA%\Breachwright\uninstall-windows.bat` to uninstall. The
uninstaller asks separately before deleting application data.

## Linux x64

The desktop window requires GTK3, WebKitGTK, and PyGObject. On Debian or Ubuntu:

```bash
sudo apt-get install python3-gi python3-gi-cairo gir1.2-gtk-3.0 gir1.2-webkit2-4.1
```

Other distributions provide equivalent GTK3, WebKitGTK, and GObject
introspection packages.

Extract and install the archive:

```bash
tar -xzf breachwright-*-linux-x64.tar.gz
cd Breachwright
./install.sh
```

Open a new terminal if the installer added `~/.local/bin` to `PATH`, then run:

```bash
breachwright
```

Follow the first-run screen to create the administrator account. The
application-menu entry can also launch Breachwright.

Application files and data use:

```text
${XDG_DATA_HOME:-$HOME/.local/share}/breachwright/
├── bin/        application files
└── data/       database, evidence, reports, backups, configuration, and logs
```

The command-line companion is:

```text
${XDG_DATA_HOME:-$HOME/.local/share}/breachwright/bin/BreachwrightCLI
```

Run the installed uninstaller with:

```bash
"${XDG_DATA_HOME:-$HOME/.local/share}/breachwright/bin/uninstall.sh"
```

Application data is preserved unless you delete the `data` directory
separately.

## Backup before upgrading

Administrators can create a verified backup from **Settings > Data Safety**.
Backups include the SQLite database, evidence, uploaded scans, and reports.
API keys and token-signing secrets are excluded.

For command-line backup and restore instructions, including the required
offline restore process, read [docs/DATA_SAFETY.md](docs/DATA_SAFETY.md).

## AI providers are optional

Manual findings, evidence management, checklists, local reports, export/import,
and backups work without an AI provider. Optional third-party AI services may
charge for their own API usage. Local compatible model servers can be
configured in **Settings** without a commercial AI API.
