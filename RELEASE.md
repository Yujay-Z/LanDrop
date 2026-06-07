# LanDrop Release Checklist

## Local macOS Build

```bash
bash scripts/build_macos.sh
```

Output:

- `dist/LanDrop-macOS.zip`

## Local Windows 11 Build

Run in PowerShell from the repository root:

```powershell
.\scripts\build_windows.ps1
```

Output:

- `dist\LanDrop.exe`

## GitHub Actions Build

Push the repository to GitHub and run the `Build LanDrop` workflow. The workflow builds:

- `LanDrop-macOS`
- `LanDrop-Windows`

## Pre-release Checks

Before sharing a build, verify:

- Web UI starts with `landrop_web.py`
- Two machines are on the same LAN
- Windows Firewall or macOS firewall allows LAN access
- Manual IP and LAN port connection works when discovery is unavailable
- File and folder transfer both work
- Wrong receive code is rejected
