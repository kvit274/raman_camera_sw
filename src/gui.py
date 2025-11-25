import sys
from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QStackedWidget, QLineEdit, QPushButton, QFileDialog, QLabel, QComboBox, QMessageBox
from PyQt5.QtGui import QIntValidator, QDoubleValidator, QImage, QPixmap
from PyQt5.QtCore import pyqtSignal, QTimer, QThread
import os
from controller import RamanCameraController

class MainWindow(QWidget):
    # run_clicked = pyqtSignal(dict)

    def __init__(self):

        super().__init__()
        self.setWindowTitle("Raman Camera GUI")

        # attach controller
        self.controller = RamanCameraController(view=self)

        self.preview = QLabel("Preview")
        self.preview.setFixedSize(640,480)
        self.btn_connect = QPushButton("Connect")
        self.btn_live = QPushButton("Start Live")
        self.btn_stop = QPushButton("Stop Live")
        self.btn_acquire = QPushButton("Acquire")
        self.btn_disconnect = QPushButton("Disconnect")

        # self.dlls_path = ""
        # self.save_path = ""
        # self.dlls_path_label = QLabel("No directory selected")
        # self.dlls_path_btn = QPushButton("Select dll folder")
        # self.dlls_path_btn.clicked.connect(self.select_dlls_path)
        # self.save_path_label = QLabel("No directory selected")
        # self.save_path_btn = QPushButton("Select where to save results")
        # self.save_path_btn.clicked.connect(self.select_save_path)
        # self.temp_input = QLineEdit()
        # self.temp_input.setPlaceholderText("temperature")
        # self.temp_input.setValidator(QDoubleValidator())
        # self.exposure_input = QLineEdit()
        # self.exposure_input.setPlaceholderText("exposure time")
        # self.exposure_input.setValidator(QDoubleValidator())
        # self.hbin_input = QLineEdit()
        # self.hbin_input.setPlaceholderText("hbin")
        # self.hbin_input.setValidator(QIntValidator())
        # self.vbin_input = QLineEdit()
        # self.vbin_input.setPlaceholderText("vbin")
        # self.vbin_input.setValidator(QIntValidator())
        # self.read_mode_input = QLineEdit()
        # self.read_mode_input.setPlaceholderText("read mode")
        # # self.acq_mode_input = QComboBox()
        # self.acq_mode_input = QLineEdit()
        # self.acq_mode_input.setPlaceholderText("read mode")
        # # self.acq_mode_input.addItems(["single","accumulate","run_till_abort","kinetic"])
        # # self.acq_mode_input.currentTextChanged.connect(self.toggle_accum_input)
        # # use drop down in future
        # self.accum_n_input = QLineEdit()
        # self.accum_n_input.setPlaceholderText("number of frame to accumulate, only for accumulate acquisition mode")
        # self.accum_n_input.setValidator(QIntValidator())
        # self.accum_n_input.hide()
        # self.roi_input = QLineEdit()
        # self.roi_input.setPlaceholderText("ROI in format (x,y,w,h)")
        # self.run_btn = QPushButton("Run")
        # self.run_btn.clicked.connect(self.run_exp)

        # layout
        layout = QVBoxLayout()
        layout.addWidget(self.preview)
        hl = QHBoxLayout()
        hl.addWidget(self.btn_connect)
        hl.addWidget(self.btn_live)
        hl.addWidget(self.btn_stop)
        hl.addWidget(self.btn_acquire)
        hl.addWidget(self.btn_disconnect)
        layout.addLayout(hl)

        # layout.addWidget(self.save_path_label)
        # layout.addWidget(self.dlls_path_label)
        # layout.addWidget(self.save_path_btn)
        # layout.addWidget(self.dlls_path_btn)
        # layout.addWidget(self.temp_input)
        # layout.addWidget(self.exposure_input)
        # layout.addWidget(self.hbin_input)
        # layout.addWidget(self.vbin_input)
        # layout.addWidget(self.read_mode_input)
        # layout.addWidget(self.acq_mode_input)
        # layout.addWidget(self.accum_n_input)
        # layout.addWidget(self.roi_input)
        # layout.addWidget(self.run_btn)

        self.setLayout(layout)

        # Connect buttons to controller
        self.btn_connect.clicked.connect(self.connect)
        self.btn_live.clicked.connect(self.start_live)
        self.btn_stop.clicked.connect(self.stop_live)
        self.btn_acquire.clicked.connect(self.acquire_frame)
        self.btn_disconnect.clicked.connect(self.disconnect)

        # Live preview updates
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_preview)


    # ===== Functions ======

    def connect(self):
        self.controller.connect()
        self.disable_buttons()
        self.worker = CoolingWorker(self.controller,target_temp=-80)
        self.worker.finished.connect(self.enable_buttons)
        self.worker.start()

    def disconnect(self):
        self.disable_buttons()
        self.worker = WarmUpCloseWorker(self.controller)
        self.worker.finished.connect(self.enable_buttons)
        self.worker.start()

    def disable_buttons(self):
        for b in [self.btn_connect, self.btn_live, self.btn_stop, self.btn_acquire]:
            b.setEnabled(False)
    
    def enable_buttons(self):
        for b in [self.btn_connect, self.btn_live, self.btn_stop, self.btn_acquire]:
            b.setEnabled(True)

    def start_live(self):
        self.controller.start_live()
        self.timer.start(30)    # 30 is FPS, we might change it

    def stop_live(self):
        self.time.stop()
        self.controller.stop_live()

    def update_preview(self):
        frame = self.controller.get_live_frame()
        if not frame:
            return
        self.display_image(frame)

    def display_image(self,frame):
        # !!! this needs to be fixed
        # Normalize to 8-bit
        frame8, h, w = self.controller.adjust_frame(frame)

        qimg = QImage(frame8.data, w, h, w, QImage.Format_Grayscale8)
        pix = QPixmap.fromImage(qimg)
        self.preview.setPixmap(pix.scaled(
            self.preview.width(),
            self.preview.height()
        ))
    
    def acquire_frame(self):
        frame = self.controller.acquire_single()
        if not frame:
            return
        self.display_image(frame)

    def toggle_accum_input(self, mode):
        if mode == "accumulate":
            self.accum_n_input.show()
        else:
            self.accum_n_input.hide()


    def select_dlls_path(self):
        file = QFileDialog.getExistingDirectory(self, "Select dll file")
        if file:
            self.dlls_path = file
            # self.dlls_path_label.setText(f"DLL file: {file}")
            self.dlls_path_label.setText(os.path.basename(file))

    def select_save_path(self):
        directory = QFileDialog.getExistingDirectory(self, "Select saving directory")
        if directory:
            self.save_path = directory
            self.save_path_label.setText(f"Save folder: {directory}")
            # self.save_path.setText(os.path.dirname(directory))

    # def run_exp(self):
    #     params = {
    #         "save_path": self.save_path,
    #         "dlls_path": self.dlls_path,
    #         "temp": self.temp_input.text(),
    #         "exposure_time": self.exposure_input.text(),
    #         "hbin": self.hbin_input.text(),
    #         "vbin": self.vbin_input.text(),
    #         "read_mode": self.read_mode_input.text(),
    #         "acq_mode": self.acq_mode_input.text(),
    #         "accum_n": self.accum_n_input.text() if self.accum_n_input.text() else None,
    #         "roi": self.roi_input.text() if self.roi_input.text() else None
    #     }

    #     self.run_clicked.emit(params)

    def show_info(self, message: str):
        QMessageBox.information(self, "Info", message)

    def show_error(self, message: str):
        QMessageBox.critical(self, "Error", message)

class CoolingWorker(QThread):
    finished = pyqtSignal()

    def __init__(self, controller, target_temp):
        super().__init__()
        self.controller = controller
        self.target_temp = target_temp

    def run(self):
        self.controller.cool_cam(self.target_temp)
        self.finished.emit()    # unlock buttons

class WarmUpCloseWorker(QThread):
    finished = pyqtSignal()

    def __init__(self, controller):
        super().__init__()
        self.controller = controller

    def run(self):
        self.controller.warm_cam()
        self.controller.disconnect()
        self.finished.emit()


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()

