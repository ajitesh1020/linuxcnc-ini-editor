# LinuxCNC INI Configuration Editor

A desktop GUI application for editing LinuxCNC machine configuration files (`.ini`) safely and efficiently — without manually editing raw text files or risking formatting errors.

Built with Python and PySide6 (Qt6). Designed for CNC operators and integrators running LinuxCNC on Ubuntu/Debian-based systems.

---

## Table of Contents

- [Features](#features)
- [Screenshots](#screenshots)
- [Project Structure](#project-structure)
- [Requirements](#requirements)
- [Installation](#installation)
- [Usage](#usage)
- [Configuration Tabs Explained](#configuration-tabs-explained)
- [How It Works Internally](#how-it-works-internally)
- [Known Limitations](#known-limitations)
- [Contributing](#contributing)
- [License](#license)

---

## Features

| Feature | Details |
|---|---|
| **Safe INI parsing** | Custom `IniFileHandler` preserves duplicate keys (`PROGRAM_EXTENSION`, `HALFILE`, `MDI_COMMAND`, `REMAP`) that Python's `configparser` silently discards |
| **Non-destructive saving** | Original file structure, comments, blank lines, and key casing are preserved on every save |
| **Automatic backup** | A timestamped `.backup.YYYYMMDD_HHMMSS` copy is created before every write |
| **Axis configuration** | Edit all `AXIS_X/Y/Z` and `JOINT_0/1/2` parameters in a side-by-side panel |
| **Scale calculator** | Built-in dialog computes corrected axis scale from commanded vs. measured distance |
| **ATC rack configuration** | Configure automatic tool changer positions, speeds, and all 9 individual tool pocket coordinates |
| **Trajectory, Filter, Display, RS274NGC, HAL tabs** | Every major INI section is covered |
| **Responsive layout** | All panels, input fields, and text areas scale correctly when the window is resized or maximised |
| **Comprehensive logging** | DEBUG-level log written to `linuxcnc_editor_debug.log` for troubleshooting |

---

## Screenshots

> _Add screenshots here after your first run. Place `.png` files in `docs/screenshots/` and reference them below._

```
docs/
└── screenshots/
    ├── axis_tab.png
    ├── atc_tab.png
    ├── hal_tab.png
    └── scale_calculator.png
```

---

## Project Structure

```
linuxcnc-ini-editor/
│
├── main.py                  # Entry point — creates QApplication, sets up root logging
├── gui.py                   # Main window, all tabs, IniFileHandler, layout logic
├── scale_calculator.py      # Standalone dialog: calculates corrected axis scale
│
├── requirements.txt         # Python package dependencies (PySide6 only)
├── LICENSE                  # GNU GPL v3.0
├── README.md                # This file
├── .gitignore               # Excludes logs, backups, __pycache__, venvs
│
└── .github/
    └── ISSUE_TEMPLATE/
        ├── bug_report.md    # Structured bug report template
        └── feature_request.md
```

> **Note:** The `.ini` configuration files are machine-specific and are **not** committed to the repository. They stay on your LinuxCNC machine. The editor opens them from their original location on disk.

---

## Requirements

- **Operating System:** Ubuntu 20.04 / 22.04 / Debian 11 / 12 (or any Linux distro running LinuxCNC)
- **Python:** 3.8 or newer
- **PySide6:** 6.4.0 or newer

All other dependencies (`configparser`, `logging`, `shutil`, `pathlib`, `datetime`) are part of the Python standard library and require no installation.

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/ajitesh1020/linuxcnc-ini-editor.git
cd linuxcnc-ini-editor
```

### 2. Create a virtual environment (recommended)

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Run the application

```bash
python3 main.py
```

---

## Usage

### Opening an INI file

1. Launch the application: `python3 main.py`
2. Click **File → Open INI** or the **"Open INI"** toolbar button
3. Navigate to your LinuxCNC config directory (default: `~/linuxcnc/configs/<machine>/`)
4. Select your `.ini` file

### Editing values

- Navigate between tabs (**Axis Configuration**, **ATC Configuration**, **Trajectory**, **Filter**, **Display**, **RS274NGC**, **HAL**)
- Edit any field directly
- For text areas (HAL files, MDI commands, program extensions) — one entry per line

### Saving

- Click **"Update INI"** (bottom of window) to apply GUI changes and save
- Or click **File → Save INI** to save the current in-memory state without re-reading the GUI fields
- A backup is automatically created at `<original_file>.backup.YYYYMMDD_HHMMSS`

### Scale Calculator

1. Go to the **Axis Configuration** tab
2. Click **"Calc"** next to the **SCALE** field for the axis you want to correct
3. Enter the distance you commanded (e.g. `100 mm`)
4. Enter the distance the machine actually moved (measured with a dial indicator or ruler)
5. Click **Calculate** — the corrected scale is shown
6. Click **Apply New Scale** to populate the field

**Formula:** `New Scale = (Commanded Distance ÷ Measured Distance) × Current Scale`

---

## Configuration Tabs Explained

### Axis Configuration

Displays one panel per axis (`X`, `Y`, `Z`). Each panel edits both the `[AXIS_n]` and `[JOINT_n]` sections simultaneously, since LinuxCNC 2.8+ splits these.

| Parameter | Description |
|---|---|
| `MAX_VELOCITY` | Maximum axis speed (mm/s) |
| `MAX_ACCELERATION` | Maximum axis acceleration (mm/s²) |
| `MIN_LIMIT` / `MAX_LIMIT` | Soft travel limits (mm) |
| `STEPGEN_MAXACCEL` | Step generator acceleration headroom (typically 1.25× `MAX_ACCELERATION`) |
| `SCALE` | Steps per mm. Use the Scale Calculator to correct after measuring actual movement |
| `HOME_SEARCH_VEL` | Speed during initial home search (negative = move toward negative limit) |
| `HOME_LATCH_VEL` | Slow speed for final home latch (sign must match `HOME_SEARCH_VEL`) |
| `HOME_SEQUENCE` | Order in which axes home. Lower numbers home first; same number = simultaneous |

### ATC Configuration

Configures the automatic tool changer rack. Parameters map directly to the `[ATC]` section.

| Parameter | Description |
|---|---|
| `CHANGEX/Y/Z` | Machine coordinates for the manual tool change position |
| `NUMPOCKETS` | Total number of tool pockets in the rack |
| `DROPSPEEDRAPID/XY/Z` | Feed rates (mm/min) for rapid, XY traverse, and Z plunge during tool change |
| `FIRSTPOCKET_X/Y/Z` | Coordinates of pocket #1 (used as reference if individual coords not set) |
| `SAFE_X/Y/YY/Z` | Safe clearance positions used between moves |
| `DELTA_X/Y` | Spacing between pockets (used to auto-calculate positions if not set individually) |
| `TOOL1_X … TOOL9_Y` | Individual X/Y pocket coordinates (override calculated positions) |

### Trajectory

Controls the `[TRAJ]` section — coordinate system, units, and velocity limits at the trajectory planner level.

### Filter

Controls the `[FILTER]` section. The **Program Extensions** text area holds all `PROGRAM_EXTENSION` lines. Enter one per line. All entries are preserved exactly, including duplicates.

### Display

Controls the `[DISPLAY]` section: editor path, G-code program prefix directory, startup file, and optional PyVCP panel.

### RS274NGC

Controls the `[RS274NGC]` section: parameter file, startup G-code string, subroutine path, user M-code path.

### HAL

Controls the `[HAL]` and `[HALUI]` sections.

- **HAL Files** text area — one `HALFILE` entry per line, in load order
- **MDI Commands** text area — one `MDI_COMMAND` entry per line, in the order LinuxCNC assigns them to `halui.mdi-command-NN` pins

> ⚠️ **Order matters.** The position of each MDI command in the list determines its `halui.mdi-command-00`, `halui.mdi-command-01`, … pin number.

---

## How It Works Internally

### The Duplicate-Key Problem

Python's built-in `configparser` **does not support duplicate keys** in the same section. When an INI file contains:

```ini
[HALUI]
MDI_COMMAND = G28
MDI_COMMAND = G10 L20 P0 X0Y0
MDI_COMMAND = M61 Q0
```

`configparser` silently discards the first two and keeps only `M61 Q0`. Saving would then write `M61 Q0` for all three lines — corrupting the file.

### The Fix: `IniFileHandler`

A custom line-level parser (`IniFileHandler` in `gui.py`) reads the file into an **ordered list of line dictionaries**, one per line. Every line is kept — comments, blanks, and all duplicate key occurrences as separate entries.

Key methods:

| Method | Purpose |
|---|---|
| `read(filepath)` | Parse file; store every line as a dict with `type`, `section`, `key`, `value`, `text` |
| `get_all(section, key)` | Return all values for a repeated key, in file order |
| `set_all(section, key, values)` | Replace exactly the right number of lines in-place; add/remove lines as needed |
| `set(section, key, value)` | Update the last occurrence of a single-value key |
| `write(filepath)` | Write all stored line-dicts back verbatim — no reconstruction, no reformatting |

This means the saved file is a **surgical in-place update** — only the values you changed differ from the original. Every comment, blank line, `#HALFILE = ...` commented-out line, and section order is preserved.

---

## Known Limitations

- **Read-only sections:** `[EMC]`, `[KINS]`, `[EMCMOT]`, `[EMCIO]`, `[TASK]`, `[PYTHON]`, and `[ATC_PINS]` are not exposed in the GUI (they are preserved in the file unchanged). A future tab could expose these.
- **No validation against machine limits:** The editor does not cross-check that your `MAX_VELOCITY` is achievable given `BASE_PERIOD` and `SCALE`. That validation is LinuxCNC's job at startup.
- **Single file at a time:** Only one INI file can be open per session.
- **LinuxCNC must not be running:** Do not save an INI file while LinuxCNC is actively using it. Always save, then restart LinuxCNC.

---

## Contributing

Contributions are welcome. Please:

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Make your changes following the existing code style (PEP 8, descriptive names, logging at appropriate levels)
4. Test against a real or sample `.ini` file
5. Open a Pull Request with a clear description of what changed and why

For bugs, use the [bug report template](.github/ISSUE_TEMPLATE/bug_report.md).
For ideas, use the [feature request template](.github/ISSUE_TEMPLATE/feature_request.md).

---

## License

This project is licensed under the MIT License.
See LICENSE for the full text.

