import sys
from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QStackedWidget, QLineEdit, QPushButton, QFileDialog, QLabel
from PyQt5.QtGui import QIntValidator, QDoubleValidator
import os

class MainWindow(QWidget):
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
        self.dll_dir_path = ""
        self.save_dir_path = ""

        self.layout_info = QVBoxLayout()

        self.dll_dir_label = QLabel("No directory selected")
        self.dll_dir_btn = QPushButton("Select dll folder")
        self.dll_dir_btn.clicked.connect(self.select_dll_dir)

        self.save_dir_label = QLabel("No directory selected")
        self.save_dir_btn = QPushButton("Select where to save results")
        self.save_dir_btn.clicked.connect(self.select_save_dir)

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
        layout.addWidget(self.save_dir_label)
        layout.addWidget(self.dll_dir_label)
        layout.addWidget(self.save_dir_btn)
        layout.addWidget(self.dll_dir_btn)
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


    def select_dll_dir(self):
        directory = QFileDialog.getExistingDirectory(self, "Select dll directory")
        if directory:
            self.dll_dir = directory
            self.dll_dir_label.setText(f"DLL folder: {directory}")
            # self.dll_dir_label.setText(os.path.dirname(directory))

    def select_save_dir(self):
        directory = QFileDialog.getExistingDirectory(self, "Select saving directory")
        if directory:
            self.save_dir = directory
            self.save_dir_label.setText(f"Save folder: {directory}")
            # self.save_dir.setText(os.path.dirname(directory))

    def run_exp(self):
        if not self.save_dir:
            print("No save folder selected!")
            return
        if not self.dll_dir:
            print("No dll folder selected!")
            return
        
        try:
            self.temp = float(self.temp_input.text())
            self.exposure_time = float(self.exposure_input.text())
            self.hbin = float(self.hbin_input.text())
            self.vbin = float(self.vbin_input.text())
            self.read_mode = self.read_mode_input.text()
            self.acq_mode = self.acq_mode_input.text()
            self.accum_n = int(self.accum_n_input.text()) if self.accum_n_input.text() else None
            self.roi = self.roi_input.text() if self.roi_input.text() else None
            if not self.read_mode or not self.acq_mode:
                raise ValueError("please enter Read Mode and Acquisition Mode")
            run_code(self.temp,self.exposure_time,self.hbin,self.vbin,self.read_mode,self.acq_mode,self.accum_n,self.roi)

        except Exception:
            print("Wrong input")

# def run_code(temp,exposure_time,hbin,vbin,read_mode,acq_mode,accum_n,roi):
#     print("RUN:")
#     print("Temperature:", temp)
#     print("Exposure:", exposure_time)
#     print("HBIN:", hbin)
#     print("VBIN:", vbin)
#     print("Read mode:", read_mode)
#     print("Acq mode:", acq_mode)
#     print("Accum N:", accum_n)
#     print("ROI:", roi)
    

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()

