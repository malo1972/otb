# CLAUDE.md – Opening Tree Builder (OTB)

Desktop app to build and save a chess opening repertoire offline.
Single-file Python app `otb.py` (PyQt6 + python-chess), licence GPL-3.0-or-later.
Repo: https://github.com/malo1972/otb · project page: https://gambitgear.ch/projects/opening-tree-builder.html

## Structure
- `otb.py` – the whole application
- `pyproject.toml`, `uv.lock` – dependencies; run from source with `uv run otb.py`
- `packaging/otb.iss` – Inno Setup script for the Windows installer `OTB-Setup.exe`
  (name has no version on purpose: the website links to
  `releases/latest/download/OTB-Setup.exe`)
- `README.md` – user manual; Mac/Linux install via `uv`
- `TODO.md` – open tasks

## Open task: Linux packages (Snap and Flatpak)
See `TODO.md`, section "Linux packages: Snap and Flatpak". Both are wanted:
Snap for Ubuntu's App Center, Flatpak for Flathub. Key decisions: OTB always
uses Stockfish (no engine selection); bundle it inside each package so engine
evaluation works in the sandbox; do not rely on host engines
(`flatpak-spawn --host`).

## Working rules
- Commit only when asked; commit messages in English (as in the existing history).
- Keep the installer file name stable (`OTB-Setup.exe`) across releases.
