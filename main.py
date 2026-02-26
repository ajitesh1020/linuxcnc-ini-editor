# main.py
import sys
import os
import logging
from pathlib import Path
from PySide6.QtWidgets import QApplication
from gui import LinuxCNCConfigEditor

if __name__ == "__main__":
    # Set locale to avoid Gtk warnings
    os.environ['LANG'] = 'C'
    os.environ['LC_ALL'] = 'C'
    
    app = QApplication(sys.argv)
    
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('linuxcnc_editor.log'),
            logging.StreamHandler()
        ]
    )
    
    window = LinuxCNCConfigEditor()
    window.show()
    sys.exit(app.exec())