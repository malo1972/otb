# Opening Tree Builder (OTB)

![](screenshot.png)


## What is it?

**OTB** stands for "**O**pening **T**ree **B**uilder". I know this acronym is occupied, it's a tribute to "Over The Board" chess &#128521;

OTB lets you build and save your opening repertoire to a single polyglot file.    
The polyglot format has many advantages over PGN: interchangeability with other tools like SCID, easy detection of transpositions, weigthing of branches and many more:  
https://chessprogramming.org/PolyGlot

OTB offers a $\color{#00FF00}{\text{view-mode (green switch)}}$, where moves that you enter in the chessboard are **NOT** saved.   
In $\color{#FF0000}{\text{build-mode (red board)}}$ every move you enter is immediately saved to the polyglot file without additional user interaction.   
The default-filename name is book.bin, but you can create your own files via <kbd>File</kbd> &rarr; <kbd>New Book</kbd>   
The currently used book and further status information is displayed in the bottom statusbar.

**<ins>Book color</ins>**: a repertoire is normally built for one side. When you create a book you choose **White**, **Black** or **Both**.   
The color is stored inside the book file and shown in the file name (`W_`, `B_` or `WB_`) and in the statusbar; the board turns to that side when the book is opened.   
For an existing book OTB asks for the color when you open it; change it any time via <kbd>File</kbd> &rarr; <kbd>Set Book Color</kbd>

You can also expand your opening tree by importing PGN-files via <kbd>File</kbd> &rarr;   <kbd>Import PGN</kbd> (e.g. PGN's that you exported from other tools).   
Before the import you can tick one or more players and choose a color: then only the games they played as White, as Black or with both colors are imported.   
If that color does not fit the book, OTB offers to create a new book for it.

**<ins>Deletion</ins>** is done via right-click on a move in build-mode.   
CAUTION: all attached branches to follow behind that node will also be deleted, except positions that can still be reached by another move order.   
Right-click also lets you edit a move's weight (how often it is chosen by engines/GUIs using the book).   

**<ins>Transpositions</ins>** are chess positions, that can be reached by different move orders.\
The predecessor-moves to a transposition are marked in red in the bookmove-list.\   
Right-click transpositions to see all move orders leading there.\
Left-click a line or use the cursor up/down keys to load it to the editor, right-click to copy it as PGN.

**<ins>Autoplay from here</ins>**: right-click a move in the current line to play the line automatically from that move to its end. Any click or key stops it.

**<ins>Arrows and circles</ins>**: draw green arrows on the board with the right mouse button (drag from one square to another), or a circle by right-clicking a square. They are only for looking: they disappear when you leave the position and are never saved.

**<ins>Book folder</ins>**: new books are created in the book folder, which you can change via <kbd>File</kbd> &rarr; <kbd>Set Book Folder</kbd>

**<ins>View menu</ins>**: sets the autoplay speed, the speed of the piece animation and the board coordinates (inside the board, outside the board or none).

## Install OTB

### Windows
**[⬇ Download the installer (OTB-Setup.exe)](https://github.com/malo1972/otb/releases/latest/download/OTB-Setup.exe)**

Run the downloaded file and follow the installer — no Python or admin rights needed. It adds OTB to the Start menu (and, if you like, to the desktop).   
To update, just run the new installer: it replaces the old version and keeps your books and settings.   
Windows may show *"Windows protected your PC"*: click **More info** &rarr; **Run anyway**.

---

### Linux
Install OTB from the Snap Store, e.g. in Ubuntu's App Center (search for *Opening Tree Builder*), or in a terminal:
```
sudo snap install opening-tree-builder
```
Stockfish is included. A Flatpak for Flathub is on its way.

---

### Mac (and Linux from source)
OTB runs directly from source, managed by [`uv`](https://docs.astral.sh/uv/):

**1.** **[⬇ Download OTB (zip)](https://github.com/malo1972/otb/archive/refs/heads/main.zip)** and unzip it into a folder of your choice.

**2.** Install `uv` (one-time setup) in your terminal:
```
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**3.** Open a terminal in the OTB folder and run:
```
uv run otb.py
```

*(This automatically downloads Python if needed, creates a virtual environment, installs PyQt6 and python-chess, and launches the app.)*

---

### Engine evaluation

OTB uses [Stockfish](https://stockfishchess.org/) as its engine. Toggle the engine-switch to turn it on.     
A blue arrow will indicate the engine's top choice, the current engine-evaluation is shown leftmost in the statusbar.

**Windows and Linux (Snap / Flatpak):** Stockfish is included, nothing to set up.   
**Mac / running from source:** install Stockfish once, OTB finds it automatically:
```
brew install stockfish          # Mac
sudo apt install stockfish      # Ubuntu / Debian
```


## Features to wish for
* Add comments to moves
* You name it. please let me know features that you would like to see implemented
