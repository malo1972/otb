# TODO

## Stable installer name for "latest" downloads

The download button on gambitgear.ch (Opening Tree Builder page) currently
points to one fixed version:

    https://github.com/malo1972/otb/releases/download/v1.0/OTB-Setup-1.0.exe

With a version number in the file name, the link has to be changed on every
release. GitHub only offers an "always the newest file" link if the asset name
stays the same in each release.

- [ ] In `packaging/otb.iss` change `OutputBaseFilename=OTB-Setup-{#AppVersion}`
      to `OutputBaseFilename=OTB-Setup` (the version is still visible in the
      installer itself and in the release title).
- [ ] Optional: upload a copy of the 1.0 installer as `OTB-Setup.exe` to the
      existing v1.0 release, so the new link works right away.
- [ ] Change the button link on the website to:

      https://github.com/malo1972/otb/releases/latest/download/OTB-Setup.exe

  (file `projects/opening-tree-builder.html` in the gambitgear repo, then run
  `./build-de.py`).
