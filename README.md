# Opening Tree Builder (OTB)


## What is it?

OTB stands for "Opening Tree Builder". I know this acronym is occupied, it's a tribute to "Over The Board" chess &#128521;

OTB lets you build and save your opening repertoire in a single polyglot file. The polyglot format has many advantages over PGN like interchangeability with other tools like SCID, easy detection of transpositions, weighing of branches and many more (see https://chessprogramming.org/PolyGlot)

OTB offers a browse-mode (green), where the moves that you enter to the chessbaord are not saved. In edit-mode (red) every move you enter is immediately saved to the polyglot file without additional user interaction (default name is book.bin, but you can create your own files). The currently used book and further status information is displayed in the bottom statusbar.

Building your opening tree can be done by entering your moves in edit mode. Only in edit-mode (red) they are automatically saved to file. You can expand your opening tree by importing PGN-files via File->Import PGN...(e.g. PGN's that you exported from other tools)
Deletion is done via right-click on a move in edit-mode. Caution: all attached branches of the tree are also deleted!

## How to Run

### 3. Download the project from github into a project-folder of your choice
* `otb.py` : the single-file python code 
* `pyproject.toml` : description of dependencies used by uv to create a virtual environment
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
  you can create a shortcut in explorer: Right-click in the projectfolder and select new->shortcut. Then enter this to the location field (replace path):
  C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe -ExecutionPolicy Bypass -NoExit -Command "Set-Location 'C:\path\po\Projectfolder'; uv run otb.py"

*(This automatically downloads Python if needed, creates a virtual environment, installs PyQt6 and python-chess, and launches the app.)*


## Features to wish for
* edit weight for each move via context menu 
* when hitting a transposition, show the multiple paths how to get there
