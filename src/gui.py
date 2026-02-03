import atexit
import traceback
import sys
from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QStackedWidget, QLineEdit, QPushButton, QFileDialog, QLabel, QComboBox, QMessageBox
from PyQt5.QtGui import QIntValidator, QDoubleValidator, QImage, QPixmap
from PyQt5.QtCore import pyqtSignal, QTimer, QThread, Qt
import os
from controller import RamanCameraController
from widgets import MultiTrackWidget, SingleTrackWidget, FVBWidget, ImageWidget, RandomTrackWidget
from typing import Dict

class MainWindow(QMainWindow):
    # run_clicked = pyqtSignal(dict)

    def __init__(self):

        super().__init__()
        self.setWindowTitle("Raman Camera GUI")
        self.status = self.statusBar()
        self.status.setSizeGripEnabled(False)

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

        # Camera settings

        # ROI
        self.roi_hstart_input = QLineEdit()
        self.roi_hstart_input.setPlaceholderText("ROI H Start")
        self.roi_hstart_input.setValidator(QIntValidator())
        self.roi_hend_input = QLineEdit()
        self.roi_hend_input.setPlaceholderText("ROI H End")
        self.roi_hend_input.setValidator(QIntValidator())
        self.roi_vstart_input = QLineEdit()
        self.roi_vstart_input.setPlaceholderText("ROI V Start")
        self.roi_vstart_input.setValidator(QIntValidator())
        self.roi_vend_input = QLineEdit()
        self.roi_vend_input.setPlaceholderText("ROI V End")
        self.roi_vend_input.setValidator(QIntValidator())
        self.roi_hbin_input = QLineEdit()
        self.roi_hbin_input.setPlaceholderText("ROI H Bin")
        self.roi_hbin_input.setValidator(QIntValidator())
        self.roi_vbin_input = QLineEdit()
        self.roi_vbin_input.setPlaceholderText("ROI V Bin")
        self.roi_vbin_input.setValidator(QIntValidator())
        # self.btn_set_roi = QPushButton("Set ROI")

        # Shutter controls
        self.shutter_mode_input = QComboBox()
        self.shutter_mode_input.addItems(["auto", "open", "close"])
        self.tll_mode_input = QComboBox()
        self.tll_mode_input.addItems(["0", "1"]) # ask about these
        self.shutter_open_time_input = QLineEdit()
        self.shutter_open_time_input.setPlaceholderText("Shutter Open Time (ms)")
        self.shutter_open_time_input.setValidator(QDoubleValidator())
        self.shutter_close_time_input = QLineEdit()
        self.shutter_close_time_input.setPlaceholderText("Shutter Close Time (ms)")
        self.shutter_close_time_input.setValidator(QDoubleValidator())
        # self.btn_set_shutter = QPushButton("Set Shutter")
        self.shutter_current_state = QLabel("Shutter State: --")

        # Read mode
        self.read_mode_input = QComboBox()
        self.read_mode_input.addItems(["fvb", "image", "single_track", "multi_track", "random_track"])
        self.read_mode_stack = QStackedWidget()
        self.read_mode_widgets = {
            "fvb": FVBWidget(),
            "image": ImageWidget(),
            "single_track": SingleTrackWidget(),
            "multi_track": MultiTrackWidget(),
            "random_track": RandomTrackWidget()
        }

        for w in self.read_mode_widgets.values():
            self.read_mode_stack.addWidget(w)

        # Acquisition 
        self.acquisition_mode_input = QComboBox()
        self.acquisition_mode_input.addItems(["single", "accum", "kinetic", "fast_kinetic", "cont"])

        # Trigger mode
        self.trigger_mode_input = QComboBox()
        self.trigger_mode_input.addItems(["int","ext","ext_start","ext_exp","ext_fvb_em","software","ext_charge_shift"])

        # Exposure
        self.exposure_input = QLineEdit()
        self.exposure_input.setPlaceholderText("Exposure time (ms)")
        self.exposure_input.setValidator(QDoubleValidator())

        # Amp
        self.amp_mode_input = QComboBox()

        # Vsspeed
        self.vsspeed_input  = QComboBox()

        # EMCCD gain
        self.emccd_gain_input = QLineEdit()
        self.emccd_gain_input.setPlaceholderText("EMCCD gain, do not exceed 300")
        self.emccd_gain_input.setValidator(QDoubleValidator())

        self.set_settings_button = QPushButton("Apply Settings")

        # Spectrometer controls
        # self.btn_connect_spec = QPushButton("Connect Spectrometer")
        # self.btn_disconnect_spec = QPushButton("Disconnect Spectrometer")
        # self.wavelength_input = QLineEdit()
        # self.wavelength_input.setPlaceholderText("Wavelength (m)")
        # self.wavelength_input.setValidator(QDoubleValidator())
        # self.grating_input = QLineEdit()
        # self.grating_input.setPlaceholderText("Grating (#)")
        # self.grating_input.setValidator(QIntValidator())
        # self.slit_width_input = QLineEdit()
        # self.slit_width_input.setPlaceholderText("Slit Width (m)")
        # self.slit_width_input.setValidator(QDoubleValidator())
        # self.btn_update_spec = QPushButton("Update Spec Settings")


        # ===== LAYOUT =====

        layout = QVBoxLayout()
        layout.addWidget(self.preview)
        layout.addWidget(self.temp)
        layout.addWidget(self.shutter_current_state)
        layout.addWidget(self.set_settings_button)

        # Camera control buttons
        hl = QHBoxLayout()
        hl.addWidget(self.btn_connect_cam)
        hl.addWidget(self.btn_live)
        hl.addWidget(self.btn_stop)
        hl.addWidget(self.btn_acquire)
        hl.addWidget(self.btn_disconnect_cam)
        layout.addLayout(hl)

        # Spectrometer controls
        # hl_spec = QHBoxLayout()
        # hl_spec.addWidget(self.btn_connect_spec)
        # hl_spec.addWidget(self.btn_disconnect_spec)
        # hl_spec.addWidget(self.wavelength_input)
        # hl_spec.addWidget(self.grating_input)
        # hl_spec.addWidget(self.slit_width_input)
        # hl_spec.addWidget(self.btn_update_spec)
        # layout.addLayout(hl_spec)

        # ROI controls
        hl_roi = QHBoxLayout()
        hl_roi.addWidget(QLabel("Roi:"))
        hl_roi.addWidget(self.roi_hstart_input)
        hl_roi.addWidget(self.roi_hend_input)
        hl_roi.addWidget(self.roi_vstart_input)
        hl_roi.addWidget(self.roi_vend_input)
        hl_roi.addWidget(self.roi_hbin_input)
        hl_roi.addWidget(self.roi_vbin_input)
        # hl_roi.addWidget(self.btn_set_roi)
        layout.addLayout(hl_roi)

        # Shutter controls
        hl_shutter = QHBoxLayout()
        hl_shutter.addWidget(QLabel("Shutter:"))
        hl_shutter.addWidget(self.shutter_mode_input)
        hl_shutter.addWidget(self.tll_mode_input)
        hl_shutter.addWidget(self.shutter_open_time_input)
        hl_shutter.addWidget(self.shutter_close_time_input)
        # hl_shutter.addWidget(self.btn_set_shutter)
        layout.addLayout(hl_shutter)

        # Read mode
        hl_read_mode = QHBoxLayout()
        hl_read_mode.addWidget(QLabel("Read Mode:"))
        hl_read_mode.addWidget(self.read_mode_input)
        layout.addLayout(hl_read_mode)

        layout.addWidget(self.read_mode_stack)

        # acquisition
        hl_acquisition_mode = QHBoxLayout()
        hl_acquisition_mode.addWidget(QLabel("Acquisition Mode:"))
        hl_acquisition_mode.addWidget(self.acquisition_mode_input)
        layout.addLayout(hl_acquisition_mode)

        # trigger mode
        hl_trigger_mode = QHBoxLayout()
        hl_trigger_mode.addWidget(QLabel("Trigger Mode:"))
        hl_trigger_mode.addWidget(self.trigger_mode_input)
        layout.addLayout(hl_trigger_mode)

        # Amp mode
        hl_amp_mode = QHBoxLayout()
        hl_amp_mode.addWidget(QLabel("Amp Mode:"))
        hl_amp_mode.addWidget(self.amp_mode_input)
        layout.addLayout(hl_amp_mode)

        # Vsspeed
        hl_vsspeed = QHBoxLayout()
        hl_vsspeed.addWidget(QLabel("Vsspeed:"))
        hl_vsspeed.addWidget(self.vsspeed_input)
        layout.addLayout(hl_vsspeed)

        # EMCCD gain
        hl_emccd_gain = QHBoxLayout()
        hl_emccd_gain.addWidget(QLabel("EMCCD gain"))
        hl_emccd_gain.addWidget(self.emccd_gain_input)
        layout.addLayout(hl_emccd_gain)

        # set central widget
        central = QWidget()
        central.setLayout(layout)
        self.setCentralWidget(central)


        # Connect buttons to controller cam
        self.btn_connect_cam.clicked.connect(self.connect_cam)
        self.btn_live.clicked.connect(self.start_live)
        self.btn_stop.clicked.connect(self.stop_live)
        self.btn_acquire.clicked.connect(self.start_acquisition)
        self.btn_disconnect_cam.clicked.connect(self.disconnect_cam)
        # might join these below later
        # self.btn_set_roi.clicked.connect(self.set_roi)
        # self.btn_set_shutter.clicked.connect(self.set_shutter)
        self.set_settings_button.clicked.connect(self.set_settings)
        self.read_mode_input.currentTextChanged.connect(
            self.on_read_mode_changed
        )


        # Connect buttons to controller spec
        # self.btn_connect_spec.clicked.connect(self.connect_spec)
        # self.btn_disconnect_spec.clicked.connect(self.disconnect_spec)
        # self.btn_update_spec.clicked.connect(self.update_spec_settings)

        # Live preview updates
        self.timer_live = QTimer()
        self.timer_live.timeout.connect(self.update_preview)

        # Display temperature
        self.timer_temp = QTimer()
        self.timer_temp.timeout.connect(self.display_temp)
        self.timer_temp.start(1000)

    def load_amp_modes(self,amp_modes):
        self.amp_mode_input.clear()
        print(f"Amp modes: {len(amp_modes)}")

        for m in amp_modes:
            label = (
                f"channel={m.channel}, channel_bitdepth={m.channel_bitdepth}, oamp={m.oamp}, oamp_kind={m.oamp_kind}, hsspeed={m.hsspeed}, hsspeed_MHz={m.hsspeed_MHz}, preamp={m.preamp}, preamp_gain={m.preamp_gain}"
            )
            self.amp_mode_input.addItem(label)
            self.amp_mode_input.setItemData(self.amp_mode_input.count()-1, m, Qt.UserRole)
        print(f"Items in combo: {self.amp_mode_input.count()}")

    def load_vsspeeds(self,vsspeeds):
        self.vsspeed_input.clear()

        for idx,value in enumerate(vsspeeds):
            label = f"{value} ms"
            self.vsspeed_input.addItem(label)

            # store index
            self.vsspeed_input.setItemData(self.vsspeed_input.count()-1,idx,Qt.UserRole+1)

    def on_read_mode_changed(self, mode):
        widget = self.read_mode_widgets[mode]
        self.read_mode_stack.setCurrentWidget(widget)

    def display_used_params(self, roi:Dict[str,str], shutter:Dict[str,str], read_mode:str):
        """Display used parameters in the GUI fields."""

        self.roi_hstart_input.setText(roi["hstart"])
        self.roi_hend_input.setText(roi["hend"])
        self.roi_vstart_input.setText(roi["vstart"])
        self.roi_vend_input.setText(roi["vend"])
        self.roi_hbin_input.setText(roi["hbin"])
        self.roi_vbin_input.setText(roi["vbin"])

        self.shutter_mode_input.setCurrentText(shutter["mode"])
        self.tll_mode_input.setCurrentText(shutter["tll_mode"])
        self.shutter_open_time_input.setText(shutter["open_time"])
        self.shutter_close_time_input.setText(shutter["close_time"])

        self.read_mode_input.setCurrentText(read_mode)


    def display_msg(self, message:str):
        self.status.showMessage(message, 5000)  # display for 5 seconds

    def display_temp(self):
        temp,status = self.controller.get_temp()
        self.temp.setText(f"Temp: {temp} °C | {status}")

    def display_shutter_state(self, state:str):
        self.shutter_current_state.setText(f"Shutter State: {state}")


    # ===== Functions ======

    # ==== Camera methods =====

    def connect_cam(self):
        self.controller.connect_cam()
        # self.disable_buttons()
        # self.worker = CoolingWorker(self.controller,target_temp=-80)
        # self.worker.finished.connect(self.enable_buttons)
        # self.worker.start()

    def disconnect_cam(self):
        self.controller.disconnect_cam()

    def disable_buttons(self):
        for b in [self.btn_connect_cam, self.btn_live, self.btn_stop, self.btn_acquire]:
            b.setEnabled(False)
    
    def enable_buttons(self):
        for b in [self.btn_connect_cam, self.btn_live, self.btn_stop, self.btn_acquire]:
            b.setEnabled(True)

    def set_settings(self):
        roi = {
            "hstart": self.roi_hstart_input.text(),
            "hend": self.roi_hend_input.text(),
            "vstart": self.roi_vstart_input.text(),
            "vend": self.roi_vend_input.text(),
            "hbin": self.roi_hbin_input.text(),
            "vbin": self.roi_vbin_input.text()
        }

        shutter = {
            "mode": self.shutter_mode_input.currentText(),
            "tll_mode": self.tll_mode_input.currentText(),
            "open_time": self.shutter_open_time_input.text(),
            "close_time": self.shutter_close_time_input.text()
        }

        active_widget = self.read_mode_stack.currentWidget()
        read_mode_params = active_widget.get_params()

        acquisition_mode = self.acquisition_mode_input.currentText()

        trigger_mode = self.trigger_mode_input.currentText()

        exposure = self.exposure_input.text()

        amp_mode = self.amp_mode_input.currentData(Qt.UserRole)
        if amp_mode is not None:
            amp = {
                "channel": amp_mode.channel,
                "oamp": amp_mode.oamp,
                "hsspeed": amp_mode.hsspeed,
                "preamp": amp_mode.preamp
            }
        else:
            amp = {
                "channel": None,
                "oamp": None,
                "hsspeed": None,
                "preamp": None
            }

        vsspeed = self.vsspeed_input.currentData(Qt.UserRole+1)

        emccd_gain = self.emccd_gain_input.text()

        self.controller.apply_cam_settings(roi, shutter, read_mode_params, acquisition_mode, trigger_mode, exposure, amp, vsspeed, emccd_gain)

    def start_live(self):
        self.controller.start_live()
    
    def start_live_timer(self):
        self.timer_live.start(30)    # 30 is FPS, we might change it

    def stop_live(self):
        self.controller.stop_live()

    def stop_live_timer(self):
        self.timer_live.stop()

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
    
    def start_acquisition(self):
        frame = self.controller.acquire_single()
        # frame = self.controller.start_acquisition()
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


    # def show_info(self, message: str):
    #     QMessageBox.information(self, "Info", message)

    # def show_error(self, message: str):
    #     QMessageBox.critical(self, "Error", message)


    # ==== Spectrometer methods (unused) =====

    # def connect_spec(self):
    #     self.controller.connect_spec()
    
    # def disconnect_spec(self):
    #     self.controller.disconnect_spec()
    
    # def update_spec_settings(self):
    #     wavelength_text = self.wavelength_input.text()
    #     grating_text = self.grating_input.text()
    #     slit_width_text = self.slit_width_input.text()

    #     if wavelength_text:
    #         try:
    #             wavelength = float(wavelength_text)
    #             self.controller.set_wavelength_spec(wavelength)
    #         except ValueError:
    #             self.show_error("Invalid wavelength value")

    #     if grating_text:
    #         try:
    #             grating = int(grating_text)
    #             self.controller.set_grating_spec(grating)
    #         except ValueError:
    #             self.show_error("Invalid grating value")

    #     if slit_width_text:
    #         try:
    #             slit_width = float(slit_width_text)
    #             self.controller.set_slit_width_spec("input_side", slit_width)  # Example for input_side
    #         except ValueError:
    #             self.show_error("Invalid slit width value")
        

    # Override closeEvent to ensure safe shutdown

    def closeEvent(self, event):
        """
        Runs automatically when the user closes the GUI.
        Ensures the camera is warmed and disconnected safely.
        """
        print("[GUI] Application closing... running safe shutdown")

        try:
            # Stop live preview if running
            try:
                self.timer.stop()
            except:
                pass
            try:
                self.controller.stop_live()
            except:
                pass

            # Warm up the camera
            try:
                self.controller.warm_cam()
                print("Camera warmed up due to forced shutdown.")
            except Exception as e:
                print("Warm-up failed:", e)

            # Disconnect camera
            try:
                self.controller.disconnect_cam()
                print("Camera disconnected safely due to shutdown.")
            except Exception as e:
                print("Camera disconnect failed:", e)

            # Disconnect spectrometer safely
            try:
                self.controller.disconnect_spec()
            except Exception as e:
                print("Spectrometer disconnect failed:", e)

        except Exception as e:
            print("[GUI] Unexpected error during closeEvent:", e)

        event.accept()


def _safe_exit_close():
    """Extra safety: runs even if an exception kills the app."""
    try:
        app = QApplication.instance()
        if not app:
            return
        window = app.activeWindow()
        if not window:
            return

        ctrl = window.controller

        print("[EXIT] Python exiting — running safe camera shutdown")

        # Try warm cam
        try:
            ctrl.warm_cam()
        except:
            pass

        # Try disconnect cam
        try:
            ctrl.disconnect_cam()
        except:
            pass

        # Spectrometer safe disconnect
        try:
            ctrl.disconnect_spec()
        except:
            pass

    except Exception as e:
        print("[EXIT] Error in atexit shutdown:", e)

# Register handler
atexit.register(_safe_exit_close)

def excepthook(exc_type, exc_value, exc_traceback):
    traceback.print_exception(exc_type, exc_value, exc_traceback)
    _safe_exit_close()

sys.excepthook = excepthook

def main():
    app = QApplication(sys.argv)
    app.setStyleSheet("""
        QWidget {
            background-color: grey;
            color: white;
        }
    """)

    window = MainWindow()
    window.move(0,0)
    window.showMaximized()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()

