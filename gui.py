# gui.py (fixed sections)
import os
import sys
import logging
import configparser
from pathlib import Path
from PySide6.QtWidgets import *
from PySide6.QtCore import *
from PySide6.QtGui import *
from scale_calculator import ScaleCalculatorDialog

import traceback
import shutil
from datetime import datetime

# Configure logging to file immediately
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('linuxcnc_editor_debug.log', mode='w'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
logger.info("="*50)
logger.info("Starting LinuxCNC Configuration Editor - DEBUG MODE")
logger.info("="*50)

class IniFileHandler:
    """
    Custom INI parser that correctly handles duplicate keys (e.g. multiple
    PROGRAM_EXTENSION, HALFILE, MDI_COMMAND lines) which configparser cannot
    represent because it only keeps the last value for a given key.

    Internal representation
    -----------------------
    self.raw : list of dicts, one per parsed line, in file order:
        {'type': 'section',  'text': '[FILTER]\\n',      'section': 'FILTER'}
        {'type': 'keyval',   'text': 'png = ...',         'section': 'FILTER',
         'key': 'PNG', 'raw_key': 'png', 'value': 'image-to-gcode'}
        {'type': 'blank',    'text': '\\n'}
        {'type': 'comment',  'text': '# comment\\n'}

    self.sections : OrderedDict  section_name -> list of keyval dicts
    """

    def __init__(self):
        self.raw = []          # ordered list of all line-dicts
        self.sections = {}     # section_name -> [keyval dicts] (references into self.raw)

    # ------------------------------------------------------------------
    # Reading
    # ------------------------------------------------------------------
    def read(self, filepath: str):
        """Parse the INI file preserving ALL lines including duplicates."""
        self.raw = []
        self.sections = {}
        current_section = None

        with open(filepath, 'r') as fh:
            for line in fh:
                stripped = line.strip()

                if stripped.startswith('[') and stripped.endswith(']'):
                    section_name = stripped[1:-1]
                    current_section = section_name
                    if section_name not in self.sections:
                        self.sections[section_name] = []
                    entry = {'type': 'section', 'text': line,
                             'section': section_name}
                    self.raw.append(entry)

                elif current_section is not None and '=' in stripped and not stripped.startswith('#'):
                    raw_key, _, value = stripped.partition('=')
                    raw_key = raw_key.rstrip()
                    value = value.strip()
                    upper_key = raw_key.upper()
                    entry = {
                        'type': 'keyval',
                        'text': line,
                        'section': current_section,
                        'key': upper_key,        # canonical upper-case key
                        'raw_key': raw_key,      # original case from file
                        'value': value,
                    }
                    self.raw.append(entry)
                    self.sections[current_section].append(entry)

                else:
                    entry = {
                        'type': 'blank' if not stripped else 'comment',
                        'text': line,
                        'section': current_section,
                    }
                    self.raw.append(entry)

        logger.debug(f"IniFileHandler.read: {len(self.raw)} lines, "
                     f"{len(self.sections)} sections")

    # ------------------------------------------------------------------
    # Querying
    # ------------------------------------------------------------------
    def get(self, section: str, key: str, fallback=None):
        """Return the LAST value for (section, key) – mirrors configparser behaviour."""
        upper_key = key.upper()
        for entry in reversed(self.sections.get(section, [])):
            if entry['key'] == upper_key:
                return entry['value']
        return fallback

    def get_all(self, section: str, key: str) -> list:
        """Return ALL values for (section, key) in file order."""
        upper_key = key.upper()
        return [e['value'] for e in self.sections.get(section, [])
                if e['key'] == upper_key]

    def get_section_items(self, section: str) -> list:
        """Return [(raw_key, value), ...] for every key in section, in order."""
        return [(e['raw_key'], e['value']) for e in self.sections.get(section, [])]

    def has_section(self, section: str) -> bool:
        return section in self.sections

    # ------------------------------------------------------------------
    # Modifying
    # ------------------------------------------------------------------
    def set(self, section: str, key: str, value: str):
        """
        Update the LAST occurrence of key in section.
        If key does not exist, append it.
        """
        upper_key = key.upper()
        target = None
        for entry in reversed(self.sections.get(section, [])):
            if entry['key'] == upper_key:
                target = entry
                break

        if target is not None:
            target['value'] = str(value)
            indent = target['text'][:len(target['text']) - len(target['text'].lstrip())]
            target['text'] = f"{indent}{target['raw_key']} = {value}\n"
        else:
            self._append_key(section, key, value)

    def set_all(self, section: str, key: str, values: list):
        """
        Replace ALL occurrences of key in section with the supplied list of values.
        Extra existing lines are removed; missing lines are appended.
        Preserves the position of the first existing occurrence.
        """
        upper_key = key.upper()
        sec_entries = self.sections.get(section, [])

        # Find indices of existing entries for this key (within sec_entries)
        existing_indices = [i for i, e in enumerate(sec_entries)
                            if e['key'] == upper_key]

        if not existing_indices and not values:
            return  # nothing to do

        if not existing_indices:
            # Key doesn't exist yet – just append all values
            for v in values:
                self._append_key(section, key, v)
            return

        # Determine raw_key from first existing entry to preserve original casing
        raw_key = sec_entries[existing_indices[0]]['raw_key']

        # Reuse as many existing slots as we have new values
        for slot, value in zip(existing_indices, values):
            entry = sec_entries[slot]
            entry['value'] = value
            indent = entry['text'][:len(entry['text']) - len(entry['text'].lstrip())]
            entry['text'] = f"{indent}{raw_key} = {value}\n"

        if len(values) > len(existing_indices):
            # Need to add more lines after the last existing one
            insert_after = sec_entries[existing_indices[-1]]
            insert_pos_raw = self.raw.index(insert_after) + 1
            for value in values[len(existing_indices):]:
                new_entry = {
                    'type': 'keyval',
                    'text': f"{raw_key} = {value}\n",
                    'section': section,
                    'key': upper_key,
                    'raw_key': raw_key,
                    'value': value,
                }
                self.raw.insert(insert_pos_raw, new_entry)
                sec_entries.insert(existing_indices[-1] + 1, new_entry)
                insert_pos_raw += 1
                existing_indices.append(existing_indices[-1] + 1)
        elif len(values) < len(existing_indices):
            # Need to remove surplus lines
            for idx in reversed(existing_indices[len(values):]):
                entry_to_remove = sec_entries[idx]
                self.raw.remove(entry_to_remove)
                sec_entries.remove(entry_to_remove)

    def _append_key(self, section: str, key: str, value: str):
        """Append a new key=value line at the end of section."""
        upper_key = key.upper()
        sec_entries = self.sections.get(section, [])

        new_entry = {
            'type': 'keyval',
            'text': f"{key} = {value}\n",
            'section': section,
            'key': upper_key,
            'raw_key': key,
            'value': value,
        }

        if sec_entries:
            # Insert into self.raw right after the last entry of this section
            last_entry = sec_entries[-1]
            insert_pos = self.raw.index(last_entry) + 1
            self.raw.insert(insert_pos, new_entry)
        else:
            self.raw.append(new_entry)

        sec_entries.append(new_entry)
        self.sections.setdefault(section, sec_entries)

    # ------------------------------------------------------------------
    # Writing
    # ------------------------------------------------------------------
    def write(self, filepath: str):
        """Write the (modified) file back, preserving all comments and blank lines."""
        with open(filepath, 'w') as fh:
            for entry in self.raw:
                fh.write(entry['text'])
        logger.debug(f"IniFileHandler.write: wrote {len(self.raw)} lines to {filepath}")


class AxisGroupBox(QGroupBox):
    def __init__(self, axis_name, parent=None):
        super().__init__(f"Axis {axis_name}", parent)
        self.axis_name = axis_name
        self.params = {}
        self.setup_ui()
        
    def setup_ui(self):
        layout = QGridLayout()
        layout.setColumnStretch(0, 0)   # label column – fixed width
        layout.setColumnStretch(1, 1)   # input column – stretches with window
        layout.setColumnStretch(2, 0)   # optional button column – fixed

        params = [
            'MAX_VELOCITY', 'MAX_ACCELERATION', 'MIN_LIMIT', 'MAX_LIMIT',
            'STEPGEN_MAXACCEL', 'SCALE', 'HOME_SEARCH_VEL', 'HOME_LATCH_VEL', 'HOME_SEQUENCE'
        ]

        row = 0
        for param in params:
            label = QLabel(param)
            label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

            edit = QLineEdit()
            edit.setObjectName(param)
            edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            self.params[param] = edit

            layout.addWidget(label, row, 0)
            layout.addWidget(edit, row, 1)

            if param == 'SCALE':
                calc_btn = QPushButton("Calc")
                calc_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
                calc_btn.clicked.connect(self.open_scale_calculator)
                layout.addWidget(calc_btn, row, 2)

            row += 1

        self.setLayout(layout)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
    
    def open_scale_calculator(self):
        try:
            current_scale = float(self.params['SCALE'].text() or 0)
            dialog = ScaleCalculatorDialog(self.axis_name, current_scale, self)
            if dialog.exec():
                new_scale = dialog.get_new_scale()
                if new_scale:
                    self.params['SCALE'].setText(f"{new_scale:.6f}")
        except ValueError:
            QMessageBox.warning(self, "Warning", "Invalid current scale value")
    
    def set_values(self, values):
        for param, edit in self.params.items():
            if param in values:
                edit.setText(str(values[param]))
            else:
                edit.setText("")
    
    def get_values(self):
        values = {}
        for param, edit in self.params.items():
            text = edit.text().strip()
            if text:
                try:
                    if param == 'HOME_SEQUENCE':
                        values[param] = int(text)
                    elif '.' in text or 'e' in text.lower():
                        values[param] = float(text)
                    else:
                        values[param] = int(text)
                except ValueError:
                    values[param] = text
        return values

class ToolPositionGroupBox(QGroupBox):
    def __init__(self, tool_num, parent=None):
        super().__init__(f"Tool {tool_num}", parent)
        self.tool_num = tool_num
        self.setup_ui()
        
    def setup_ui(self):
        layout = QGridLayout()
        
        # X position
        layout.addWidget(QLabel("X:"), 0, 0)
        self.x_edit = QLineEdit()
        self.x_edit.setObjectName(f"TOOL{self.tool_num}_X")
        layout.addWidget(self.x_edit, 0, 1)
        
        # Y position
        layout.addWidget(QLabel("Y:"), 1, 0)
        self.y_edit = QLineEdit()
        self.y_edit.setObjectName(f"TOOL{self.tool_num}_Y")
        layout.addWidget(self.y_edit, 1, 1)
        
        self.setLayout(layout)
    
    def set_values(self, x_val, y_val):
        self.x_edit.setText(str(x_val) if x_val else "")
        self.y_edit.setText(str(y_val) if y_val else "")
    
    def get_values(self):
        return {
            f"TOOL{self.tool_num}_X": self.x_edit.text().strip(),
            f"TOOL{self.tool_num}_Y": self.y_edit.text().strip()
        }

# Modified ProgramExtensionWidget - properly handles multiple lines
class ProgramExtensionWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
        
    def setup_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Label
        layout.addWidget(QLabel("Program Extensions (one per line):"))
        
        # Text edit for multiple extensions
        self.extensions_text = QTextEdit()
        self.extensions_text.setPlaceholderText(
            ".png,.gif,.jpg Greyscale Depth Image\n"
            ".py Python Script\n"
            ".nc,.tap G-Code File\n"
            ".NC,.tap G-Code File"
        )
        self.extensions_text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self.extensions_text)
        
        self.setLayout(layout)
    
    def set_extensions(self, extensions):
        """Set extensions from list to text area - preserves original values"""
        if extensions:
            text = "\n".join(extensions)
            self.extensions_text.setPlainText(text)
            logger.debug(f"Set {len(extensions)} extensions in text area: {extensions}")
        else:
            self.extensions_text.clear()
    
    def get_extensions(self):
        """Get extensions from text area as list - preserves order and duplicates"""
        text = self.extensions_text.toPlainText()
        if text.strip():
            # Split by lines and keep empty lines? No, filter out empty lines
            extensions = [line.rstrip() for line in text.split('\n') if line.strip()]
            logger.debug(f"Getting {len(extensions)} extensions from text area: {extensions}")
            return extensions
        return []
    
class PathBrowseWidget(QWidget):
    path_changed = Signal(str)
    
    def __init__(self, label_text, browse_type="file", parent=None):
        super().__init__(parent)
        self.browse_type = browse_type
        self.setup_ui(label_text)
        
    def setup_ui(self, label_text):
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        self.label = QLabel(label_text)
        self.label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        layout.addWidget(self.label, 0)

        self.path_edit = QLineEdit()
        self.path_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.path_edit.textChanged.connect(self.path_changed.emit)
        layout.addWidget(self.path_edit, 1)

        self.browse_btn = QPushButton("Browse")
        self.browse_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.browse_btn.clicked.connect(self.browse)
        layout.addWidget(self.browse_btn, 0)

        self.setLayout(layout)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    
    def browse(self):
        if self.browse_type == "file":
            path, _ = QFileDialog.getOpenFileName(self, f"Select {self.label.text()}", 
                                                 self.path_edit.text() or str(Path.home()))
        else:
            path = QFileDialog.getExistingDirectory(self, f"Select {self.label.text()}", 
                                                   self.path_edit.text() or str(Path.home()))
        
        if path:
            self.path_edit.setText(path)
    
    def set_path(self, path):
        self.path_edit.setText(path)
    
    def get_path(self):
        return self.path_edit.text().strip()

class HALFileRowWidget(QWidget):
    def __init__(self, file_value="", parent=None):
        super().__init__(parent)
        self.setup_ui(file_value)
        
    def setup_ui(self, file_value):
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.file_edit = QLineEdit()
        self.file_edit.setText(file_value)
        self.file_edit.setPlaceholderText("filename.hal")
        layout.addWidget(self.file_edit)
        
        browse_btn = QPushButton("Browse")
        browse_btn.clicked.connect(self.browse_file)
        layout.addWidget(browse_btn)
        
        remove_btn = QPushButton("Remove")
        remove_btn.clicked.connect(self.remove_self)
        layout.addWidget(remove_btn)
        
        self.setLayout(layout)
    
    def browse_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select HAL File", "", "HAL Files (*.hal);;All Files (*.*)")
        if path:
            self.file_edit.setText(os.path.basename(path))
    
    def remove_self(self):
        self.deleteLater()
    
    def get_value(self):
        return self.file_edit.text().strip()

class HALUICommandRowWidget(QWidget):
    def __init__(self, command_value="", parent=None):
        super().__init__(parent)
        self.setup_ui(command_value)
        
    def setup_ui(self, command_value):
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.cmd_edit = QLineEdit()
        self.cmd_edit.setText(command_value)
        self.cmd_edit.setPlaceholderText("MDI Command")
        layout.addWidget(self.cmd_edit)
        
        remove_btn = QPushButton("Remove")
        remove_btn.clicked.connect(self.remove_self)
        layout.addWidget(remove_btn)
        
        self.setLayout(layout)
    
    def remove_self(self):
        self.deleteLater()
    
    def get_value(self):
        return self.cmd_edit.text().strip()

class LinuxCNCConfigEditor(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config = None
        self.config_file = None
        self.ini_handler = IniFileHandler()   # custom duplicate-key-aware parser
        self.axis_groups = {}
        self.tool_groups = {}
        self.logger = logging.getLogger(__name__)
        self.setup_ui()
        self.setup_menu()
        
# Add author information to the main window setup
    def setup_ui(self):
        self.setWindowTitle("LinuxCNC Configuration Editor")
        self.setGeometry(100, 100, 1200, 800)
        
        # Set window icon and author info
        self.author_info = QLabel()
        self.author_info.setText(
            "© 2025 Ajitesh Kannoja | Company: CNCToolTech | "
            "Version 1.0.0 | Licensed under GPL v3.0"
        )
        self.author_info.setAlignment(Qt.AlignCenter)
        self.author_info.setStyleSheet("color: gray; font-size: 9pt; padding: 2px;")
        
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        
        # Add author info at top
        main_layout.addWidget(self.author_info)
        
        # Top toolbar
        toolbar = QToolBar()
        self.addToolBar(toolbar)
        
        open_action = QAction("Open INI", self)
        open_action.triggered.connect(self.open_ini_file)
        toolbar.addAction(open_action)
        
        save_action = QAction("Save INI", self)
        save_action.triggered.connect(self.save_ini_file)
        toolbar.addAction(save_action)
        
        # Tab widget
        self.tab_widget = QTabWidget()
        self.tab_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        main_layout.addWidget(self.tab_widget, 1)   # stretch=1 so tabs fill remaining height
        
        # Create tabs
        self.create_axis_tab()
        self.create_atc_tab()
        self.create_traj_tab()
        self.create_filter_tab()
        self.create_display_tab()
        self.create_rs274ngc_tab()
        self.create_hal_tab()
        
        # Bottom buttons
        button_layout = QHBoxLayout()
        
        self.update_btn = QPushButton("Update INI")
        self.update_btn.clicked.connect(self.update_ini)
        self.update_btn.setEnabled(False)
        button_layout.addWidget(self.update_btn)
        
        self.exit_btn = QPushButton("Exit")
        self.exit_btn.clicked.connect(self.close)
        button_layout.addWidget(self.exit_btn)
        
        # Logging toggle
        self.logging_checkbox = QCheckBox("Enable Logging")
        self.logging_checkbox.setChecked(True)
        self.logging_checkbox.stateChanged.connect(self.toggle_logging)
        button_layout.addWidget(self.logging_checkbox)
        
        # Add GPL notice
        gpl_label = QLabel("This program is free software: you can redistribute it and/or modify "
                          "it under the terms of the GNU General Public License as published by "
                          "the Free Software Foundation, either version 3 of the License.")
        gpl_label.setWordWrap(True)
        gpl_label.setStyleSheet("color: gray; font-size: 8pt;")
        button_layout.addWidget(gpl_label)
        
        button_layout.addStretch()
        main_layout.addLayout(button_layout)
        
        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")

    def setup_menu(self):
        menubar = self.menuBar()
        file_menu = menubar.addMenu("File")
        
        open_action = QAction("Open INI", self)
        open_action.triggered.connect(self.open_ini_file)
        file_menu.addAction(open_action)
        
        save_action = QAction("Save INI", self)
        save_action.triggered.connect(self.save_ini_file)
        file_menu.addAction(save_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
    
    def create_axis_tab(self):
        axis_tab = QWidget()
        layout = QHBoxLayout(axis_tab)
        layout.setContentsMargins(4, 4, 4, 4)

        # Scroll area for axes – widgetResizable lets axes fill available space
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        axes_widget = QWidget()
        axes_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.axes_layout = QHBoxLayout(axes_widget)
        self.axes_layout.setSpacing(8)
        scroll.setWidget(axes_widget)
        layout.addWidget(scroll)

        self.tab_widget.addTab(axis_tab, "Axis Configuration")
    
    def create_atc_tab(self):
        atc_tab = QWidget()
        layout = QVBoxLayout(atc_tab)
        layout.setContentsMargins(4, 4, 4, 4)

        # ATC Parameters
        atc_group = QGroupBox("ATC Parameters")
        atc_layout = QGridLayout()
        atc_layout.setColumnStretch(0, 0)   # label column – fixed
        atc_layout.setColumnStretch(1, 1)   # input column – stretches
        
        self.atc_params = {}
        atc_params_list = [
            ('CHANGEX', 'Change X:'),
            ('CHANGEY', 'Change Y:'),
            ('CHANGEZ', 'Change Z:'),
            ('NUMPOCKETS', 'Number of Pockets:'),
            ('DROPSPEEDRAPID', 'Drop Speed Rapid:'),
            ('DROPSPEEDXY', 'Drop Speed XY:'),
            ('DROPSPEEDZ', 'Drop Speed Z:'),
            ('FIRSTPOCKET_X', 'First Pocket X:'),
            ('FIRSTPOCKET_Y', 'First Pocket Y:'),
            ('FIRSTPOCKET_Z', 'First Pocket Z:'),
            ('SAFE_X', 'Safe X:'),
            ('SAFE_Y', 'Safe Y:'),
            ('SAFE_YY', 'Safe YY:'),
            ('SAFE_Z', 'Safe Z:'),
            ('DELTA_X', 'Delta X:'),
            ('DELTA_Y', 'Delta Y:')
        ]
        
        row = 0
        for param, label in atc_params_list:
            atc_layout.addWidget(QLabel(label), row, 0)
            edit = QLineEdit()
            edit.setObjectName(f"ATC_{param}")
            edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            self.atc_params[param] = edit
            atc_layout.addWidget(edit, row, 1)
            row += 1
        
        atc_group.setLayout(atc_layout)
        atc_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        layout.addWidget(atc_group, 0)   # fixed vertical share

        # Tool Positions
        tools_group = QGroupBox("Tool Positions")
        tools_layout = QVBoxLayout()

        # Scroll area for tools
        tools_scroll = QScrollArea()
        tools_scroll.setWidgetResizable(True)
        tools_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        tools_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        tools_scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        tools_widget = QWidget()
        tools_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.tools_layout = QHBoxLayout(tools_widget)
        self.tools_layout.setSpacing(8)
        tools_scroll.setWidget(tools_widget)
        tools_layout.addWidget(tools_scroll)

        tools_group.setLayout(tools_layout)
        tools_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(tools_group, 1)   # takes remaining vertical space
        
        self.tab_widget.addTab(atc_tab, "ATC Configuration")
    
    def create_traj_tab(self):
        traj_tab = QWidget()
        layout = QVBoxLayout(traj_tab)
        layout.setContentsMargins(4, 4, 4, 4)

        # TRAJ parameters
        traj_group = QGroupBox("Trajectory Parameters")
        traj_layout = QGridLayout()
        traj_layout.setColumnStretch(0, 0)
        traj_layout.setColumnStretch(1, 1)
        
        self.traj_params = {}
        traj_params_list = [
            ('COORDINATES', 'Coordinates:'),
            ('LINEAR_UNITS', 'Linear Units:'),
            ('ANGULAR_UNITS', 'Angular Units:'),
            ('DEFAULT_LINEAR_VELOCITY', 'Default Linear Velocity:'),
            ('MAX_LINEAR_VELOCITY', 'Max Linear Velocity:')
        ]
        
        row = 0
        for param, label in traj_params_list:
            traj_layout.addWidget(QLabel(label), row, 0)
            edit = QLineEdit()
            edit.setObjectName(f"TRAJ_{param}")
            edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            self.traj_params[param] = edit
            traj_layout.addWidget(edit, row, 1)
            row += 1
        
        # NO_FORCE_HOMING checkbox
        self.no_force_homing_cb = QCheckBox("NO_FORCE_HOMING (Bypass homing)")
        traj_layout.addWidget(self.no_force_homing_cb, row, 0, 1, 2)
        
        traj_group.setLayout(traj_layout)
        traj_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        layout.addWidget(traj_group)
        layout.addStretch(1)   # push group to top, free space below

        self.tab_widget.addTab(traj_tab, "Trajectory")
    
    def create_filter_tab(self):
        filter_tab = QWidget()
        layout = QVBoxLayout(filter_tab)
        
        # Filter parameters
        filter_group = QGroupBox("Filter Configuration")
        filter_layout = QVBoxLayout()
        
        # Program extensions
        self.program_extensions = ProgramExtensionWidget()
        filter_layout.addWidget(self.program_extensions)
        
        filter_group.setLayout(filter_layout)
        filter_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(filter_group)

        self.tab_widget.addTab(filter_tab, "Filter")
    
    def create_display_tab(self):
        display_tab = QWidget()
        layout = QVBoxLayout(display_tab)
        layout.setContentsMargins(4, 4, 4, 4)

        display_group = QGroupBox("Display Configuration")
        display_layout = QGridLayout()
        display_layout.setColumnStretch(0, 0)
        display_layout.setColumnStretch(1, 1)
        
        self.display_params = {}
        
        # EDITOR
        row = 0
        self.display_params['EDITOR'] = PathBrowseWidget("EDITOR:", "file")
        display_layout.addWidget(self.display_params['EDITOR'], row, 0, 1, 2)
        
        # PROGRAM_PREFIX
        row += 1
        self.display_params['PROGRAM_PREFIX'] = PathBrowseWidget("PROGRAM_PREFIX:", "directory")
        display_layout.addWidget(self.display_params['PROGRAM_PREFIX'], row, 0, 1, 2)
        
        # OPEN_FILE
        row += 1
        self.display_params['OPEN_FILE'] = PathBrowseWidget("OPEN_FILE:", "file")
        display_layout.addWidget(self.display_params['OPEN_FILE'], row, 0, 1, 2)
        
        # PYVCP Checkbox and path
        row += 1
        pyvcp_widget = QWidget()
        pyvcp_layout = QHBoxLayout(pyvcp_widget)
        pyvcp_layout.setContentsMargins(0, 0, 0, 0)
        
        self.pyvcp_enabled = QCheckBox("Enable PYVCP")
        self.pyvcp_enabled.stateChanged.connect(self.toggle_pyvcp)
        pyvcp_layout.addWidget(self.pyvcp_enabled)
        
        self.pyvcp_path = QLineEdit()
        self.pyvcp_path.setPlaceholderText("custompanel.xml")
        self.pyvcp_path.setEnabled(False)
        self.pyvcp_path.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        pyvcp_layout.addWidget(self.pyvcp_path, 1)
        
        pyvcp_browse = QPushButton("Browse")
        pyvcp_browse.clicked.connect(self.browse_pyvcp)
        pyvcp_browse.setEnabled(False)
        self.pyvcp_browse_btn = pyvcp_browse
        pyvcp_layout.addWidget(pyvcp_browse)
        
        display_layout.addWidget(pyvcp_widget, row, 0, 1, 2)
        
        display_group.setLayout(display_layout)
        display_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        layout.addWidget(display_group)
        layout.addStretch(1)

        self.tab_widget.addTab(display_tab, "Display")
    
    def create_rs274ngc_tab(self):
        rs274_tab = QWidget()
        layout = QVBoxLayout(rs274_tab)
        layout.setContentsMargins(4, 4, 4, 4)

        rs274_group = QGroupBox("RS274NGC Configuration")
        rs274_layout = QGridLayout()
        rs274_layout.setColumnStretch(0, 0)
        rs274_layout.setColumnStretch(1, 1)
        
        self.rs274_params = {}
        
        # PARAMETER_FILE
        row = 0
        self.rs274_params['PARAMETER_FILE'] = PathBrowseWidget("PARAMETER_FILE:", "file")
        rs274_layout.addWidget(self.rs274_params['PARAMETER_FILE'], row, 0, 1, 2)
        
        # RS274NGC_STARTUP_CODE
        row += 1
        rs274_layout.addWidget(QLabel("RS274NGC_STARTUP_CODE:"), row, 0)
        self.startup_code = QLineEdit()
        self.startup_code.setObjectName("RS274NGC_STARTUP_CODE")
        self.startup_code.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        rs274_layout.addWidget(self.startup_code, row, 1)
        
        # SUBROUTINE_PATH
        row += 1
        self.rs274_params['SUBROUTINE_PATH'] = PathBrowseWidget("SUBROUTINE_PATH:", "directory")
        rs274_layout.addWidget(self.rs274_params['SUBROUTINE_PATH'], row, 0, 1, 2)
        
        # USER_M_PATH
        row += 1
        self.rs274_params['USER_M_PATH'] = PathBrowseWidget("USER_M_PATH:", "directory")
        rs274_layout.addWidget(self.rs274_params['USER_M_PATH'], row, 0, 1, 2)
        
        rs274_group.setLayout(rs274_layout)
        rs274_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        layout.addWidget(rs274_group)
        layout.addStretch(1)

        self.tab_widget.addTab(rs274_tab, "RS274NGC")
    
# Modified HAL tab creation - simplified version without add/remove buttons
    def create_hal_tab(self):
        hal_tab = QWidget()
        layout = QVBoxLayout(hal_tab)
        layout.setContentsMargins(4, 4, 4, 4)

        # HAL Files
        hal_group = QGroupBox("HAL Configuration")
        hal_layout = QVBoxLayout()

        hal_layout.addWidget(QLabel("HAL Files (one per line):"))

        self.hal_files_text = QTextEdit()
        self.hal_files_text.setPlaceholderText("6050_iCam.hal\ncustom.hal\npostgui_call_list.hal\nshutdown.hal\natc.hal")
        self.hal_files_text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        hal_layout.addWidget(self.hal_files_text)

        hal_group.setLayout(hal_layout)
        hal_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(hal_group, 1)   # equal vertical stretch

        # HALUI MDI Commands
        halui_group = QGroupBox("HALUI MDI Commands")
        halui_layout = QVBoxLayout()

        halui_layout.addWidget(QLabel("MDI Commands (one per line):"))

        self.halui_commands_text = QTextEdit()
        self.halui_commands_text.setPlaceholderText("G28\nG10 L20 P0 X0Y0\nG28.1\nM03 S#<_hal[pyvcp.peck-s]>\nO<Pressurepad_ON> CALL\nO<Pressurepad_OFF> CALL\nM61 Q0")
        self.halui_commands_text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        halui_layout.addWidget(self.halui_commands_text)

        halui_group.setLayout(halui_layout)
        halui_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(halui_group, 1)   # equal vertical stretch

        self.tab_widget.addTab(hal_tab, "HAL")

    def add_hal_file_row(self, file_value=""):
        row = HALFileRowWidget(file_value)
        self.hal_files_layout.addWidget(row)
    
    def add_halui_command_row(self, command_value=""):
        row = HALUICommandRowWidget(command_value)
        self.halui_layout.addWidget(row)
    
    def toggle_pyvcp(self, state):
        enabled = state == Qt.Checked
        self.pyvcp_path.setEnabled(enabled)
        self.pyvcp_browse_btn.setEnabled(enabled)
        if not enabled:
            self.pyvcp_path.clear()
    
    def browse_pyvcp(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select PYVCP XML File", 
                                              "", "XML Files (*.xml);;All Files (*.*)")
        if path:
            self.pyvcp_path.setText(os.path.basename(path))
    
    def open_ini_file(self):
        # Default LinuxCNC config path
        HOME_DIR = os.path.expanduser("~")
        default_path = os.path.join(HOME_DIR, "linuxcnc", "configs")
        print(default_path)
        if not os.path.exists(default_path):
            default_path = str(Path.home())
        
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open LinuxCNC INI File", default_path, "INI Files (*.ini);;All Files (*.*)"
        )
        
        if file_path:
            logger.debug(f"Selected file: {file_path}")
            self.check_file_permissions(file_path)
            
            self.config_file = file_path
            self.load_ini_file(file_path)
            self.update_btn.setEnabled(True)
            self.status_bar.showMessage(f"Loaded: {file_path}")    
            
    def load_ini_file(self, file_path):
        try:
            # Primary parser: custom handler that preserves duplicate keys
            self.ini_handler = IniFileHandler()
            self.ini_handler.read(file_path)

            # Secondary parser: configparser for sections/keys that are unique
            # (axis, ATC, TRAJ, DISPLAY, RS274NGC).  strict=False so it won't
            # raise on duplicates, but we do NOT rely on it for multi-value keys.
            self.config = configparser.ConfigParser(
                strict=False,  # Allow duplicate keys
                allow_no_value=True
            )
            self.config.optionxform = str  # Preserve case
            self.config.read(file_path)
            
            # Clear existing axis groups
            self.clear_axis_groups()
            
            # Load axis configurations
            self.load_axis_configs()
            
            # Load ATC configuration
            self.load_atc_config()
            
            # Load TRAJ configuration
            self.load_traj_config()
            
            # Load FILTER configuration - handle duplicates properly
            self.load_filter_config()
            
            # Load DISPLAY configuration
            self.load_display_config()
            
            # Load RS274NGC configuration
            self.load_rs274ngc_config()
            
            # Load HAL configuration
            self.load_hal_config()
            
            self.logger.info(f"Successfully loaded configuration from {file_path}")
            
        except Exception as e:
            self.logger.error(f"Error loading INI file: {e}")
            QMessageBox.critical(self, "Error", f"Failed to load INI file: {str(e)}")
    
    def clear_axis_groups(self):
        # Clear existing axis groups
        while self.axes_layout.count():
            item = self.axes_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.axis_groups = {}
    
    def load_axis_configs(self):
        axis_index = 0
        # Find all axis sections
        for section in self.config.sections():
            if section.startswith('AXIS_'):
                axis_name = section.replace('AXIS_', '')
                
                # Create axis group
                axis_group = AxisGroupBox(axis_name)
                
                # Load values from JOINT_ section
                joint_section = f'JOINT_{axis_index}'
                values = {}
                
                # Try to load from JOINT section first
                if joint_section in self.config:
                    for param in axis_group.params.keys():
                        if param in self.config[joint_section]:
                            values[param] = self.config[joint_section][param]
                
                # Override with AXIS section values if they exist
                if section in self.config:
                    for param in axis_group.params.keys():
                        if param in self.config[section]:
                            values[param] = self.config[section][param]
                
                axis_group.set_values(values)
                
                self.axes_layout.addWidget(axis_group, stretch=1)
                self.axis_groups[axis_name] = axis_group
                axis_index += 1
    
    def load_atc_config(self):
        if 'ATC' in self.config:
            # Load ATC parameters
            for param, edit in self.atc_params.items():
                if param in self.config['ATC']:
                    edit.setText(self.config['ATC'][param])
        
        # Clear existing tool groups
        self.clear_tool_groups()
        
        # Load TOOL positions from ATC section
        if 'ATC' in self.config:
            tool_data = {}
            for key in self.config['ATC']:
                if key.startswith('TOOL') and ('_X' in key or '_Y' in key):
                    tool_num = key.split('_')[0].replace('TOOL', '')
                    if tool_num not in tool_data:
                        tool_data[tool_num] = {}
                    
                    if '_X' in key:
                        tool_data[tool_num]['x'] = self.config['ATC'][key]
                    elif '_Y' in key:
                        tool_data[tool_num]['y'] = self.config['ATC'][key]
            
            # Sort tool numbers and create groups
            for tool_num in sorted(tool_data.keys(), key=int):
                tool_group = ToolPositionGroupBox(tool_num)
                tool_group.set_values(
                    tool_data[tool_num].get('x', ''),
                    tool_data[tool_num].get('y', '')
                )
                self.tools_layout.addWidget(tool_group)
                self.tool_groups[tool_num] = tool_group
    
    def clear_tool_groups(self):
        while self.tools_layout.count():
            item = self.tools_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.tool_groups = {}
    
    def load_traj_config(self):
        if 'TRAJ' in self.config:
            for param, edit in self.traj_params.items():
                if param in self.config['TRAJ']:
                    edit.setText(self.config['TRAJ'][param])
            
            # Load NO_FORCE_HOMING
            if 'NO_FORCE_HOMING' in self.config['TRAJ']:
                self.no_force_homing_cb.setChecked(self.config['TRAJ']['NO_FORCE_HOMING'] == '1')
            else:
                self.no_force_homing_cb.setChecked(False)
    
# Modified load_filter_config method - preserves ALL original values
    def load_filter_config(self):
        """Load FILTER configuration preserving all PROGRAM_EXTENSION values."""
        logger.debug("Loading FILTER configuration")

        if not self.ini_handler.has_section('FILTER'):
            return

        # Collect ALL PROGRAM_EXTENSION values in order via our custom handler
        extensions = self.ini_handler.get_all('FILTER', 'PROGRAM_EXTENSION')
        logger.debug(f"Found {len(extensions)} PROGRAM_EXTENSION entries: {extensions}")

        self.program_extensions.set_extensions(extensions)

    def load_display_config(self):
        if 'DISPLAY' in self.config:
            # Load EDITOR
            if 'EDITOR' in self.config['DISPLAY']:
                self.display_params['EDITOR'].set_path(self.config['DISPLAY']['EDITOR'])
            
            # Load PROGRAM_PREFIX
            if 'PROGRAM_PREFIX' in self.config['DISPLAY']:
                self.display_params['PROGRAM_PREFIX'].set_path(self.config['DISPLAY']['PROGRAM_PREFIX'])
            
            # Load OPEN_FILE
            if 'OPEN_FILE' in self.config['DISPLAY']:
                self.display_params['OPEN_FILE'].set_path(self.config['DISPLAY']['OPEN_FILE'])
            
            # Load PYVCP
            if 'PYVCP' in self.config['DISPLAY']:
                self.pyvcp_enabled.setChecked(True)
                self.pyvcp_path.setText(self.config['DISPLAY']['PYVCP'])
            else:
                self.pyvcp_enabled.setChecked(False)
    
    def load_rs274ngc_config(self):
        if 'RS274NGC' in self.config:
            # Load PARAMETER_FILE
            if 'PARAMETER_FILE' in self.config['RS274NGC']:
                self.rs274_params['PARAMETER_FILE'].set_path(self.config['RS274NGC']['PARAMETER_FILE'])
            
            # Load STARTUP_CODE
            if 'RS274NGC_STARTUP_CODE' in self.config['RS274NGC']:
                self.startup_code.setText(self.config['RS274NGC']['RS274NGC_STARTUP_CODE'])
            
            # Load SUBROUTINE_PATH
            if 'SUBROUTINE_PATH' in self.config['RS274NGC']:
                self.rs274_params['SUBROUTINE_PATH'].set_path(self.config['RS274NGC']['SUBROUTINE_PATH'])
            
            # Load USER_M_PATH
            if 'USER_M_PATH' in self.config['RS274NGC']:
                self.rs274_params['USER_M_PATH'].set_path(self.config['RS274NGC']['USER_M_PATH'])
    
# Modified load_hal_config method - preserves ALL HALFILE and MDI_COMMAND values
    def load_hal_config(self):
        """Load HAL configuration into text areas preserving all values."""
        logger.debug("Loading HAL configuration")

        # All HALFILE entries in file order
        hal_files = self.ini_handler.get_all('HAL', 'HALFILE')
        logger.debug(f"Found {len(hal_files)} HALFILE entries: {hal_files}")
        self.hal_files_text.setPlainText("\n".join(hal_files))

        # All MDI_COMMAND entries in file order
        commands = self.ini_handler.get_all('HALUI', 'MDI_COMMAND')
        logger.debug(f"Found {len(commands)} MDI_COMMAND entries: {commands}")
        self.halui_commands_text.setPlainText("\n".join(commands))

    def clear_hal_files(self):
        while self.hal_files_layout.count():
            item = self.hal_files_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
    
    def clear_halui_commands(self):
        while self.halui_layout.count():
            item = self.halui_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
    
    def update_ini(self):
        """Update the configuration with GUI values and save"""
        logger.debug("="*50)
        logger.debug("update_ini: STARTED")
        
        if not self.config or not self.config_file:
            logger.warning("update_ini: No INI file loaded")
            QMessageBox.warning(self, "Warning", "No INI file loaded")
            return
        
        try:
            # Update all configurations
            logger.debug("Updating axis configurations...")
            self.update_axis_configs()
            
            logger.debug("Updating ATC configurations...")
            self.update_atc_config()
            
            logger.debug("Updating TRAJ configurations...")
            self.update_traj_config()
            
            logger.debug("Updating FILTER configurations...")
            self.update_filter_config()
            
            logger.debug("Updating DISPLAY configurations...")
            self.update_display_config()
            
            logger.debug("Updating RS274NGC configurations...")
            self.update_rs274ngc_config()
            
            logger.debug("Updating HAL configurations...")
            self.update_hal_config()
            
            logger.debug("All configurations updated in memory")
            
            # Now save to file
            logger.debug("Calling save_ini_file...")
            self.save_ini_file()
            
            logger.debug("update_ini: COMPLETED SUCCESSFULLY")
            logger.debug("="*50)
            
        except Exception as e:
            logger.error(f"update_ini: ERROR: {e}")
            logger.error(traceback.format_exc())
            logger.debug("="*50)
            QMessageBox.critical(self, "Error", f"Failed to update INI file: {str(e)}")

    def update_axis_configs(self):
        axis_index = 0
        for axis_name, axis_group in self.axis_groups.items():
            values = axis_group.get_values()

            # Update AXIS_ section (configparser + ini_handler)
            axis_section = f'AXIS_{axis_name}'
            if axis_section not in self.config:
                self.config.add_section(axis_section)

            for param, value in values.items():
                if param in ['MAX_VELOCITY', 'MAX_ACCELERATION', 'MIN_LIMIT', 'MAX_LIMIT']:
                    self.config[axis_section][param] = str(value)
                    self.ini_handler.set(axis_section, param, str(value))

            # Update JOINT_ section (configparser + ini_handler)
            joint_section = f'JOINT_{axis_index}'
            if joint_section not in self.config:
                self.config.add_section(joint_section)

            for param, value in values.items():
                self.config[joint_section][param] = str(value)
                self.ini_handler.set(joint_section, param, str(value))

            axis_index += 1
    
    def update_atc_config(self):
        if 'ATC' not in self.config:
            self.config.add_section('ATC')
        
        # Update ATC parameters
        for param, edit in self.atc_params.items():
            text = edit.text().strip()
            if text:
                self.config['ATC'][param] = text
            elif param in self.config['ATC']:
                del self.config['ATC'][param]
        
        # Update tool positions
        # First remove existing tool entries
        keys_to_remove = []
        for key in self.config['ATC']:
            if key.startswith('TOOL') and ('_X' in key or '_Y' in key):
                keys_to_remove.append(key)
        
        for key in keys_to_remove:
            del self.config['ATC'][key]
        
        # Add updated tool positions
        for tool_num, tool_group in self.tool_groups.items():
            values = tool_group.get_values()
            for key, value in values.items():
                if value:
                    self.config['ATC'][key] = value
    
    def update_traj_config(self):
        if 'TRAJ' not in self.config:
            self.config.add_section('TRAJ')
        
        # Update TRAJ parameters
        for param, edit in self.traj_params.items():
            text = edit.text().strip()
            if text:
                self.config['TRAJ'][param] = text
        
        # Update NO_FORCE_HOMING
        self.config['TRAJ']['NO_FORCE_HOMING'] = '1' if self.no_force_homing_cb.isChecked() else '0'
    
# Modified update_filter_config method - uses IniFileHandler for correct multi-value handling
    def update_filter_config(self):
        """Update FILTER section – replaces PROGRAM_EXTENSION lines with text-area values."""
        logger.debug("Updating FILTER configuration")

        extensions = self.program_extensions.get_extensions()
        logger.debug(f"Text area contains {len(extensions)} extensions: {extensions}")

        # set_all replaces exactly the right number of PROGRAM_EXTENSION lines in place
        self.ini_handler.set_all('FILTER', 'PROGRAM_EXTENSION', extensions)
        logger.debug("FILTER PROGRAM_EXTENSION updated via IniFileHandler")

    def update_display_config(self):
        if 'DISPLAY' not in self.config:
            self.config.add_section('DISPLAY')
        
        # Update EDITOR
        editor_path = self.display_params['EDITOR'].get_path()
        if editor_path:
            self.config['DISPLAY']['EDITOR'] = editor_path
        elif 'EDITOR' in self.config['DISPLAY']:
            del self.config['DISPLAY']['EDITOR']
        
        # Update PROGRAM_PREFIX
        program_prefix = self.display_params['PROGRAM_PREFIX'].get_path()
        if program_prefix:
            self.config['DISPLAY']['PROGRAM_PREFIX'] = program_prefix
        elif 'PROGRAM_PREFIX' in self.config['DISPLAY']:
            del self.config['DISPLAY']['PROGRAM_PREFIX']
        
        # Update OPEN_FILE
        open_file = self.display_params['OPEN_FILE'].get_path()
        if open_file:
            self.config['DISPLAY']['OPEN_FILE'] = open_file
        elif 'OPEN_FILE' in self.config['DISPLAY']:
            del self.config['DISPLAY']['OPEN_FILE']
        
        # Update PYVCP
        if self.pyvcp_enabled.isChecked():
            pyvcp_path = self.pyvcp_path.text().strip()
            if pyvcp_path:
                self.config['DISPLAY']['PYVCP'] = pyvcp_path
            elif 'PYVCP' in self.config['DISPLAY']:
                del self.config['DISPLAY']['PYVCP']
        elif 'PYVCP' in self.config['DISPLAY']:
            del self.config['DISPLAY']['PYVCP']
    
# Modified update_rs274ngc_config method - preserves all values including duplicates
    def update_rs274ngc_config(self):
        """Update RS274NGC configuration preserving all values including REMAP entries"""
        logger.debug("Updating RS274NGC configuration")
        
        if 'RS274NGC' not in self.config:
            self.config.add_section('RS274NGC')
        
        # Get all current items to preserve structure
        all_items = {}
        for key, value in self.config.items('RS274NGC'):
            if key not in all_items:
                all_items[key] = []
            all_items[key].append(value)
        
        # Clear the section
        for key in list(self.config['RS274NGC'].keys()):
            del self.config['RS274NGC'][key]
        
        # Update standard parameters
        param_file = self.rs274_params['PARAMETER_FILE'].get_path()
        if param_file:
            self.config['RS274NGC']['PARAMETER_FILE'] = param_file
        
        startup_code = self.startup_code.text().strip()
        if startup_code:
            self.config['RS274NGC']['RS274NGC_STARTUP_CODE'] = startup_code
        
        sub_path = self.rs274_params['SUBROUTINE_PATH'].get_path()
        if sub_path:
            self.config['RS274NGC']['SUBROUTINE_PATH'] = sub_path
        
        user_m_path = self.rs274_params['USER_M_PATH'].get_path()
        if user_m_path:
            self.config['RS274NGC']['USER_M_PATH'] = user_m_path
        
        # Preserve FEATURES if it existed
        if 'FEATURES' in all_items:
            self.config['RS274NGC']['FEATURES'] = all_items['FEATURES'][0]
        
        # Preserve all REMAP entries (they can be multiple)
        if 'REMAP' in all_items:
            for i, remap_value in enumerate(all_items['REMAP']):
                if i == 0:
                    self.config['RS274NGC']['REMAP'] = remap_value
                else:
                    self.config['RS274NGC'][f'REMAP_{i+1}'] = remap_value
        
        logger.debug(f"Updated RS274NGC configuration")

# Modified update_hal_config method - uses IniFileHandler for correct multi-value handling
    def update_hal_config(self):
        """Update HAL/HALUI sections – replaces HALFILE and MDI_COMMAND lines correctly."""
        logger.debug("Updating HAL configuration")

        # HAL files
        hal_files_text = self.hal_files_text.toPlainText()
        hal_files = [l.rstrip() for l in hal_files_text.split('\n') if l.strip()]
        logger.debug(f"Text area contains {len(hal_files)} HAL files: {hal_files}")
        self.ini_handler.set_all('HAL', 'HALFILE', hal_files)

        # MDI Commands
        commands_text = self.halui_commands_text.toPlainText()
        commands = [l.rstrip() for l in commands_text.split('\n') if l.strip()]
        logger.debug(f"Text area contains {len(commands)} MDI commands: {commands}")
        self.ini_handler.set_all('HALUI', 'MDI_COMMAND', commands)

        logger.debug("HAL/HALUI updated via IniFileHandler")

    def check_file_permissions(self, filepath):
        """Check file permissions and return status"""
        logger.debug(f"Checking permissions for: {filepath}")
        
        if not os.path.exists(filepath):
            logger.error(f"File does not exist: {filepath}")
            return False
        
        logger.debug(f"File exists: {filepath}")
        logger.debug(f"File size: {os.path.getsize(filepath)} bytes")
        logger.debug(f"Readable: {os.access(filepath, os.R_OK)}")
        logger.debug(f"Writable: {os.access(filepath, os.W_OK)}")
        logger.debug(f"Executable: {os.access(filepath, os.X_OK)}")
        
        try:
            stat_info = os.stat(filepath)
            logger.debug(f"File mode: {oct(stat_info.st_mode)}")
            logger.debug(f"File owner: {stat_info.st_uid}")
            logger.debug(f"File group: {stat_info.st_gid}")
        except Exception as e:
            logger.error(f"Failed to get file stats: {e}")
        
        return True

    def save_ini_file(self):
        """Save the current configuration to the INI file.

        Multi-value keys (PROGRAM_EXTENSION, HALFILE, MDI_COMMAND …) are
        handled by IniFileHandler which edited self.ini_handler in place.

        Single-value keys (axis params, ATC, TRAJ, DISPLAY, RS274NGC) are
        synced from self.config into self.ini_handler before writing.
        """
        logger.debug("="*50)
        logger.debug("save_ini_file: STARTED")

        if not self.config or not self.config_file:
            logger.warning("save_ini_file: No INI file loaded")
            QMessageBox.warning(self, "Warning", "No INI file loaded")
            return

        try:
            if not os.path.exists(self.config_file):
                QMessageBox.critical(self, "Error",
                                     f"File does not exist: {self.config_file}")
                return

            if not os.access(self.config_file, os.W_OK):
                QMessageBox.critical(self, "Error",
                                     f"File is not writable: {self.config_file}")
                return

            # ---- Backup ------------------------------------------------
            backup_file = (self.config_file +
                           f".backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}")
            try:
                shutil.copy2(self.config_file, backup_file)
                logger.info(f"Backup created: {backup_file}")
                self.status_bar.showMessage(
                    f"Backup created: {os.path.basename(backup_file)}")
            except Exception as exc:
                logger.error(f"Backup failed (continuing): {exc}")

            # ---- Sync single-value keys from configparser -> ini_handler ----
            # Keys that are multi-value and already handled by update_*_config()
            MULTI_VALUE_KEYS = {
                'FILTER':  {'PROGRAM_EXTENSION'},
                'HAL':     {'HALFILE'},
                'HALUI':   {'MDI_COMMAND'},
                'RS274NGC': {'REMAP'},          # also multi-value, skip here
            }

            for section in self.config.sections():
                if not self.ini_handler.has_section(section):
                    logger.debug(f"Section [{section}] not in original file – skipping")
                    continue
                skip_keys = {k.upper() for k in MULTI_VALUE_KEYS.get(section, set())}
                for key, value in self.config[section].items():
                    if key.upper() in skip_keys:
                        continue
                    self.ini_handler.set(section, key, value)
                    logger.debug(f"  Synced [{section}] {key} = {value}")

            # ---- Write via IniFileHandler (preserves ALL structure) --------
            self.ini_handler.write(self.config_file)
            logger.info(f"Configuration saved to {self.config_file}")
            self.status_bar.showMessage(f"Saved: {self.config_file}")
            logger.debug("save_ini_file: COMPLETED SUCCESSFULLY")
            logger.debug("="*50)

            QMessageBox.information(
                self, "Success",
                f"INI file saved successfully\n"
                f"Backup created: {os.path.basename(backup_file)}")

        except Exception as exc:
            logger.error(f"save_ini_file: ERROR: {exc}")
            logger.error(traceback.format_exc())
            logger.debug("="*50)
            QMessageBox.critical(self, "Error",
                                 f"Failed to save INI file: {str(exc)}")

    def toggle_logging(self, state):
        if state == Qt.Checked:
            logging.getLogger().setLevel(logging.INFO)
            self.logger.info("Logging enabled")
        else:
            logging.getLogger().setLevel(logging.WARNING)