# Packaging Medhabhyasah

## Prerequisites

- Python 3.11+
- [Inno Setup 6](https://jrsoftware.org/isinfo.php) (for the installer)

## 1. Install build dependencies

```
uv sync --extra package
```

## 2. Build the PyInstaller bundle

```
uv run python scripts/build.py
```

This produces `dist/Medhabhyasah/` — a self-contained directory that runs without Python installed.

### Verify the bundle

```
dist\Medhabhyasah\Medhabhyasah.exe
```

The app should open the pywebview window and show the first-run setup screen.

## 3. Build the installer (optional)

Open `packaging/medhabhyasah.iss` in Inno Setup and compile, or run from the command line:

```
iscc packaging\medhabhyasah.iss
```

This produces `installer_output/Medhabhyasah-Setup.exe`.

## Where things go

| What | Location |
|------|----------|
| Application files | `%LOCALAPPDATA%\Medhabhyasah\` |
| SQLite database | `%APPDATA%\Medhabhyasah\medhabhyasah.db` |
| Start Menu shortcut | `Medhabhyasah` group |

The database directory survives upgrades — reinstalling the app does not touch `%APPDATA%`.

## Installing on another machine

1. Copy `installer_output/Medhabhyasah-Setup.exe` to the other PC and run it. No admin rights or Python are needed.
2. The target PC needs Windows 10 or 11 (64-bit) and the Microsoft Edge WebView2 Runtime. Windows 11 includes it. The installer checks for it and points to the download page if it is missing.
3. On first launch, set the parent PIN and add the API key. The PIN and API keys live in that PC's Windows Credential Manager, so they do not travel with the installer.
4. Questions, students and results live in `%APPDATA%\Medhabhyasah\medhabhyasah.db`. To move them, copy that file to the same folder on the new PC before first launch.

`AppId` in `medhabhyasah.iss` must stay the same across releases so a newer installer upgrades in place. Bump `AppVersion` here and `version` in `pyproject.toml` together.

The installer is not code-signed, so Windows SmartScreen may warn on first run. Choose "More info", then "Run anyway".

## Changing the AI model

The parent picks the provider, model id and token prices in Settings. They are saved in `%APPDATA%\Medhabhyasah\models.json` (no keys in that file). If a provider retires a model or rejects the key, generation stops with a message that links to the provider's model list, deprecation page and key page.
