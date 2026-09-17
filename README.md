# Opening Tree Builder (OTB)

![](screenshot.png)


## What is it?

**OTB** stands for "**O**pening **T**ree **B**uilder". I know this acronym is occupied, it's a tribute to "Over The Board" chess &#128521;

OTB lets you build and save your opening repertoire in a single polyglot file. The polyglot format has many advantages over PGN like interchangeability with other tools like SCID, easy detection of transpositions, weighing of branches and many more (see https://chessprogramming.org/PolyGlot)

OTB offers a browse-mode (green), where the moves that you enter to the chessbaord are **NOT** saved. In edit-mode (red) every move you enter is immediately saved to the polyglot file without additional user interaction (default name is book.bin, but you can create your own files). The currently used book and further status information is displayed in the bottom statusbar.

Building your opening tree can be done by entering your moves in edit-mode. Only in edit-mode (red) they are automatically saved to file. You can expand your opening tree by importing PGN-files via <kbd>File</kbd> &rarr; <kbd>Import PGN...</kbd> (e.g. PGN's that you exported from other tools)
Deletion is done via right-click on a move in edit-mode. Caution: all attached branches of the tree are also deleted!

## How to Run OTB

For quick evaluation and distribution for now the python package is managed by `uv` : https://docs.astral.sh/uv/. 

Installers will follow for every OS...

### 3. Download the project from github into a project-folder of your choice
* `otb.py` : the single-file python code 
* `pyproject.toml` : description of dependencies used by `uv` to create a virtual environment
* `uv.lock` : the currently used dependencies (for reproducible builds to prevent "works on my machine")

### 2. Install `uv` (One-time setup)
- **macOS / Linux:** Run this in your terminal:
  ```
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```
- **Windows:** Run this in PowerShell:
  ```
  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
  ```

### 3. Launch the Application
Open a terminal in this project folder and run:
```
uv run otb.py
```
- **Windows** :
  you can create a shortcut in explorer: Right-click within your project-folder and select <kbd>new</kbd> &rarr; <kbd>shortcut</kbd>. Then enter this to the location field (replace path):
  ```
  C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe -ExecutionPolicy Bypass -NoExit -Command "Set-Location 'C:\path\po\Projectfolder'; uv run otb.py"
  ```

*(This automatically downloads Python if needed, creates a virtual environment, installs PyQt6 and python-chess, and launches the app.)*

### 4. Use an Engine

If you want to see engine-evaluation use the Engine-toggle-button (a blue arrow indicates the engine's top choice) you need to tell OTB where to find the engine's executable (only once).
Download your preferred engine (e.g. from https://stockfishchess.org/).
Then point OTB to the location of the engine's executable via <kbd>File</kbd> &rarr; <kbd>Select Engine...</kbd>


## Features to wish for
* edit weight for each move via context menu and sort the list by that value
* when hitting a transposition, show the multiple paths how to get there
