import atexit
import traceback
from pathlib import Path
import sys
from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QStackedWidget, QLineEdit, QPushButton, QFileDialog, QLabel, QComboBox, QMessageBox, QScrollArea, QGroupBox, QSizePolicy, QSplitter
from PyQt5.QtGui import QIntValidator, QDoubleValidator, QImage, QPixmap
from PyQt5.QtCore import pyqtSignal, QTimer, QThread, Qt
import os
from controller import RamanCameraController
from widgets import MultiTrackWidget, SingleTrackWidget, FVBWidget, ImageWidget, RandomTrackWidget, SingleWidget, AccumWidget, KineticWidget, FastKineticWidget, ContinuousWidget, CollapsibleSection, QNoScrollComboBox, PreviewWidget, RulerContainer
from typing import Dict

class MainWindow(QMainWindow):

    def __init__(self):

        super().__init__()
        self.setWindowTitle("Raman Camera GUI")
        self.status = self.statusBar()
        self.status.setSizeGripEnabled(False)

        # attach controller
        self.controller = RamanCameraController(view=self)

        # Camera preview and controls
        self.preview = PreviewWidget()
        self.preview.setFixedSize(1024,256)  # change to camera max width/height
        self.preview_container = RulerContainer(self.preview)
        self.btn_connect_cam = QPushButton("Connect Camera")
        self.btn_live = QPushButton("Start Live")
        self.btn_stop = QPushButton("Stop Live")
        self.btn_acquire = QPushButton("Acquire")
        self.btn_disconnect_cam = QPushButton("Disconnect Camera")
        self.temp = QLabel("Temp: -- °C")

        # Save path directories
        self.save_frame_path_button = QPushButton("Save frames to:")
        self.save_frame_path_label = QLabel("Frames saved to: ./data")

        # Camera settings


        # Shutter controls
        self.shutter_mode_input = QNoScrollComboBox()
        self.shutter_mode_input.addItems(["auto", "open", "closed"])
        self.tll_mode_input = QNoScrollComboBox()
        self.tll_mode_input.addItems(["0", "1"]) # THESE NEEDS TO BE CHANGED TO: TTL_low TTL_high for nicer ux
        self.shutter_open_time_input = QLineEdit()
        self.shutter_open_time_input.setPlaceholderText("Shutter Open Time (ms)")
        self.shutter_open_time_input.setValidator(QDoubleValidator())
        self.shutter_close_time_input = QLineEdit()
        self.shutter_close_time_input.setPlaceholderText("Shutter Close Time (ms)")
        self.shutter_close_time_input.setValidator(QDoubleValidator())
        # self.btn_set_shutter = QPushButton("Set Shutter")
        self.shutter_current_state = QLabel("Shutter State: --")

        # Read mode
        self.read_mode_input = QNoScrollComboBox()
        self.read_mode_input.addItems(["fvb", "image", "single_track", "multi_track", "random_track"])
        self.read_mode_input.setCurrentText("image")
        self.read_mode_stack = QStackedWidget()
        self.read_mode_stack.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        image_widget = ImageWidget()
        image_widget.roi_visual_changed.connect(self.update_image_preview_overlay)  # connect to draw on preview
        self.read_mode_widgets = {
            "fvb": FVBWidget(),
            "image": image_widget,
            "single_track": SingleTrackWidget(),
            "multi_track": MultiTrackWidget(),
            "random_track": RandomTrackWidget()
        }

        

        for w in self.read_mode_widgets.values():
            self.read_mode_stack.addWidget(w)

        # Acquisition 
        self.acquisition_mode_input = QNoScrollComboBox()
        self.acquisition_mode_input.addItems(["single", "accum", "kinetic", "fast_kinetic", "cont"])
        self.acquisition_mode_stack = QStackedWidget()
        self.acquisition_mode_widgets = {
            "single": SingleWidget(),
            "accum": AccumWidget(),
            "kinetic": KineticWidget(),
            "fast_kinetic": FastKineticWidget(),
            "cont": ContinuousWidget()
        }

        for w in self.acquisition_mode_widgets.values():
            self.acquisition_mode_stack.addWidget(w)

        # Trigger mode
        self.trigger_mode_input = QNoScrollComboBox()
        self.trigger_mode_input.addItems(["int","ext","ext_start","ext_exp","ext_fvb_em","software","ext_charge_shift"])

        # Exposure
        self.exposure_input = QLineEdit()
        self.exposure_input.setPlaceholderText("Exposure time (s)")
        self.exposure_input.setValidator(QDoubleValidator())

        # Amp
        self.amp_mode_input = QNoScrollComboBox()

        # Vsspeed
        self.vsspeed_input  = QNoScrollComboBox()

        # EMCCD gain
        self.emccd_gain_input = QLineEdit()
        self.emccd_gain_input.setPlaceholderText("EMCCD gain, do not exceed 300")
        self.emccd_gain_input.setValidator(QDoubleValidator())

        self.set_settings_button = QPushButton("Apply Settings")

        # ==== Acquisition progress ====
        self.acquisition_state = QLabel("Acquisition in progress: False")


        # ===== LAYOUT (split) =====

        # ==== LEFT PANEL (FULL HEIGHT) ====
        

        left_container = QWidget()
        left_layout = QVBoxLayout(left_container)
        left_layout.setSpacing(10)
        left_layout.setContentsMargins(10, 10, 10, 10)

        left_container.setStyleSheet("""
            QWidget {
                background-color: #2b2b2b;
            }
        """)

        # -------- Camera Control (NOT collapsible) --------
        control_layout = QVBoxLayout()

        control_layout.addWidget(QLabel("Camera Control"))
        control_layout.addWidget(self.btn_connect_cam)
        control_layout.addWidget(self.btn_live)
        control_layout.addWidget(self.btn_stop)
        control_layout.addWidget(self.btn_acquire)
        control_layout.addWidget(self.btn_disconnect_cam)
        control_layout.addWidget(self.save_frame_path_button)
        control_layout.addWidget(self.save_frame_path_label)

        left_layout.addLayout(control_layout)

        # -------- Shutter --------
        section_shutter = CollapsibleSection("Shutter")
        shutter_layout = QVBoxLayout()

        shutter_layout.addWidget(QLabel("Mode"))
        shutter_layout.addWidget(self.shutter_mode_input)

        shutter_layout.addWidget(QLabel("TTL Mode"))
        shutter_layout.addWidget(self.tll_mode_input)

        shutter_layout.addWidget(QLabel("Open Time (ms)"))
        shutter_layout.addWidget(self.shutter_open_time_input)

        shutter_layout.addWidget(QLabel("Close Time (ms)"))
        shutter_layout.addWidget(self.shutter_close_time_input)

        section_shutter.setContentLayout(shutter_layout)
        left_layout.addWidget(section_shutter)

        # -------- Read Mode --------
        section_read = CollapsibleSection("Read Mode")
        read_layout = QVBoxLayout()

        read_layout.addWidget(self.read_mode_input)
        read_layout.addWidget(self.read_mode_stack)

        section_read.setContentLayout(read_layout)
        left_layout.addWidget(section_read)

        # -------- Acquisition --------
        section_acq = CollapsibleSection("Acquisition")
        acq_layout = QVBoxLayout()

        acq_layout.addWidget(QLabel("Acquisition Mode"))
        acq_layout.addWidget(self.acquisition_mode_input)

        acq_layout.addWidget(self.acquisition_mode_stack)

        acq_layout.addWidget(QLabel("Trigger Mode"))
        acq_layout.addWidget(self.trigger_mode_input)

        acq_layout.addWidget(QLabel("Exposure (ms)"))
        acq_layout.addWidget(self.exposure_input)

        section_acq.setContentLayout(acq_layout)
        left_layout.addWidget(section_acq)

        # -------- Amplifier --------
        section_amp = CollapsibleSection("Amplifier / Speed")
        amp_layout = QVBoxLayout()

        amp_layout.addWidget(QLabel("Amp Mode"))
        amp_layout.addWidget(self.amp_mode_input)

        amp_layout.addWidget(QLabel("Vertical Shift Speed"))
        amp_layout.addWidget(self.vsspeed_input)

        amp_layout.addWidget(QLabel("EMCCD Gain"))
        amp_layout.addWidget(self.emccd_gain_input)

        section_amp.setContentLayout(amp_layout)
        left_layout.addWidget(section_amp)

        left_layout.addWidget(self.set_settings_button)
        left_layout.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(left_container)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        # ============================================================
        # RIGHT PREVIEW (FULL HEIGHT)
        # ============================================================

        preview_container = QWidget()
        preview_layout = QVBoxLayout(preview_container)
        preview_layout.setContentsMargins(0, 0, 0, 0)

        preview_container.setStyleSheet("""
            QWidget {
                background-color: #3c3f41;
                border-left: 1px solid #555555;
            }
        """)

        self.preview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        # self.preview.setAlignment(Qt.AlignRight |Qt.AlignVCenter)

        # preview_layout.addWidget(self.preview, alignment = Qt.AlignRight)
        preview_layout.addWidget(self.preview_container, alignment = Qt.AlignRight)

        # ============================================================
        # SPLITTER (DRAGGABLE)
        # ============================================================

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(scroll)
        splitter.addWidget(preview_container)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Expanding)

        # ============================================================
        # STATUS BAR (BOTTOM STRIP)
        # ============================================================

        status_container = QWidget()
        status_container.setObjectName("statusBarContainer")
        status_layout = QHBoxLayout(status_container)
        status_layout.setContentsMargins(10, 5, 10, 5)

        # self.status = QLabel("")
        self.status.setStyleSheet("color: red;")

        status_layout.addWidget(self.temp)
        status_layout.addWidget(self._separator())
        status_layout.addWidget(self.shutter_current_state)
        status_layout.addWidget(self._separator())
        status_layout.addWidget(self.acquisition_state)
        status_layout.addWidget(self._separator())
        status_layout.addStretch()
        status_layout.addWidget(self.status)

        status_container.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Fixed)

        # ============================================================
        # FINAL MAIN LAYOUT
        # ============================================================

        main_layout = QVBoxLayout()
        main_layout.addWidget(splitter,1)
        main_layout.addWidget(status_container)

        central = QWidget()
        central.setLayout(main_layout)
        self.setCentralWidget(central)


        # Connect buttons to controller cam
        self.btn_connect_cam.clicked.connect(self.connect_cam)
        self.btn_live.clicked.connect(self.start_live)
        self.btn_stop.clicked.connect(self.stop_live)
        self.btn_acquire.clicked.connect(self.start_acquisition)
        self.btn_disconnect_cam.clicked.connect(self.disconnect_cam)
        self.set_settings_button.clicked.connect(self.set_settings)
        self.read_mode_input.currentTextChanged.connect(self.on_read_mode_changed)
        self.on_read_mode_changed("image")      # update ui for image
        self.acquisition_mode_input.currentTextChanged.connect(self.on_acquisition_mode_changed)
        self.on_acquisition_mode_changed("single")
        self.save_frame_path_button.clicked.connect(self.select_save_frame_path)

        # Live preview updates
        self.timer_live = QTimer()
        self.timer_live.timeout.connect(self.update_preview)

        # Display temperature
        self.timer_temp = QTimer()
        self.timer_temp.timeout.connect(self.display_temp)
        self.timer_temp.start(1000)

        # Display acquisition status
        self.timer_acquisition = QTimer()
        self.timer_acquisition.timeout.connect(self.display_acquisition_state)

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
            label = f"{value} microseconds"
            self.vsspeed_input.addItem(label)

            # store index
            self.vsspeed_input.setItemData(self.vsspeed_input.count()-1,idx,Qt.UserRole+1)

    def on_read_mode_changed(self, mode):
        widget = self.read_mode_widgets[mode]
        self.read_mode_stack.setCurrentWidget(widget)

        self.read_mode_stack.setFixedHeight(widget.sizeHint().height())

    def on_acquisition_mode_changed(self,mode):
        widget = self.acquisition_mode_widgets[mode]
        self.acquisition_mode_stack.setCurrentWidget(widget)

        self.acquisition_mode_stack.setFixedHeight(widget.sizeHint().height())

    # def display_used_params(self, roi:Dict[str,str], shutter:Dict[str,str], read_mode:str):
    #     """Display used parameters in the GUI fields."""

    #     self.roi_hstart_input.setText(roi["hstart"])
    #     self.roi_hend_input.setText(roi["hend"])
    #     self.roi_vstart_input.setText(roi["vstart"])
    #     self.roi_vend_input.setText(roi["vend"])
    #     self.roi_hbin_input.setText(roi["hbin"])
    #     self.roi_vbin_input.setText(roi["vbin"])

    #     self.shutter_mode_input.setCurrentText(shutter["mode"])
    #     self.tll_mode_input.setCurrentText(shutter["tll_mode"])
    #     self.shutter_open_time_input.setText(shutter["open_time"])
    #     self.shutter_close_time_input.setText(shutter["close_time"])

    #     self.read_mode_input.setCurrentText(read_mode)


    def display_msg(self, message:str):
        self.status.showMessage(message, 5000)  # display for 5 seconds

    def display_temp(self):
        temp,status = self.controller.get_temp()
        self.temp.setText(f"Temp: {temp} °C | {status}")

    def display_shutter_state(self, state:str):
        self.shutter_current_state.setText(f"Shutter State: {state}")

    def display_acquisition_state(self):
        in_progress,state = self.controller.display_acquisition_state()
        num_frames, num_acc = state
        self.acquisition_state.setText(f"Acquisition in progress: {in_progress} (frames done: {num_frames}, acc_done: {num_acc})")

    def update_image_preview_overlay(self,roi,show_roi,show_grid):
        if self.read_mode_input.currentText() != "image":
            self.preview.overlay_enabled = False
            self.preview.set_roi(None)
            return
        
        self.preview.overlay_enabled = True
        self.preview.show_roi = show_roi
        self.preview.show_grid = show_grid
        self.preview.set_roi(roi)





    # ===== Functions ======

    # ==== Camera methods =====

    def connect_cam(self):
        self.controller.connect_cam()
        self.timer_acquisition.start(500)
        # self.disable_buttons()
        # self.worker = CoolingWorker(self.controller,target_temp=-80)
        # self.worker.finished.connect(self.enable_buttons)
        # self.worker.start()

    def disconnect_cam(self):
        self.timer_acquisition.stop()
        self.controller.disconnect_cam()

    def disable_buttons(self):
        for b in [self.btn_connect_cam, self.btn_live, self.btn_stop, self.btn_acquire]:
            b.setEnabled(False)
    
    def enable_buttons(self):
        for b in [self.btn_connect_cam, self.btn_live, self.btn_stop, self.btn_acquire]:
            b.setEnabled(True)

    def apply_roi_preset(self, text):
        try:
            full_w, full_h = self.controller.camera.detect_cam_size()
        except:
            return  # camera not connected

        if text == "Custom":
            return

        roi_w, roi_h = map(int, text.split("x"))

        # Center ROI
        hstart = (full_w - roi_w) // 2
        vstart = (full_h - roi_h) // 2
        hend = hstart + roi_w
        vend = vstart + roi_h

        self.roi_hstart_input.setText(str(hstart))
        self.roi_hend_input.setText(str(hend))
        self.roi_vstart_input.setText(str(vstart))
        self.roi_vend_input.setText(str(vend))


    def apply_bin_preset(self, text):
        if text == "Custom":
            return

        hbin, vbin = map(int, text.split("x"))
        self.roi_hbin_input.setText(str(hbin))
        self.roi_vbin_input.setText(str(vbin))


    def set_settings(self):
        # roi = {
        #     "hstart": self.roi_hstart_input.text(),
        #     "hend": self.roi_hend_input.text(),
        #     "vstart": self.roi_vstart_input.text(),
        #     "vend": self.roi_vend_input.text(),
        #     "hbin": self.roi_hbin_input.text(),
        #     "vbin": self.roi_vbin_input.text()
        # }

        shutter = {
            "mode": self.shutter_mode_input.currentText(),
            "tll_mode": self.tll_mode_input.currentText(),
            "open_time": self.shutter_open_time_input.text(),
            "close_time": self.shutter_close_time_input.text()
        }

        active_read_mode_widget = self.read_mode_stack.currentWidget()
        read_mode_params = active_read_mode_widget.get_params()

        active_acquisition_mode_widget = self.acquisition_mode_stack.currentWidget()
        acquisition_mode_params = active_acquisition_mode_widget.get_params()

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

        self.controller.apply_cam_settings(shutter, read_mode_params, acquisition_mode_params, trigger_mode, exposure, amp, vsspeed, emccd_gain)

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
        self.preview.set_frame((frame8,h,w))
        # qimg = QImage(frame8.data, w, h, w, QImage.Format_Grayscale8)
        # pix = QPixmap.fromImage(qimg)
        # self.preview.setPixmap(pix.scaled(
        #     self.preview.width(),
        #     self.preview.height()
        # ))
    
    # use for preview of acquisition
    def acquisition_preview(self):
        frame = self.controller.acquire_single()
        # frame = self.controller.start_acquisition()
        if frame is None:
            return
        self.display_image(frame)

    def start_acquisition(self):
        # frame = self.controller.acquire_single()
        self.controller.start_acquisition()

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

    def select_save_frame_path(self):
        folder = QFileDialog.getExistingDirectory(self,"Select folder to save frames","",QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks)
        if folder:
            self.save_frame_path_label.setText(f"Frames saved to: {folder}")
            self.controller.set_save_frame_path(Path(folder))

    # ==== VISUALS ====
    def _separator(self):
        sep = QWidget()
        sep.setFixedWidth(1)
        sep.setObjectName("statusSeparator")
        return sep

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
            # try:
            #     self.controller.disconnect_spec()
            # except Exception as e:
            #     print("Spectrometer disconnect failed:", e)

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
            background-color: #3c3f41;
            color: white;
            font-size: 13px;
        }

        QWidget#sectionContent {
            background-color: #323232;
            border: 1px solid #444444;
            border-radius: 4px;
        }

        QLineEdit, QComboBox, QSpinBox {
            background-color: #2b2b2b;
            border: 1px solid #555555;
            border-radius: 4px;
            padding: 4px
        }

        QLabel {
            border: none;
            background: transparent;
        }

        QCheckBox {
            spacing: 6px;
        }

        QSplitter::handle {
            background-color: #555555;
        }

        QSplitter::handle:hover {
            background-color: #777777;
        }

        QWidget#statusBarContainer {
            background-color: #2b2b2b;
            border-top: 1px solid #444444;
        }

        QWidget#statusSeparator {
            background-color: #555555;
            margin-left: 5px;
            margin-right: 5px;
        }

        QWidget#rulerContainer {
            background-color: #555555;
        }

    """)

    window = MainWindow()
    window.move(0,0)
    window.showMaximized()
    # QTimer.singleShot(0,lambda: self.on_read_mode_changed(self.read_mode_input.currentText()))  # sinlge shot to update ui selections on loading
    # QTimer.singleShot(0,lambda: self.on_acquisition_mode_changed(self.acquisition_mode_input.currentText()))  # sinlge shot to update ui selections on loading
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()

