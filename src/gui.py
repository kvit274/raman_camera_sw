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

        # Camera preview and controls
        self.preview = QLabel("Preview")
        self.preview.setFixedSize(640,480)  # change to camera max width/height
        self.btn_connect_cam = QPushButton("Connect Camera")
        self.btn_live = QPushButton("Start Live")
        self.btn_stop = QPushButton("Stop Live")
        self.btn_acquire = QPushButton("Acquire")
        self.btn_disconnect_cam = QPushButton("Disconnect Camera")
        self.temp = QLabel("Temp: -- °C")

        # Spectrometer controls
        self.btn_connect_spec = QPushButton("Connect Spectrometer")
        self.btn_disconnect_spec = QPushButton("Disconnect Spectrometer")
        self.wavelength_input = QLineEdit()
        self.wavelength_input.setPlaceholderText("Wavelength (m)")
        self.wavelength_input.setValidator(QDoubleValidator())
        self.grating_input = QLineEdit()
        self.grating_input.setPlaceholderText("Grating (#)")
        self.grating_input.setValidator(QIntValidator())
        self.slit_width_input = QLineEdit()
        self.slit_width_input.setPlaceholderText("Slit Width (m)")
        self.slit_width_input.setValidator(QDoubleValidator())
        self.btn_update_spec = QPushButton("Update Spec Settings")



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
        layout.addWidget(self.temp)
        hl = QHBoxLayout()
        hl.addWidget(self.btn_connect_cam)
        hl.addWidget(self.btn_live)
        hl.addWidget(self.btn_stop)
        hl.addWidget(self.btn_acquire)
        hl.addWidget(self.btn_disconnect_cam)
        layout.addLayout(hl)
        hl_spec = QHBoxLayout()
        hl_spec.addWidget(self.btn_connect_spec)
        hl_spec.addWidget(self.btn_disconnect_spec)
        hl_spec.addWidget(self.wavelength_input)
        hl_spec.addWidget(self.grating_input)
        hl_spec.addWidget(self.slit_width_input)
        hl_spec.addWidget(self.btn_update_spec)
        layout.addLayout(hl_spec)

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

        # Connect buttons to controller cam
        self.btn_connect_cam.clicked.connect(self.connect_cam)
        self.btn_live.clicked.connect(self.start_live)
        self.btn_stop.clicked.connect(self.stop_live)
        self.btn_acquire.clicked.connect(self.acquire_frame)
        self.btn_disconnect_cam.clicked.connect(self.disconnect_cam)

        # Connect buttons to controller spec
        self.btn_connect_spec.clicked.connect(self.connect_spec)
        self.btn_disconnect_spec.clicked.connect(self.disconnect_spec)
        self.btn_update_spec.clicked.connect(self.update_spec_settings)

        # Live preview updates
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_preview)

        # Display temperature
        self.timer_temp = QTimer()
        self.timer_temp.timeout.connect(self.display_temp)
        self.timer_temp.start(1000)



    # ===== Functions ======

    # ==== Camera methods =====

    def connect_cam(self):
        self.controller.connect_cam()
        self.disable_buttons()
        self.worker = CoolingWorker(self.controller,target_temp=-80)
        self.worker.finished.connect(self.enable_buttons)
        self.worker.start()

    def disconnect_cam(self):
        self.disable_buttons()
        self.worker = WarmUpCloseWorker(self.controller)
        self.worker.finished.connect(self.enable_buttons)
        self.worker.start()

    def disable_buttons(self):
        for b in [self.btn_connect_cam, self.btn_live, self.btn_stop, self.btn_acquire]:
            b.setEnabled(False)
    
    def enable_buttons(self):
        for b in [self.btn_connect_cam, self.btn_live, self.btn_stop, self.btn_acquire]:
            b.setEnabled(True)

    def display_temp(self):
        temp,status = self.controller.get_temp()
        self.temp.setText(f"Temp: {temp} °C | {status}")

    def start_live(self):
        self.controller.start_live()
        self.timer.start(30)    # 30 is FPS, we might change it

    def stop_live(self):
        self.timer.stop()
        self.controller.stop_live()

    def update_preview(self):
        frame = self.controller.get_live_frame()
        if frame is None:
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
        if frame is None:
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

    # ==== Spectrometer methods =====

    def connect_spec(self):
        self.controller.connect_spec()
    
    def disconnect_spec(self):
        self.controller.disconnect_spec()
    
    def update_spec_settings(self):
        wavelength_text = self.wavelength_input.text()
        grating_text = self.grating_input.text()
        slit_width_text = self.slit_width_input.text()

        if wavelength_text:
            try:
                wavelength = float(wavelength_text)
                self.controller.set_wavelength_spec(wavelength)
            except ValueError:
                self.show_error("Invalid wavelength value")

        if grating_text:
            try:
                grating = int(grating_text)
                self.controller.set_grating_spec(grating)
            except ValueError:
                self.show_error("Invalid grating value")

        if slit_width_text:
            try:
                slit_width = float(slit_width_text)
                self.controller.set_slit_width_spec("input_side", slit_width)  # Example for input_side
            except ValueError:
                self.show_error("Invalid slit width value")
        

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
        self.controller.disconnect_cam()
        self.finished.emit()


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()

