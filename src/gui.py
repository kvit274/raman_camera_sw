import sys
from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QStackedWidget, QLineEdit, QPushButton, QFileDialog, QLabel
from PyQt5.QtGui import QIntValidator, QDoubleValidator
from PyQt5.QtCore import pyqtSignal
import os
from controller import RamanCameraController

class MainWindow(QWidget):
    run_clicked = pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Raman Camera GUI")
        # x = 0
        # y = 0
        # width = 500
        # height = 500
        # self.setGeometry(x,y,width,height)

        # self.initUI()
    # def initUI(self):
        self.dll_path_path = ""
        self.save_path_path = ""

        self.dll_path_label = QLabel("No directory selected")
        self.dll_path_btn = QPushButton("Select dll folder")
        self.dll_path_btn.clicked.connect(self.select_dll_path)

        self.save_path_label = QLabel("No directory selected")
        self.save_path_btn = QPushButton("Select where to save results")
        self.save_path_btn.clicked.connect(self.select_save_path)

        self.temp_input = QLineEdit()
        self.temp_input.setPlaceholderText("temperature")
        self.temp_input.setValidator(QDoubleValidator())
        # also need to validate for sanity

        self.exposure_input = QLineEdit()
        self.exposure_input.setPlaceholderText("exposure time")
        self.exposure_input.setValidator(QDoubleValidator())


        self.hbin_input = QLineEdit()
        self.hbin_input.setPlaceholderText("hbin")
        self.hbin_input.setValidator(QDoubleValidator())

        self.vbin_input = QLineEdit()
        self.vbin_input.setPlaceholderText("vbin")
        self.vbin_input.setValidator(QDoubleValidator())

        self.read_mode_input = QLineEdit()
        self.read_mode_input.setPlaceholderText("read mode")
        # use drop down in future

        self.acq_mode_input = QLineEdit()
        self.acq_mode_input.setPlaceholderText("acquisition mode")
        # use drop down in future

        self.accum_n_input = QLineEdit()
        self.accum_n_input.setPlaceholderText("number of frame to accumulate, only for accumulate acquisition mode")
        self.accum_n_input.setValidator(QIntValidator())

        self.roi_input = QLineEdit()
        self.roi_input.setPlaceholderText("ROI in format (x,y,w,h)")
        # validate for format

        # run experiment
        self.run_btn = QPushButton("Run")
        self.run_btn.clicked.connect(self.run_exp)

        # layout
        layout = QVBoxLayout()
        layout.addWidget(self.save_path_label)
        layout.addWidget(self.dll_path_label)
        layout.addWidget(self.save_path_btn)
        layout.addWidget(self.dll_path_btn)
        layout.addWidget(self.temp_input)
        layout.addWidget(self.exposure_input)
        layout.addWidget(self.hbin_input)
        layout.addWidget(self.vbin_input)
        layout.addWidget(self.read_mode_input)
        layout.addWidget(self.acq_mode_input)
        layout.addWidget(self.accum_n_input)
        layout.addWidget(self.roi_input)
        layout.addWidget(self.run_btn)

        self.setLayout(layout)

        # attach controller
        self.controller = RamanCameraController()


    def select_dll_path(self):
        directory = QFileDialog.getExistingDirectory(self, "Select dll directory")
        if directory:
            self.dll_path = directory
            self.dll_path_label.setText(f"DLL folder: {os.path.dirname(directory)}")
            # self.dll_path_label.setText(os.path.dirname(directory))

    def select_save_path(self):
        directory = QFileDialog.getExistingDirectory(self, "Select saving directory")
        if directory:
            self.save_path = directory
            self.save_path_label.setText(f"Save folder: {os.path.dirname(directory)}")
            # self.save_path.setText(os.path.dirname(directory))

    def run_exp(self):
        params = {
            "save_path": self.save_path,
            "dll_path": self.dll_path,
            "temp": self.temp_input.text(),
            "exposure_time": self.exposure_input.text(),
            "hbin": self.hbin_input.text(),
            "vbin": self.vbin_input.text(),
            "read_mode": self.read_mode_input.text(),
            "acq_mode": self.acq_mode_input.text(),
            "accum_n": self.accum_n_input.text() if self.accum_n_input.text() else None,
            "roi": self.roi_input.text() if self.roi_input.text() else None
        }

        self.run_clicked.emit(params)

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()

