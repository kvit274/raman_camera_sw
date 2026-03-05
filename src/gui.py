import atexit
import traceback
from pathlib import Path
import numpy as np
import sys
from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QStackedWidget, QLineEdit, QPushButton, QFileDialog, QLabel, QComboBox, QMessageBox, QScrollArea, QGroupBox, QSizePolicy, QSplitter, QTabWidget
from PyQt5.QtGui import QIntValidator, QDoubleValidator, QImage, QPixmap
from PyQt5.QtCore import pyqtSignal, QTimer, QThread, Qt
import pyqtgraph as pg
import os
from controller import RamanCameraController
from widgets import MultiTrackWidget, SingleTrackWidget, FVBWidget, ImageWidget, RandomTrackWidget, SingleWidget, AccumWidget, KineticWidget, FastKineticWidget, ContinuousWidget, CollapsibleSection, QNoScrollComboBox, PreviewWidget, RulerContainer, TemperaturePopUp
from typing import Dict

class MainWindow(QMainWindow):

    def __init__(self):

        super().__init__()
        self.setWindowTitle("Raman Camera GUI")
        self.status = self.statusBar()
        self.temp_popup = TemperaturePopUp(self)
        self.status.setSizeGripEnabled(False)

        self.acq_worker = None

        # attach controller
        self.controller = RamanCameraController(view=self)

        # Camera preview and controls
        self.preview = PreviewWidget()
        self.preview.setFixedSize(1024,256)  # change to camera max width/height
        self.preview_container = RulerContainer(self.preview)
        self.btn_connect_cam = QPushButton("Connect Camera")
        self.btn_live = QPushButton("Start Live")
        self.btn_stop = QPushButton("Stop Live")
        self.btn_preview = QPushButton("Preview")
        self.btn_acquire = QPushButton("Start Acquisition")
        self.btn_stop_acq = QPushButton("Stop Acquisition")
        self.btn_disconnect_cam = QPushButton("Disconnect Camera")
        self.temp = QLabel("Temp: -- °C")
        self.btn_set_temp = QPushButton("Set to")
        self.btn_set_temp.setFixedWidth(70)

        # Save path directories
        self.save_frame_path_button = QPushButton("Save frames to:")
        self.save_frame_path_label = QLabel("Frames saved to: ./data")

        # Camera settings


        # Shutter controls
        self.shutter_mode_input = QNoScrollComboBox()
        self.shutter_mode_input.addItems(["auto", "open", "closed"])
        self.ttl_mode_input = QNoScrollComboBox()
        self.ttl_mode_input.addItems(["0", "1"]) # THESE NEEDS TO BE CHANGED TO: TTL_low TTL_high for nicer ux
        self.shutter_open_time_input = QLineEdit()
        self.shutter_open_time_input.setPlaceholderText("Shutter Open Time (ms)")
        self.shutter_open_time_input.setValidator(QDoubleValidator())
        self.shutter_close_time_input = QLineEdit()
        self.shutter_close_time_input.setPlaceholderText("Shutter Close Time (ms)")
        self.shutter_close_time_input.setValidator(QDoubleValidator())
        self.shutter_current_state = QLabel("Shutter State: --")

        # Read mode
        self.read_mode_input = QNoScrollComboBox()
        self.read_mode_input.addItems(["fvb", "image", "single_track", "multi_track", "random_track"])
        self.read_mode_input.setCurrentText("image")
        self.read_mode_stack = QStackedWidget()
        self.read_mode_stack.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        self.image_widget = ImageWidget()
        self.image_widget.roi_visual_changed.connect(self.update_image_preview_overlay)  # connect to draw on preview
        self.read_mode_widgets = {
            "fvb": FVBWidget(),
            "image": self.image_widget,
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

        # Result mode (avg or sum of frames)
        self.result_mode_input = QNoScrollComboBox()
        self.result_mode_input.addItems(["sum", "avg"])

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
        

        self.left_container = QWidget()
        self.left_layout = QVBoxLayout(self.left_container)
        self.left_layout.setSpacing(10)
        self.left_layout.setContentsMargins(10, 10, 10, 10)

        self.left_container.setStyleSheet("""
            QWidget {
                background-color: #2b2b2b;
            }
        """)

        # -------- Camera Control (NOT collapsible) --------
        self.control_layout = QVBoxLayout()

        self.control_layout.addWidget(QLabel("Camera Control"))
        self.control_layout.addWidget(self.btn_connect_cam)
        self.control_layout.addWidget(self.btn_live)
        self.control_layout.addWidget(self.btn_stop)
        self.control_layout.addWidget(self.btn_preview)
        self.control_layout.addWidget(self.btn_acquire)
        self.control_layout.addWidget(self.btn_stop_acq)
        self.control_layout.addWidget(self.btn_disconnect_cam)
        self.control_layout.addWidget(self.save_frame_path_button)
        self.control_layout.addWidget(self.save_frame_path_label)

        self.left_layout.addLayout(self.control_layout)

        # -------- Shutter --------
        self.section_shutter = CollapsibleSection("Shutter")
        self.shutter_layout = QVBoxLayout()

        self.shutter_layout.addWidget(QLabel("Mode"))
        self.shutter_layout.addWidget(self.shutter_mode_input)

        self.shutter_layout.addWidget(QLabel("TTL Mode"))
        self.shutter_layout.addWidget(self.ttl_mode_input)

        self.shutter_layout.addWidget(QLabel("Open Time (ms)"))
        self.shutter_layout.addWidget(self.shutter_open_time_input)

        self.shutter_layout.addWidget(QLabel("Close Time (ms)"))
        self.shutter_layout.addWidget(self.shutter_close_time_input)

        self.section_shutter.setContentLayout(self.shutter_layout)
        self.left_layout.addWidget(self.section_shutter)

        # -------- Read Mode --------
        self.section_read = CollapsibleSection("Read Mode")
        self.read_layout = QVBoxLayout()

        self.read_layout.addWidget(self.read_mode_input)
        self.read_layout.addWidget(self.read_mode_stack)

        self.section_read.setContentLayout(self.read_layout)
        self.left_layout.addWidget(self.section_read)

        # -------- Acquisition --------
        self.section_acq = CollapsibleSection("Acquisition")
        self.acq_layout = QVBoxLayout()

        self.acq_layout.addWidget(QLabel("Acquisition Mode"))
        self.acq_layout.addWidget(self.acquisition_mode_input)

        self.acq_layout.addWidget(self.acquisition_mode_stack)

        self.acq_layout.addWidget(QLabel("Trigger Mode"))
        self.acq_layout.addWidget(self.trigger_mode_input)

        self.acq_layout.addWidget(QLabel("Exposure (s)"))
        self.acq_layout.addWidget(self.exposure_input)

        self.acq_layout.addWidget(QLabel("Result Processing"))
        self.acq_layout.addWidget(self.result_mode_input)

        self.section_acq.setContentLayout(self.acq_layout)
        self.left_layout.addWidget(self.section_acq)

        # -------- Amplifier --------
        self.section_amp = CollapsibleSection("Amplifier / Speed")
        self.amp_layout = QVBoxLayout()

        self.amp_layout.addWidget(QLabel("Amp Mode"))
        self.amp_layout.addWidget(self.amp_mode_input)

        self.amp_layout.addWidget(QLabel("Vertical Shift Speed"))
        self.amp_layout.addWidget(self.vsspeed_input)

        self.amp_layout.addWidget(QLabel("EMCCD Gain"))
        self.amp_layout.addWidget(self.emccd_gain_input)

        self.section_amp.setContentLayout(self.amp_layout)
        self.left_layout.addWidget(self.section_amp)

        self.left_layout.addWidget(self.set_settings_button)
        self.left_layout.addStretch()

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setWidget(self.left_container)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        # ============================================================
        # ---- RIGHT SIDE TABS ----
        # ============================================================

        self.right_tabs = QTabWidget()
        self.right_tabs.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Expanding)

        # ---- PREVIEW ----
        
        self.preview_tab = QWidget()
        self.preview_layout = QVBoxLayout(self.preview_tab)
        self.preview_layout.setContentsMargins(0, 0, 0, 0)

        self.preview_tab.setStyleSheet("""
            QWidget {
                background-color: #3c3f41;
                border-left: 1px solid #555555;
            }
        """)

        self.preview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.preview_layout.addWidget(self.preview_container, alignment = Qt.AlignRight)

        self.right_tabs.addTab(self.preview_tab, "Preview")

        # ---- SPECTROGRAM ----

        self.calibration_plot = pg.PlotWidget()
        self.calibration_plot.setLabel('left', 'Intensity')
        self.calibration_plot.setLabel('bottom', 'Pixels')

        cal_vb = self.calibration_plot.getViewBox()
        cal_vb.setMouseEnabled(x=False,y=False)

        self.calibration_tab = QWidget()
        self.cal_layout = QVBoxLayout(self.calibration_tab)
        self.cal_layout.setContentsMargins(0,0,0,0)
        self.cal_layout.addWidget(self.calibration_plot)

        self.right_tabs.addTab(self.calibration_tab, "Calibration")

        # ============================================================
        # SPLITTER (DRAGGABLE)
        # ============================================================

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.addWidget(self.scroll)
        self.splitter.addWidget(self.right_tabs)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Expanding)

        # ============================================================
        # STATUS BAR (BOTTOM STRIP)
        # ============================================================

        self.status_container = QWidget()
        self.status_container.setObjectName("statusBarContainer")
        self.status_layout = QHBoxLayout(self.status_container)
        self.status_layout.setContentsMargins(10, 5, 10, 5)

        self.status.setStyleSheet("color: red;")

        self.status_layout.addWidget(self.temp)
        self.status_layout.insertWidget(1,self.btn_set_temp)
        self.status_layout.addWidget(self._separator())
        self.status_layout.addWidget(self.shutter_current_state)
        self.status_layout.addWidget(self._separator())
        self.status_layout.addWidget(self.acquisition_state)
        self.status_layout.addWidget(self._separator())
        self.status_layout.addStretch()
        self.status_layout.addWidget(self.status)

        self.status_container.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Fixed)

        # ============================================================
        # FINAL MAIN LAYOUT
        # ============================================================

        self.main_layout = QVBoxLayout()
        self.main_layout.addWidget(self.splitter,1)
        self.main_layout.addWidget(self.status_container)

        self.central = QWidget()
        self.central.setLayout(self.main_layout)
        self.setCentralWidget(self.central)


        # Connect buttons to controller cam
        self.btn_set_temp.clicked.connect(self.show_temp_popup)
        self.temp_popup.apply_btn.clicked.connect(self.apply_temperature)
        self.btn_connect_cam.clicked.connect(self.connect_cam)
        self.btn_live.clicked.connect(self.start_live)
        self.btn_stop.clicked.connect(self.stop_live)
        self.btn_preview.clicked.connect(self.show_preview)
        self.btn_acquire.clicked.connect(self.start_acquisition)
        self.btn_stop_acq.clicked.connect(self.stop_acquisition)
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


    def show_temp_popup(self):
        if not self.controller.camera.cam:
            return
        
        btn_pos = self.btn_set_temp.mapToGlobal(self.btn_set_temp.rect().topLeft())
        self.temp_popup.move(btn_pos.x(), btn_pos.y() - self.temp_popup.height())
        self.temp_popup.show()


    # ===== Functions ======

    # ==== Camera methods =====

    def connect_cam(self):
        self.controller.connect_cam()
        self.timer_acquisition.start(500)

    def disconnect_cam(self):
        self.timer_acquisition.stop()
        self.controller.disconnect_cam()

    def disable_buttons(self):
        for b in [self.btn_connect_cam, self.btn_live, self.btn_stop, self.btn_preview, self.btn_acquire, self.btn_stop_acq]:
            b.setEnabled(False)
    
    def disable_acq_buttons(self):
        for b in [self.btn_acquire, self.btn_connect_cam, self.btn_live, self.btn_stop, self.btn_preview, self.btn_acquire, self.btn_set_temp,self.set_settings_button]:
            b.setEnabled(False)
    
    def enable_buttons(self):
        for b in [self.btn_connect_cam, self.btn_live, self.btn_stop, self.btn_preview, self.btn_acquire, self.btn_stop_acq, self.btn_set_temp, self.set_settings_button]:
            b.setEnabled(True)

    def apply_temperature(self):
        target_temp = self.temp_popup.get_value()

        try:
            self.controller.cool_cam(target_temp)
        except Exception as e:
            self.display_msg(str(e))
        
        self.temp_popup.hide()

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

        shutter = {
            "mode": self.shutter_mode_input.currentText(),
            "ttl_mode": self.ttl_mode_input.currentText(),
            "open_time": self.shutter_open_time_input.text(),
            "close_time": self.shutter_close_time_input.text()
        }

        active_read_mode_widget = self.read_mode_stack.currentWidget()
        read_mode_params = active_read_mode_widget.get_params()

        active_acquisition_mode_widget = self.acquisition_mode_stack.currentWidget()
        acquisition_mode_params = active_acquisition_mode_widget.get_params()

        trigger_mode = self.trigger_mode_input.currentText()

        exposure = self.exposure_input.text()

        result_mode = self.result_mode_input.currentText()

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

        self.controller.apply_cam_settings(shutter, read_mode_params, acquisition_mode_params, trigger_mode, exposure, result_mode, amp, vsspeed, emccd_gain)

    def show_preview(self):
        frame = self.controller.single_preview()
        # if frame:
        self.display_image(frame)

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
        self.display_image(frame)

    def display_image(self,frame):
        if frame is None:
            return
        frame8, h, w = self.controller.adjust_frame(frame)
        self.preview.set_frame((frame8,h,w))

    def handle_acq_result(self, frame, spectrum):
        self.show_calibration_result(frame, spectrum)

    def show_calibration_result(self, frame, spectrum):
        # Switch to calibration tab
        self.right_tabs.setCurrentIndex(1)

        # Plot spectrum
        self.calibration_plot.clear()

        pixels = np.arange(len(spectrum))

        self.calibration_plot.plot(pixels,spectrum,pen="y")

        self.calibration_plot.enableAutoRange(x=True,y=True)
        
    
    # use for preview of acquisition
    def acquisition_preview(self):
        frame = self.controller.acquire_single()
        self.display_image(frame)

    def start_acquisition(self):
        # self.controller.start_acquisition()
        self.acq_worker = AcquisitionWorker(self.controller)
        self.acq_worker.finished.connect(self.handle_acq_result)
        # self.acq_worker.camera_lost.connect(self.handle_camera_loss)
        self.acq_worker.start()

    def stop_acquisition(self):
        if self.controller.acquisition_in_progress():
            if self.acq_worker and self.acq_worker.isRunning():
                self.acq_worker.stop()
                self.acq_worker.wait()

            self.controller.stop_acquisition()
        return

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

        except Exception as e:
            print("[GUI] Unexpected error during closeEvent:", e)

        event.accept()

    def handle_camera_loss(self):

        self.display_msg("Camera connection lost!")
        self.disable_buttons()

        if hasattr(self.controller, "acq_worker") and self.controller.acq_worker.isRunning():
            self.acq_worker.terminate()
            self.acq_worker.wait()

        if hasattr(self.controller, "cooling_worker") and self.controller.cooling_worker.isRunning():
            self.controller.camera.cancel = True
            self.controller.cooling_worker.wait()

        # stop live timer
        self.stop_live_timer()

        # reset controller state
        try:
            self.controller.disconnect_cam()
        except:
            pass
        
        self.temp.setText("Temp: -- °C")
        self.shutter_current_state.setText("Shutter State: --")
        self.acquisition_state.setText("Acquisition in progress: False")


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

        QTabWidget::pane {
            border: 1px solid #444444;
            background: #3c3f41;
        }

        QTabBar::tab {
            background: #2b2b2b;
            color: white;
            border: 1px solid #444444;
            padding: 5px;
            min-width: 120px;
        }

        QTabBar::tab:selected {
            background: #444444;
            color: #00ffcc;
        }

        QTabBar::tab:hover {
            background: #555555;
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

