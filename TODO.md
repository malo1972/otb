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
- [ ] Change the button link on the website to:

      https://github.com/malo1972/otb/releases/latest/download/OTB-Setup.exe

  (file `projects/opening-tree-builder.html` in the gambitgear repo, then run
  `./build-de.py`).
