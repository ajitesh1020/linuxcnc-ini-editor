# scale_calculator.py
from PySide6.QtWidgets import *
from PySide6.QtCore import *

class ScaleCalculatorDialog(QDialog):
    def __init__(self, axis_name, current_scale, parent=None):
        super().__init__(parent)
        self.axis_name = axis_name
        self.current_scale = current_scale
        self.new_scale = None
        self.setup_ui()
        
    def setup_ui(self):
        self.setWindowTitle(f"Scale Calculator - Axis {self.axis_name}")
        self.setModal(True)
        self.setMinimumWidth(400)
        
        layout = QVBoxLayout()
        
        # Info label
        info_label = QLabel(
            "Calculate new scale based on known distance and measured distance.\n"
            "New Scale = (Commanded Distance / Measured Distance) × Current Scale"
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
        # Current scale display
        current_scale_layout = QHBoxLayout()
        current_scale_layout.addWidget(QLabel("Current Scale:"))
        self.current_scale_label = QLabel(f"{self.current_scale:.6f}")
        self.current_scale_label.setStyleSheet("font-weight: bold;")
        current_scale_layout.addWidget(self.current_scale_label)
        current_scale_layout.addStretch()
        layout.addLayout(current_scale_layout)
        
        # Input fields
        input_group = QGroupBox("Measurement Data")
        input_layout = QGridLayout()
        
        # Commanded distance
        input_layout.addWidget(QLabel("Commanded Distance (mm):"), 0, 0)
        self.cmd_distance = QDoubleSpinBox()
        self.cmd_distance.setRange(0.001, 10000)
        self.cmd_distance.setValue(100)
        self.cmd_distance.setDecimals(3)
        input_layout.addWidget(self.cmd_distance, 0, 1)
        
        # Measured distance
        input_layout.addWidget(QLabel("Measured Distance (mm):"), 1, 0)
        self.measured_distance = QDoubleSpinBox()
        self.measured_distance.setRange(0.001, 10000)
        self.measured_distance.setValue(100)
        self.measured_distance.setDecimals(3)
        input_layout.addWidget(self.measured_distance, 1, 1)
        
        input_group.setLayout(input_layout)
        layout.addWidget(input_group)
        
        # Calculate button
        self.calc_btn = QPushButton("Calculate New Scale")
        self.calc_btn.clicked.connect(self.calculate_scale)
        layout.addWidget(self.calc_btn)
        
        # Result display
        result_group = QGroupBox("Result")
        result_layout = QVBoxLayout()
        
        self.result_label = QLabel("Click Calculate to get new scale")
        self.result_label.setStyleSheet("font-size: 11pt; font-weight: bold; color: blue;")
        self.result_label.setWordWrap(True)
        result_layout.addWidget(self.result_label)
        
        result_group.setLayout(result_layout)
        layout.addWidget(result_group)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        self.apply_btn = QPushButton("Apply New Scale")
        self.apply_btn.clicked.connect(self.accept)
        self.apply_btn.setEnabled(False)
        button_layout.addWidget(self.apply_btn)
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)
        
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
        
    def calculate_scale(self):
        try:
            cmd_dist = self.cmd_distance.value()
            measured_dist = self.measured_distance.value()
            
            if measured_dist <= 0:
                QMessageBox.warning(self, "Warning", "Measured distance must be greater than 0")
                return
            
            # Calculate new scale
            ratio = cmd_dist / measured_dist
            self.new_scale = self.current_scale * ratio
            
            # Display result
            self.result_label.setText(
                f"New Scale: {self.new_scale:.6f}\n"
                f"(Change: {self.current_scale:.6f} → {self.new_scale:.6f})"
            )
            
            self.apply_btn.setEnabled(True)
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Calculation error: {str(e)}")
    
    def get_new_scale(self):
        return self.new_scale