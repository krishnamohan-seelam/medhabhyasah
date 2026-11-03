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
