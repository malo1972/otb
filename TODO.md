# TODO

## Stable installer name for "latest" downloads

Done in the repo with release 1.1: the installer is now always called
`OTB-Setup.exe` and the README links to the newest release. Still open is the
website. The download button on gambitgear.ch (Opening Tree Builder page)
points to one fixed version:

    https://github.com/malo1972/otb/releases/download/v1.0/OTB-Setup-1.0.exe

With a version number in the file name, the link has to be changed on every
release. GitHub only offers an "always the newest file" link if the asset name
stays the same in each release.

- [x] In `packaging/otb.iss` change `OutputBaseFilename=OTB-Setup-{#AppVersion}`
      to `OutputBaseFilename=OTB-Setup` (the version is still visible in the
      installer itself and in the release title).
- [x] Change the button link on the website to (done 2026-11-14):

      https://github.com/malo1972/otb/releases/latest/download/OTB-Setup.exe

  (file `projects/opening-tree-builder.html` in the gambitgear repo, then run
  `./build-de.py`).

## Linux packages: Snap and Flatpak (next task, planned 2026-11-14)

Goal: Linux users find OTB in their software centre and install it with one
click, instead of the README's zip + `uv` + terminal steps. Both packages are
needed, because the stores don't overlap:
- **Snap (Snap Store)**: the only source Ubuntu's App Center searches.
- **Flatpak (Flathub)**: the standard on Fedora, Linux Mint, Pop!_OS and most
  other distributions; Ubuntu does not show Flathub by default.

Order: shared groundwork first, then the Snap (most beta testers use Ubuntu),
then the Flatpak.

### Shared groundwork (used by both) – done 2026-11-14, untested in a sandbox
- [x] App ID (reverse domain): `ch.gambitgear.OTB`; snap name
      `opening-tree-builder` (free on 2026-11-14 – register it early).
- [x] `packaging/linux/`: desktop file `ch.gambitgear.OTB.desktop` (runs the
      command `otb`, which each package has to provide), icons 32–256 px
      from `otb_icon.png`, AppStream metainfo
      `ch.gambitgear.OTB.metainfo.xml` (store text, releases 1.0 and 1.1,
      licence). Passes `desktop-file-validate` and `appstreamcli validate`.
      Snapcraft reads the same metainfo (`adopt-info`).
- [ ] Screenshot: the metainfo points to `screenshot.png` in the repo, which
      still shows the old green board – replace it before submitting.
- [ ] Stockfish built from source as part of each package (Flathub requires
      building from source; GPL, like OTB). `_engine_path()` already finds it
      on the package's PATH (`shutil.which`), so install it as `bin/stockfish`.
- [x] `_desktop_file_name()`: Flatpak → `ch.gambitgear.OTB`, Snap →
      `<snap>_<snap>` (so the snap's app must be named like the snap),
      from source → `otb`.
- [x] Default book in a sandbox: `Documents/OTB/book.bin` in the real home
      (`_sandbox_documents_dir()`), instead of the sandbox's hidden data
      folder. The folder's localized name ("Dokumente") is read from
      `~/.config/user-dirs.dirs`; grant read access to that file
      (Flatpak `--filesystem=xdg-config/user-dirs.dirs:ro`, Snap
      `personal-files` plug) or it falls back to "Documents".
- [ ] Permissions: Flatpak `--filesystem=xdg-documents` (books) plus the
      file-chooser portal for PGN files elsewhere; Snap plugs `home`,
      `removable-media`. Test Open Book / Set Book Folder / Import PGN.

### Snap
- [x] Snapcraft account (Ubuntu One), name `opening-tree-builder` registered
      (2026-11-14).
- [x] `snap/snapcraft.yaml` written (2026-11-14): base `core24`, strict,
      gnome extension, PyQt6 wheels (own Qt), Stockfish sf_19 built from source
      into `otb/engines/`; plugs home, removable-media. Not built yet.
- [x] Built locally, tested OK (2026-11-14). Size 108 MB (Stockfish alone
      95 MB unpacked; unused Qt parts removed in the recipe).
- [x] Revision 1 uploaded to `edge` (2026-11-14), passed automatic review.
- [ ] Test from the store (`snap install opening-tree-builder --edge`),
      then release to `stable`.
- [ ] Store page: title, summary, description, icon, screenshots.
- [ ] GitHub Actions: build and upload on each `v*` tag
      (snapcore/action-build, snapcore/action-publish) to the `stable` channel
      – only stable releases are found by search.

### Flatpak

Goal: Linux users install OTB with one click from their software centre
(Flathub) instead of the README's zip + `uv` + terminal steps. Build and test a
local Flatpak first; Flathub submission later.

Why Flatpak: one package for all distributions (Ubuntu, Fedora, Mint, Arch …),
Python + PyQt6 + python-chess bundled (no `uv`, no Python setup), automatic
updates, sandbox, visibility on Flathub (link back to gambitgear.ch).

Decisions so far:
- **Bundle Stockfish inside the Flatpak.** OTB loads a UCI engine via
  File › Select Engine…; the sandbox cannot start programs from the host by
  default. Bundling Stockfish (GPL, like OTB) makes engine evaluation work out of
  the box. Allowing host engines via `flatpak-spawn --host` is possible but
  Flathub reviewers dislike it – avoid. Pre-select the bundled engine when no
  engine is configured. (Since then OTB always uses Stockfish and has no
  engine selection any more; the Flatpak only has to put it where
  `_engine_path()` looks.)
- File access (PGN, Polyglot .bin) through the normal Qt file dialog, which uses
  the Flatpak file-chooser portal; check that open/save works in the sandbox.

Steps:
- [ ] Install the build tool: `sudo apt install flatpak-builder` (flatpak itself
      and the flathub remote are already set up).
- [ ] App ID (reverse domain), e.g. `ch.gambitgear.OTB`.
- [ ] Manifest: KDE/Qt6 runtime or freedesktop runtime + PyQt6; python-chess as
      pip module (flatpak-pip-generator); Stockfish built from source as a module.
- [ ] Desktop file, icon (`otb_icon.png`, needs sizes / SVG), AppStream
      metainfo (description, screenshot `screenshot.png`, release notes, licence).
- [ ] Build and run locally (`flatpak-builder --user --install …`), test: board,
      PGN import, Polyglot save/load, engine evaluation with bundled Stockfish.
- [ ] README: Linux section → Flatpak install instead of uv (keep uv for Mac).
- [ ] Later: submit to Flathub; then the website's "Install instructions
      Mac / Linux" button could point Linux users to Flathub.
