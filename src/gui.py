import atexit
import traceback
from pathlib import Path
import numpy as np
import sys
from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QStackedWidget, QLineEdit, QPushButton, QFileDialog, QLabel, QComboBox, QMessageBox, QScrollArea, QGroupBox, QSizePolicy, QSplitter, QTabWidget, QCheckBox
from PyQt5.QtGui import QIntValidator, QDoubleValidator, QImage, QPixmap
from PyQt5.QtCore import pyqtSignal, QTimer, QThread, Qt
import pyqtgraph as pg
import os
from controller import RamanCameraController
from widgets import MultiTrackWidget, SingleTrackWidget, FVBWidget, ImageWidget, RandomTrackWidget, SingleWidget, AccumWidget, KineticWidget, FastKineticWidget, ContinuousWidget, CollapsibleSection, QNoScrollComboBox, PreviewWidget, RulerContainer, TemperaturePopUp
from typing import Dict
from fsm import CameraState

class MainWindow(QMainWindow):
    """
    Main application window for the Raman Camera Acquisition Software.
 
    Owns the RamanCameraController and wires together all UI widgets, layouts,
    and signal/slot connections.  The window is divided into:
    - A top control bar with camera lifecycle buttons (connect, live, acquire, ...).
    - A left scrollable panel with collapsible settings sections (shutter,
      read mode, acquisition mode, amplifier/speed) and file controls.
    - A right tabbed area with a live camera Preview tab and a Spectrogram tab
      that supports multiple overlaid curves.
    - A bottom status bar showing temperature, shutter state, and status messages.
    """

    def __init__(self):
        """
        Build all widgets, assemble layouts, connect signals/slots, and configure
        the initial disabled-button state that is correct before a camera connects.
        """

        super().__init__()
        self.setWindowTitle("Raman Camera GUI")
        self.status = self.statusBar()
        self.temp_popup = TemperaturePopUp(self)
        self.status.setSizeGripEnabled(False)

        self.controller = RamanCameraController()
        self.controller.error_signal.connect(self.display_msg)
        self.controller.camera_lost_signal.connect(self.handle_camera_loss)
        self.controller.message_signal.connect(self.display_msg)
        self.controller.shutter_state_changed.connect(self.display_shutter_state)
        self.controller.amp_modes_loaded.connect(self.load_amp_modes)
        self.controller.vsspeeds_loaded.connect(self.load_vsspeeds)
        self.controller.ui_state_changed.connect(self.apply_state_to_ui)
        self.controller.live_frame_ready.connect(self.handle_live_results)
        self.controller.live_finished.connect(lambda: self.display_msg("Live mode stopped.", success=True))
        self.controller.acquisition_finished.connect(self.handle_acq_result)

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
        self.btn_save_frame_path = QPushButton("Save data to:")
        self.save_frame_path_label = QLabel("Data saved to: ./data")
        self.save_frame_path_label.setWordWrap(True)


        self.filename_label = QLabel("Filename:")
        self.filename_input = QLineEdit()
        self.filename_input.setPlaceholderText("Filename (without extension)")
        # self.filename_input.setText("spectrum")

        self.file_index_label = QLabel("index:")
        self.file_index_input = QLineEdit()
        self.file_index_input.setPlaceholderText("idx")
        self.file_index_input.setValidator(QIntValidator())
        self.file_index_input.setText("1")
        # self.file_index_input.setFixedWidth(60)

        self.save_frame_path_layout = QHBoxLayout()
        self.save_frame_path_layout.addWidget(self.filename_label)
        self.save_frame_path_layout.addWidget(self.filename_input)
        self.save_frame_path_layout.addWidget(self.file_index_label)
        self.save_frame_path_layout.addWidget(self.file_index_input)

        self.btn_open_npz = QPushButton("Load experiment")

        # Camera settings

        # Shutter controls
        self.shutter_mode_input = QNoScrollComboBox()
        self.shutter_mode_input.addItems(["auto", "open", "closed"])
        self.ttl_mode_input = QNoScrollComboBox()
        self.ttl_mode_input.addItems(["0", "1"])
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
        self.image_widget.roi_visual_changed.connect(self.update_image_preview_overlay)
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

        # Amp
        self.amp_mode_input = QNoScrollComboBox()
        self.amp_mode_input.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.amp_mode_input.setMinimumContentsLength(1)

        # Vsspeed
        self.vsspeed_input  = QNoScrollComboBox()

        # EMCCD gain
        self.emccd_gain_input = QLineEdit()
        self.emccd_gain_input.setPlaceholderText("EMCCD gain, do not exceed 300")
        self.emccd_gain_input.setValidator(QDoubleValidator())
        self.emccd_advanced_checkbox = QCheckBox("Advanced EMCCD (>300)")

        self.btn_set_settings = QPushButton("Apply Settings")

        # -------- LAYOUT -------

        # -------- LEFT PANEL  --------
        
        self.left_container = QWidget()
        self.left_layout = QVBoxLayout(self.left_container)
        self.left_layout.setSpacing(10)
        self.left_layout.setContentsMargins(10, 10, 10, 10)
        self.left_container.setObjectName("leftPanel")
        self.left_container.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)

        # -------- Top camera controls row --------
        self.top_controls_container = QWidget()
        self.top_controls_layout = QHBoxLayout(self.top_controls_container)
        self.top_controls_layout.setContentsMargins(10, 10, 10, 0)
        self.top_controls_layout.setSpacing(8)
        self.top_controls_layout.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self.top_controls_layout.addStretch()
        self.top_controls_layout.addWidget(self.btn_connect_cam)
        self.top_controls_layout.addWidget(self.btn_disconnect_cam)
        self.top_controls_layout.addWidget(self.btn_live)
        self.top_controls_layout.addWidget(self.btn_stop)
        self.top_controls_layout.addWidget(self.btn_preview)
        self.top_controls_layout.addWidget(self.btn_acquire)
        self.top_controls_layout.addWidget(self.btn_stop_acq)

        # -------- File / save controls --------
        self.file_controls_layout = QVBoxLayout()
        self.file_controls_layout.addWidget(self.btn_save_frame_path)
        self.file_controls_layout.addWidget(self.save_frame_path_label)
        self.file_controls_layout.addLayout(self.save_frame_path_layout)
        self.file_controls_layout.addWidget(self.btn_open_npz)
        self.left_layout.addLayout(self.file_controls_layout)

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
        self.amp_layout.addWidget(self.emccd_advanced_checkbox)
        self.section_amp.setContentLayout(self.amp_layout)
        self.left_layout.addWidget(self.section_amp)
        self.left_layout.addWidget(self.btn_set_settings)
        self.left_layout.addStretch()
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setWidget(self.left_container)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setSizePolicy(QSizePolicy.Preferred,QSizePolicy.Expanding)

        # ---- RIGHT SIDE TABS ----

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

        # ---- SPECTROGRAMS ----

        self.calibration_tab = QWidget()
        self.cal_layout = QVBoxLayout(self.calibration_tab)
        self.cal_layout.setContentsMargins(0,0,0,0)

        self.calibration_tabs = QTabWidget()
        self.calibration_tabs.setTabsClosable(True)
        self.calibration_tabs.tabCloseRequested.connect(lambda i: self.close_calibration_tab(i))

        self.btn_new_spectrum_tab = QPushButton("+")
        self.btn_new_spectrum_tab.setFixedWidth(30)
        self.btn_new_spectrum_tab.clicked.connect(lambda: self.create_empty_spectrum_tab())

        self.calibration_tabs.setCornerWidget(self.btn_new_spectrum_tab, Qt.TopRightCorner)
        self.cal_layout.addWidget(self.calibration_tabs)
        self.right_tabs.addTab(self.calibration_tab, "Spectrogram")

        # init common plots
        self.live_plot = self.create_spectrum_plot("Live")
        self.live_tab_index = self.calibration_tabs.addTab(self.live_plot, "Live")
        self.pending_filename = None
        self.plot_pens = [
            pg.mkPen("y", width=1.8),
            pg.mkPen("c", width=1.8),
            pg.mkPen("m", width=1.8),
            pg.mkPen("g", width=1.8),
            pg.mkPen("w", width=1.8),
        ]
        self.orange_pen = pg.mkPen((255,165,9),width=1.8)
        self.next_plot_pen_idx = 0

        # ---- SPLITTER ----

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.addWidget(self.scroll)
        self.splitter.addWidget(self.right_tabs)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Expanding)
        self.status_container = QWidget()
        self.status_container.setObjectName("statusBarContainer")
        self.status_layout = QHBoxLayout(self.status_container)
        self.status_layout.setContentsMargins(10, 5, 10, 5)
        self.status.setStyleSheet("color: red;")
        self.status_layout.addWidget(self.temp)
        self.status_layout.insertWidget(1,self.btn_set_temp)
        self.status_layout.addWidget(self.separator())
        self.status_layout.addWidget(self.shutter_current_state)
        self.status_layout.addWidget(self.separator())
        self.status_layout.addWidget(self.separator())
        self.status_layout.addStretch()
        self.status_layout.addWidget(self.status)
        self.status_container.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Fixed)

        # ---- MAIN LAYOUT ----

        self.main_layout = QVBoxLayout()
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(6)
        self.main_layout.addWidget(self.top_controls_container, 0)
        self.main_layout.addWidget(self.splitter, 1)
        self.main_layout.addWidget(self.status_container, 0)
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
        self.btn_set_settings.clicked.connect(self.set_settings)
        self.read_mode_input.currentTextChanged.connect(self.on_read_mode_changed)
        self.on_read_mode_changed("image")
        self.acquisition_mode_input.currentTextChanged.connect(self.on_acquisition_mode_changed)
        self.on_acquisition_mode_changed("single")
        self.btn_save_frame_path.clicked.connect(self.select_save_frame_path)
        self.btn_open_npz.clicked.connect(self.open_npz)
        self.preview.roi_changed.connect(self.update_roi_inputs)
        self.preview.bit_shift_region_changed.connect(self.update_bit_shift_inputs)

        # Display temperature
        self.timer_temp = QTimer(self)
        self.timer_temp.timeout.connect(self.display_temp)

        # SETTINGS MAP
        self.settings_map = {
            "exposure": self.exposure_input,
            "trigger_mode": self.trigger_mode_input,
            ("shutter","mode"): self.shutter_mode_input,
            ("shutter","ttl_mode"): self.ttl_mode_input,
            ("shutter","open_time"): self.shutter_open_time_input,
            ("shutter","close_time"): self.shutter_close_time_input,
            ("read_mode","hstart"): self.image_widget.roi_hstart_input,
            ("read_mode","hend"): self.image_widget.roi_hend_input,
            ("read_mode","vstart"): self.image_widget.roi_vstart_input,
            ("read_mode","vend"): self.image_widget.roi_vend_input,
            ("read_mode","hbin"): self.image_widget.roi_hbin_input,
            ("read_mode","vbin"): self.image_widget.roi_vbin_input,
        }

        # disable buttons before camera connection
        for b in [self.btn_live, self.btn_disconnect_cam, self.btn_stop, self.btn_preview, self.btn_acquire, self.btn_stop_acq, self.btn_set_temp,self.btn_set_settings]:
            b.setEnabled(False)

    def apply_state_to_ui(self,state):
        """
        Enable or disable every camera-control button according to the new FSM state.
 
        Called automatically whenever CameraStateMachine emits state_changed.
        Each state defines a precise set of allowed actions; all other buttons are
        disabled to prevent the user from issuing invalid commands.
 
        Args:
            state: CameraState enum value received from the controller FSM.
        """
        buttons = {
            "connect": self.btn_connect_cam,
            "disconnect": self.btn_disconnect_cam,
            "live": self.btn_live,
            "stop_live": self.btn_stop,
            "preview": self.btn_preview,
            "acquire": self.btn_acquire,
            "stop_acq": self.btn_stop_acq,
            "set_temp": self.btn_set_temp,
            "apply_settings": self.btn_set_settings,
            "open_npz": self.btn_open_npz,
        }

        if state == CameraState.DISCONNECTED:
            buttons["connect"].setEnabled(True)
            buttons["disconnect"].setEnabled(False)
            buttons["live"].setEnabled(False)
            buttons["stop_live"].setEnabled(False)
            buttons["preview"].setEnabled(False)
            buttons["acquire"].setEnabled(False)
            buttons["stop_acq"].setEnabled(False)
            buttons["set_temp"].setEnabled(False)
            buttons["apply_settings"].setEnabled(False)
            buttons["open_npz"].setEnabled(True)

        elif state == CameraState.CONNECTED:
            buttons["connect"].setEnabled(False)
            buttons["disconnect"].setEnabled(True)
            buttons["live"].setEnabled(False)
            buttons["stop_live"].setEnabled(False)
            buttons["preview"].setEnabled(False)
            buttons["acquire"].setEnabled(False)
            buttons["stop_acq"].setEnabled(False)
            buttons["set_temp"].setEnabled(True)
            buttons["apply_settings"].setEnabled(False)
            buttons["open_npz"].setEnabled(True)

        elif state == CameraState.COOLING:
            buttons["connect"].setEnabled(False)
            buttons["disconnect"].setEnabled(True)
            buttons["live"].setEnabled(False)
            buttons["stop_live"].setEnabled(False)
            buttons["preview"].setEnabled(False)
            buttons["acquire"].setEnabled(False)
            buttons["stop_acq"].setEnabled(False)
            buttons["set_temp"].setEnabled(True)
            buttons["apply_settings"].setEnabled(False)
            buttons["open_npz"].setEnabled(True)

        elif state == CameraState.READY:
            buttons["connect"].setEnabled(False)
            buttons["disconnect"].setEnabled(True)
            buttons["live"].setEnabled(True)
            buttons["stop_live"].setEnabled(False)
            buttons["preview"].setEnabled(True)
            buttons["acquire"].setEnabled(True)
            buttons["stop_acq"].setEnabled(False)
            buttons["set_temp"].setEnabled(True)
            buttons["apply_settings"].setEnabled(True)
            buttons["open_npz"].setEnabled(True)

        elif state == CameraState.LIVE:
            buttons["connect"].setEnabled(False)
            buttons["disconnect"].setEnabled(False)
            buttons["live"].setEnabled(False)
            buttons["stop_live"].setEnabled(True)
            buttons["preview"].setEnabled(False)
            buttons["acquire"].setEnabled(False)
            buttons["stop_acq"].setEnabled(False)
            buttons["set_temp"].setEnabled(False)
            buttons["apply_settings"].setEnabled(False)
            buttons["open_npz"].setEnabled(True)

        elif state == CameraState.ACQUIRING:
            buttons["connect"].setEnabled(False)
            buttons["disconnect"].setEnabled(False)
            buttons["live"].setEnabled(False)
            buttons["stop_live"].setEnabled(False)
            buttons["preview"].setEnabled(False)
            buttons["acquire"].setEnabled(False)
            buttons["stop_acq"].setEnabled(True)
            buttons["set_temp"].setEnabled(False)
            buttons["apply_settings"].setEnabled(False)
            buttons["open_npz"].setEnabled(True)

        elif state == CameraState.ERROR:
            buttons["connect"].setEnabled(True)
            buttons["disconnect"].setEnabled(False)
            buttons["live"].setEnabled(False)
            buttons["stop_live"].setEnabled(False)
            buttons["preview"].setEnabled(False)
            buttons["acquire"].setEnabled(False)
            buttons["stop_acq"].setEnabled(False)
            buttons["set_temp"].setEnabled(False)
            buttons["apply_settings"].setEnabled(False)
            buttons["open_npz"].setEnabled(True)

    def load_amp_modes(self,amp_modes):
        """
        Populate the amplifier mode combo box with human-readable labels.
 
        Called when the controller emits amp_modes_loaded after connecting.
        Each item stores the raw amp-mode object as Qt.UserRole data for
        retrieval by set_settings().
 
        Args:
            amp_modes: List of amp-mode objects from pylablib, each with
                       hsspeed_MHz and preamp_gain attributes.
        """
        self.amp_mode_input.clear()
        print(f"Amp modes: {len(amp_modes)}")

        for m in amp_modes:
            label = f"HSSpeed: {m.hsspeed_MHz:.2f} MHz | Preamp gain: {m.preamp_gain:.2f}x"
            self.amp_mode_input.addItem(label)
            self.amp_mode_input.setItemData(self.amp_mode_input.count()-1, m, Qt.UserRole)
        print(f"Items in combo: {self.amp_mode_input.count()}")

    def load_vsspeeds(self,vsspeeds):
        """
        Populate the vertical shift speed combo box with human-readable labels.
 
        Called when the controller emits vsspeeds_loaded after connecting.
        Each item stores its integer index as Qt.UserRole+1 data for retrieval
        by set_settings().
 
        Args:
            vsspeeds: List of VS-speed values in microseconds from pylablib.
        """
        self.vsspeed_input.clear()

        for idx,value in enumerate(vsspeeds):
            label = f"{value:.2f} µs"
            self.vsspeed_input.addItem(label)
            self.vsspeed_input.setItemData(self.vsspeed_input.count()-1,idx,Qt.UserRole+1)

    def load_settings_from_metadata(self, meta):
        """
        Restore GUI input fields from a metadata dict saved alongside an NPZ file.
 
        Uses self.settings_map to map flat and nested config keys to their
        corresponding widgets.  After simple scalar fields, handles the more
        complex read_mode and acquisition_mode sections separately, since these
        require updating mode-specific sub-widgets.
 
        Args:
            meta: Dict previously saved as the 'metadata' field in an NPZ file,
                  with the same structure as CameraConfig.to_dict().
        """

        for key, widget in self.settings_map.items():

            try:

                if isinstance(key, tuple):
                    section, subkey = key
                    value = meta.get(section, {}).get(subkey)
                else:
                    value = meta.get(key)

                if value is None:
                    continue

                value = str(value)

                if isinstance(widget, QLineEdit):
                    widget.setText(value)

                elif isinstance(widget, QComboBox):
                    widget.setCurrentText(value)

            except Exception as e:
                print(f"Failed loading {key}: {e}")

        if "read_mode" in meta:
            read = meta["read_mode"]
            mode = read.get("mode", "image")
            self.read_mode_input.setCurrentText(mode)

            if mode == "image":
                w = self.image_widget
                w.processing_mode_input.setCurrentText(str(read.get("processing_mode", "binning")))
                w.bit_shift_pixels_input.setText("" if read.get("bit_shift_pixels") is None else str(read.get("bit_shift_pixels", "")))
                w.bit_shift_vstart_input.setText("" if read.get("bit_shift_vstart") is None else str(read.get("bit_shift_vstart", "")))
                w.bit_shift_vend_input.setText("" if read.get("bit_shift_vend") is None else str(read.get("bit_shift_vend", "")))

        if "acquisition_mode" in meta:
            acq = meta["acquisition_mode"]
            mode = acq.get("mode", "single")
            self.acquisition_mode_input.setCurrentText(mode)

            if mode == "accum":
                w = self.acquisition_mode_widgets["accum"]
                w.num_acc_input.setText("" if acq.get("num_acc") is None else str(acq.get("num_acc", "")))
                w.cycle_time_acc_input.setText("" if acq.get("cycle_time_acc") is None else str(acq.get("cycle_time_acc", "")))
                w.result_mode_input.setCurrentText(str(acq.get("result_mode", "sum")))

            elif mode == "kinetic":
                w = self.acquisition_mode_widgets["kinetic"]
                w.num_cycle_input.setText("" if acq.get("num_cycle") is None else str(acq.get("num_cycle", "")))
                w.cycle_time_input.setText("" if acq.get("cycle_time") is None else str(acq.get("cycle_time", "")))
                w.num_acc_input.setText("" if acq.get("num_acc") is None else str(acq.get("num_acc", "")))
                w.cycle_time_acc_input.setText("" if acq.get("cycle_time_acc") is None else str(acq.get("cycle_time_acc", "")))
                w.num_prescan.setText("" if acq.get("num_prescan") is None else str(acq.get("num_prescan", "")))
                w.result_mode_input.setCurrentText(str(acq.get("result_mode", "sum")))

            elif mode == "fast_kinetic":
                w = self.acquisition_mode_widgets["fast_kinetic"]
                w.num_acc_input.setText("" if acq.get("num_acc") is None else str(acq.get("num_acc", "")))
                w.cycle_time_acc_input.setText("" if acq.get("cycle_time_acc") is None else str(acq.get("cycle_time_acc", "")))
                w.result_mode_input.setCurrentText(str(acq.get("result_mode", "sum")))

            elif mode == "cont":
                w = self.acquisition_mode_widgets["cont"]
                w.cycle_time.setText("" if acq.get("cycle_time") is None else str(acq.get("cycle_time", "")))

        print("Metadata loaded into GUI")
        print("Metadata loaded into GUI")

    def on_read_mode_changed(self, mode):
        """
        Switch the read-mode QStackedWidget to the widget matching the selected
        mode and resize the stack to fit it exactly.
 
        Args:
            mode: Read mode string selected in read_mode_input.
        """
        widget = self.read_mode_widgets[mode]
        self.read_mode_stack.setCurrentWidget(widget)

        self.read_mode_stack.setFixedHeight(widget.sizeHint().height())

    def on_acquisition_mode_changed(self,mode):
        """
        Switch the acquisition-mode QStackedWidget to the widget for the new mode
        and resize to fit.
 
        Args:
            mode: Acquisition mode string selected in acquisition_mode_input.
        """
        widget = self.acquisition_mode_widgets[mode]
        self.acquisition_mode_stack.setCurrentWidget(widget)

        self.acquisition_mode_stack.setFixedHeight(widget.sizeHint().height())

    # ---- STATUS / DISPLAY HELPERS ----

    def display_msg(self, message:str,success=False):
        """
        Show a message in the status bar for 5 seconds.
 
        Args:
            message: Text to display.
            success: If True the text is rendered green; otherwise red.
        """
        if success:
            self.status.setStyleSheet("color: #00ff00;")
        else:
            self.status.setStyleSheet("color: red;")

        self.status.showMessage(message, 5000)  # display for 5 seconds

    def display_temp(self):
        """
        Poll the current sensor temperature from the controller and update the
        temperature label in the status bar.  Called every second by timer_temp.
        """
        temp,status = self.controller.get_temp()
        self.temp.setText(f"Temp: {temp} °C | {status}")

    def display_shutter_state(self, state:str):
        """
        Update the shutter state label in the status bar.
 
        Args:
            state: Shutter state string (e.g. 'auto', 'open', 'closed').
        """
        self.shutter_current_state.setText(f"Shutter State: {state}")

    # ---- PREVIEW OVERLAY ----

    def update_image_preview_overlay(self,roi,show_roi,show_grid,bit_shift_vstart,bit_shift_vend,show_bit_shift_region):
        """
        Synchronise the ROI and bit-shift overlay on PreviewWidget with the
        current ImageWidget inputs.
 
        Connected to ImageWidget.roi_visual_changed.  Disables the overlay
        entirely when the current read mode is not 'image'.
 
        Args:
            roi:                  ROI tuple (hstart, hend, vstart, vend, hbin, vbin).
            show_roi:             Whether to draw the ROI rectangle.
            show_grid:            Whether to draw a binning grid (only in binning mode).
            bit_shift_vstart:     Top row of the bit-shift region.
            bit_shift_vend:       Bottom row of the bit-shift region.
            show_bit_shift_region: Whether to highlight the bit-shift region.
        """
        if self.read_mode_input.currentText() != "image":
            self.preview.overlay_enabled = False
            self.preview.set_roi(None)
            self.preview.set_bit_shift_region(None, None, False)
            return

        self.preview.overlay_enabled = True
        self.preview.show_roi = show_roi
        self.preview.show_grid = show_grid and (self.image_widget.processing_mode_input.currentText() == "binning")
        self.preview.set_roi(roi)
        self.preview.set_bit_shift_region(bit_shift_vstart,bit_shift_vend,show_bit_shift_region)

    def update_roi_inputs(self,roi):
        """
        Write ROI values dragged on PreviewWidget back into the ImageWidget inputs.
 
        Connected to PreviewWidget.roi_changed so dragging the overlay rectangle
        updates the numeric fields automatically.
 
        Args:
            roi: 6-tuple (hstart, hend, vstart, vend, hbin, vbin).
        """
        hstart, hend, vstart, vend, _, _ = roi
        w = self.image_widget
        w.roi_hstart_input.setText(str(hstart))
        w.roi_hend_input.setText(str(hend))
        w.roi_vstart_input.setText(str(vstart))
        w.roi_vend_input.setText(str(vend))

    def update_bit_shift_inputs(self, vstart, vend):
        """
        Write bit-shift region boundaries dragged on PreviewWidget into the
        ImageWidget inputs.
 
        Connected to PreviewWidget.bit_shift_region_changed.
 
        Args:
            vstart: Top detector row of the bit-shift region.
            vend:   Bottom detector row of the bit-shift region.
        """
        w = self.image_widget
        w.bit_shift_vstart_input.setText(str(vstart))
        w.bit_shift_vend_input.setText(str(vend))


    def show_temp_popup(self):
        """
        Display the TemperaturePopUp widget anchored above the Set Temperature
        button.  Does nothing if the camera is not alive.
        """
        if not self.controller.is_camera_alive():
            return
        
        btn_pos = self.btn_set_temp.mapToGlobal(self.btn_set_temp.rect().topLeft())
        self.temp_popup.move(btn_pos.x(), btn_pos.y() - self.temp_popup.height())
        self.temp_popup.show()

    def apply_temperature(self):
        """
        Read the target temperature from the popup and start a new cooling cycle.
 
        Hides the popup afterwards and shows any errors in the status bar.
        """
        target_temp = self.temp_popup.get_value()

        try:
            self.controller.cool_cam(target_temp)
        except Exception as e:
            self.display_msg(str(e))
        
        self.temp_popup.hide()

    # ---- Camera methods ----

    def connect_cam(self):
        """Connect to the camera and start the 1 s temperature polling timer."""
        self.controller.connect_cam()
        self.timer_temp.start(1000)

    def disconnect_cam(self):
        """Stop temperature polling and disconnect the camera."""
        self.timer_temp.stop()
        self.controller.disconnect_cam()

    # ---- ROI / BIN PRESETS ----

    def apply_roi_preset(self, text):
        """
        Populate the ImageWidget ROI inputs with a centred preset ROI size.
 
        Args:
            text: Preset string in 'WxH' format (e.g. '512x256'), or 'Custom'
                  to leave inputs unchanged.
        """
        try:
            full_w, full_h = self.controller.detect_cam_size()
        except:
            return

        if text == "Custom":
            return

        roi_w, roi_h = map(int, text.split("x"))

        # Center ROI
        hstart = (full_w - roi_w) // 2
        vstart = (full_h - roi_h) // 2
        hend = hstart + roi_w
        vend = vstart + roi_h

        w = self.image_widget

        w.roi_hstart_input.setText(str(hstart))
        w.roi_hend_input.setText(str(hend))
        w.roi_vstart_input.setText(str(vstart))
        w.roi_vend_input.setText(str(vend))


    def apply_bin_preset(self, text):
        """
        Populate the ImageWidget binning inputs from a preset string.
 
        Args:
            text: Preset string in 'HxV' format (e.g. '2x2'), or 'Custom'.
        """
        if text == "Custom":
            return

        hbin, vbin = map(int, text.split("x"))
        w = self.image_widget
        w.roi_hbin_input.setText(str(hbin))
        w.roi_vbin_input.setText(str(vbin))

    def set_settings(self):
        """
        Collect all current widget values and send them to the controller as a
        complete camera settings update.
 
        Reads shutter, read mode, acquisition mode, trigger mode, exposure,
        amplifier mode, VS speed, and EMCCD gain, then calls
        controller.apply_cam_settings().  Shows a success message on completion.
        """
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

        emccd_gain_input = self.emccd_gain_input.text()
        emccd_advanced = self.emccd_advanced_checkbox.isChecked()

        emccd_gain = {"emccd_gain": emccd_gain_input, "emccd_advanced": emccd_advanced}

        result = self.controller.apply_cam_settings(shutter, read_mode_params, acquisition_mode_params, trigger_mode, exposure, amp, vsspeed, emccd_gain)

        if result is None: 
            self.display_msg("Settings applied",True)
            return

    def show_preview(self):
        """
        Trigger a single-frame preview acquisition, display the frame in the
        Preview tab, and update the Live spectrum plot.
        """
        result = self.controller.single_preview()
        if result is None:
            return

        frame, spectrum_data = result

        self.display_image(frame)
        self.show_live_spectrum(spectrum_data)
        self.display_msg("Preview captured.", success=True)

    def display_image(self,frame):
        """
        Normalise a raw detector frame to 8-bit and render it in PreviewWidget.
 
        Args:
            frame: 2-D ndarray of raw detector counts, or None (no-op).
        """
        if frame is None:
            return

        frame8, h, w = self.controller.adjust_frame(frame)
        roi = self.controller.get_roi()
        self.preview.set_frame((frame8,h,w),roi)

    def create_spectrum_plot(self, title="Spectrum"):
        """
        Create and configure a new pyqtgraph PlotWidget for spectrum display.
 
        Sets axis labels, enables a grid, adds a legend, attaches a hover-tooltip
        TextItem, and connects mouse-move events to on_spectrum_hover().
 
        Args:
            title: Descriptive title (for context only; not shown in the widget).
 
        Returns:
            Configured pg.PlotWidget with private attributes:
            _label (TextItem), _x/_y (last data arrays), _curves (list of dicts).
        """
        plot = pg.PlotWidget()
        plot.setLabel("left", "Intensity")
        plot.setLabel("bottom", "Detector pixel")
        plot.showGrid(x=True, y=True, alpha=0.2)
        vb = plot.getViewBox()
        vb.setMouseEnabled(x=True, y=True)
        vb.setDefaultPadding(0.0)
        plot.addLegend()
        label = pg.TextItem("", anchor=(0.5, 1), fill =pg.mkBrush(0,0,0),border=pg.mkPen(255,255,255))
        label.setZValue(500)
        label.setVisible(False)
        plot.addItem(label)
        plot._label = label
        plot._x = None
        plot._y = None
        plot._curves = []  
        plot.scene().sigMouseMoved.connect(lambda pos, p=plot: self.on_spectrum_hover(pos, p))
        plot.setMouseTracking(True)
        return plot
    
    def get_next_pen(self):
        """
        Return the next pen from the cycling colour palette and advance the index.
 
        Returns:
            pg.mkPen object.
        """
        pen = self.plot_pens[self.next_plot_pen_idx % len(self.plot_pens)]
        self.next_plot_pen_idx += 1
        return pen

    def add_curve_to_spectrum_plot(self, plot, spectrum_data, name, pen=None, clear_existing=False):
        """
        Add a spectrum curve to a PlotWidget, updating axis ranges to fit all
        curves currently on the plot.
 
        Args:
            plot:           PlotWidget from create_spectrum_plot().
            spectrum_data:  Tuple (x, y) of 1-D ndarrays.
            name:           Legend label for this curve.
            pen:            pyqtgraph pen.  None = next cyclic pen.
            clear_existing: If True, remove all existing curves before adding
                            the new one (used for live/preview single-curve updates).
        """
        x, y = spectrum_data
        x = np.asarray(x)
        y = np.asarray(y)

        if clear_existing:
            for item in getattr(plot, "_curves", []):
                plot.removeItem(item["curve"])
            plot._curves = []

        if pen is None:
            pen = self.get_next_pen()

        curve = plot.plot(x, y, pen=pen, name=name)
        plot._curves.append({
            "curve": curve,
            "x": x,
            "y": y,
            "name": name
        })
        plot._x = x
        plot._y = y
        all_x = np.concatenate([c["x"] for c in plot._curves]) if plot._curves else x
        all_y = np.concatenate([c["y"] for c in plot._curves]) if plot._curves else y
        xmin = float(all_x.min())
        xmax = float(all_x.max())
        ymin = float(all_y.min())
        ymax = float(all_y.max())

        if ymin == ymax:
            ymax = ymin + 1

        ypad = max((ymax - ymin) * 0.08, 1.0)

        plot.setLimits(xMin=xmin, xMax=xmax)
        plot.setXRange(xmin, xmax, padding=0)
        plot.setYRange(ymin - ypad, ymax + ypad, padding=0)
        plot._label.setVisible(False)


    def update_spectrum_plot(self, plot, spectrum_data, name="Spectrum",pen=None):
        """
        Replace all curves on a plot with a single new curve.
 
        Thin wrapper around add_curve_to_spectrum_plot with clear_existing=True,
        used for live preview and single-shot preview updates.
 
        Args:
            plot:          Target PlotWidget.
            spectrum_data: Tuple (x, y).
            name:          Legend label.
            pen:           Pen override; None = next cyclic pen.
        """
        self.add_curve_to_spectrum_plot(
            plot,
            spectrum_data,
            name=name,
            pen=pen,
            clear_existing=True
        )

    def create_empty_spectrum_tab(self, title="Spectrum"):
        """
        Create a new empty spectrum tab in the Spectrogram tab widget and
        switch focus to it.
 
        Args:
            title: Tab label (default 'Spectrum').
 
        Returns:
            The newly created PlotWidget.
        """
        plot = self.create_spectrum_plot(title)
        index = self.calibration_tabs.addTab(plot, title)
        self.calibration_tabs.setCurrentIndex(index)
        self.right_tabs.setCurrentWidget(self.calibration_tab)
        return plot


    def on_spectrum_hover(self, pos, plot):
        """
        Update the floating tooltip on a spectrum plot as the mouse moves.
 
        Finds the nearest x-position across all curves and builds a multi-line
        label showing pixel index and per-curve intensities, positioned above the
        highest curve at that x location.  Hides the tooltip outside all x-ranges.
 
        Args:
            pos:  QPointF scene position from sigMouseMoved.
            plot: PlotWidget that emitted the signal.
        """
        curves = getattr(plot, "_curves", [])
        if not curves:
            return

        vb = plot.getViewBox()
        if vb is None:
            return

        mouse_point = vb.mapSceneToView(pos)

        entries = []
        x_for_label = None
        y_for_label = None

        for item in curves:
            x = item["x"]
            y = item["y"]
            name = item["name"]

            if len(x) == 0:
                continue

            x_min, x_max = float(x.min()), float(x.max())
            if mouse_point.x() < x_min or mouse_point.x() > x_max:
                continue

            idx = int(np.argmin(np.abs(x - mouse_point.x())))
            px = float(x[idx])
            py = float(y[idx])

            entries.append((name,px,py))

            if x_for_label is None:
                x_for_label = px
                y_for_label = py
            else:
                if py>y_for_label:
                    x_for_label = px
                    y_for_label = py
        
        if not entries:
            plot._label.setVisible(False)
            return

        lines = [f"x={entries[0][1]:.0f}"]
        for name, _, py in entries:
            lines.append(f"{name}: {py:.0f}")

        plot._label.setText("\n".join(lines))
        plot._label.setPos(x_for_label,y_for_label)
        plot._label.setVisible(True)

    def show_live_spectrum(self, spectrum_data):
        """
        Update the dedicated Live spectrum tab with the latest live-preview data.
 
        Recreates the Live tab if the user previously closed it.
 
        Args:
            spectrum_data: Tuple (x, y) from the controller's live pipeline.
        """
        if spectrum_data is None:
            return

        if self.live_plot is None:
            self.live_plot = self.create_spectrum_plot("Live")
            self.live_tab_index = self.calibration_tabs.addTab(self.live_plot, "Live")

        self.update_spectrum_plot(self.live_plot, spectrum_data, name="Live",pen=self.orange_pen)
    
    def show_calibration_result(self, spectrum_data, title="Acquisition"):
        """
        Open a new spectrum tab containing the result of a completed acquisition.
 
        Uses self.pending_filename as the tab title if set during start_acquisition().
 
        Args:
            spectrum_data: Tuple (x, y) from the controller's acquisition pipeline.
            title:         Fallback tab title if no pending filename is set.
        """
        if self.pending_filename:
            title = self.pending_filename

        plot = self.create_spectrum_plot(title)
        self.update_spectrum_plot(plot, spectrum_data, name=title, pen=self.orange_pen)

        self.calibration_tabs.addTab(plot, title)
        self.pending_filename = None
    
    def close_calibration_tab(self, index):
        """
        Remove a spectrum tab and free its PlotWidget.
 
        If the closed tab is the Live plot, resets self.live_plot to None so
        it will be recreated on the next live frame.
 
        Args:
            index: Tab index within calibration_tabs.
        """
        widget = self.calibration_tabs.widget(index)
        if widget is self.live_plot:
            self.live_plot = None
            self.live_tab_index = None

        self.calibration_tabs.removeTab(index)
        widget.deleteLater()

    # UNUSED
    def acquisition_preview(self):
        
        frame = self.controller.acquire_single()
        self.display_image(frame)

    def start_acquisition(self):
        """
        Validate the filename, compose the full .npz filename, and start an
        async acquisition via the controller.
 
        Does nothing if check_filename() returns False.
        """
        if self.check_filename():
            name = self.filename_input.text().strip()
            idx = self.file_index_input.text().strip()
            filename = f"{name}_{idx}.npz"
            self.controller.start_acquisition_async(filename=filename)

    def stop_acquisition(self):
        """Request the controller to abort the running acquisition."""
        self.controller.stop_acquisition_async()

    def handle_acq_result(self, spectrum):
        """
        Slot called when AcquisitionWorker finishes.
 
        On success: shows a success message, auto-increments the file index,
        and opens a new spectrum tab.  On failure: shows an error message.
 
        Args:
            spectrum: 1-D ndarray on success, or None on error / cancellation.
        """
        if spectrum is None:
            self.display_msg("Acquisition failed or camera lost during acquisition.")
            return
        
        self.display_msg("Acquisition finished successfully.",success=True)

        try:
            idx = int(self.file_index_input.text().strip())
            self.file_index_input.setText(str(idx+1))

        except:
            pass

        self.show_calibration_result(spectrum)

    def check_filename(self):
        """
        Validate that a non-empty filename is entered and warn if the target
        file already exists.
 
        Sets self.pending_filename on success so that handle_acq_result() can
        use it as the spectrum tab title.
 
        Returns:
            True if the acquisition should proceed, False to abort.
        """
        name = self.filename_input.text().strip()
        idx = self.file_index_input.text().strip()

        if not name:
            self.display_msg("Please enter a filename.")
            return False
        
        idx = int(idx) if idx else 1
        filename = f"{name}_{idx}.npz"

        save_path = Path(self.controller.get_save_path()) / filename
        print(f"Checking save path: {save_path}")
        print(f"Save path exists: {save_path.exists()}")
        if save_path.exists():
            reply = QMessageBox.question(self, "File Exists", f"{filename} already exists in {save_path}. Do you want to overwrite it?", QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.No:
                return False
        
        self.pending_filename = filename
        return True

    def start_live(self):
        """Start the live preview worker and display a status message."""
        self.controller.start_live_async()
        self.display_msg("Live mode started.", success=True)

    def stop_live(self):
        """Stop the live preview worker and display a status message."""
        self.controller.stop_live_async()
        self.display_msg("Live mode stopped.", success=True)

    def handle_live_results(self, frame, spectrum_data):
        """
        Slot called by LiveWorker on each captured frame.
 
        Updates both the PreviewWidget image and the Live spectrum tab.
 
        Args:
            frame:         2-D ndarray display frame, or None.
            spectrum_data: Tuple (x, y), or None.
        """
        if frame is not None:
            self.display_image(frame)

        if spectrum_data is not None:
            self.show_live_spectrum(spectrum_data)

    # UNUSED
    def toggle_accum_input(self, mode):
        if mode == "accumulate":
            self.accum_n_input.show()
        else:
            self.accum_n_input.hide()


    def select_dlls_path(self):
        """
        UNUSED -- not connected to any button in the current UI.
        Originally allowed the user to choose the Andor SDK2 DLL directory.
        Safe to delete.
        """
        file = QFileDialog.getExistingDirectory(self, "Select dll file")
        if file:
            self.dlls_path = file
            self.dlls_path_label.setText(os.path.basename(file))

    def select_save_frame_path(self):
        """
        Open a directory picker and update both the save-path label and the
        AcquisitionService save directory via the controller.
        """
        folder = QFileDialog.getExistingDirectory(self,"Select folder to save data","",QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks)
        if folder:
            self.save_frame_path_label.setText(f"Data saved to: {folder}")
            self.controller.set_save_frame_path(Path(folder))

    def open_npz(self):
        """
        Open a file picker, load a saved NPZ experiment file, and overlay
        its spectrum onto the currently selected Spectrogram tab.
 
        If the file contains metadata and the camera is connected, the user is
        offered the option to restore those settings into the GUI and apply them
        to the hardware.
 
        Shows a critical error dialog if the file cannot be loaded.
        """
        file, _ = QFileDialog.getOpenFileName(
            self,
            "Open NPZ file",
            "",
            "NPZ Files (*.npz)"
        )

        if not file:
            return

        try:
            data = np.load(file, allow_pickle=True)

            spectrum = data["spectrum"]
            pixel = data["pixel"]
            spectrum_data = (pixel, spectrum)

            metadata = None
            if "metadata" in data:
                metadata = data["metadata"].item()

            name = Path(file).name

            current_plot = self.calibration_tabs.currentWidget()
            if current_plot is None:
                current_plot = self.create_empty_spectrum_tab(title=name)

            self.add_curve_to_spectrum_plot(current_plot, spectrum_data, name=name)

            self.right_tabs.setCurrentWidget(self.calibration_tab)

            if self.controller.is_camera_alive():
                if metadata:
                    reply = QMessageBox.question(
                        self,
                        "Load Settings",
                        "This file contains acquisition settings.\n"
                        "Do you want to load them into the GUI?",
                        QMessageBox.Yes | QMessageBox.No
                    )

                    if reply == QMessageBox.Yes:
                        self.load_settings_from_metadata(metadata)
                        self.set_settings()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to open file:\n{e}")

    def separator(self):
        sep = QWidget()
        sep.setFixedWidth(1)
        sep.setObjectName("statusSeparator")
        return sep

    def closeEvent(self, event):
        """
        Override QMainWindow.closeEvent to safely shut down the camera before
        the application exits.
 
        Stops the temperature timer, halts any live preview, warms the sensor,
        and disconnects the camera.  Each step is individually guarded so a
        failure in one does not prevent the others from running.
 
        Args:
            event: QCloseEvent -- always accepted to allow the window to close.
        """
        print("[GUI] Application closing... running safe shutdown")

        try:
            
            try:
                self.timer_temp.stop()
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
                self.disconnect_cam()
                print("Camera disconnected safely due to shutdown.")
            except Exception as e:
                print("Camera disconnect failed:", e)

        except Exception as e:
            print("[GUI] Unexpected error during closeEvent:", e)

        event.accept()

    def handle_camera_loss(self):
        """
        Slot called when the controller emits camera_lost_signal.
 
        Stops all running workers (acquisition, live, cooling), resets the
        controller state via disconnect_cam(), and clears the temperature and
        shutter status labels.
        """
        self.display_msg("Camera connection lost!")

        if self.controller.acq_worker and self.controller.acq_worker.isRunning():
            self.controller.stop_acquisition_async()

        if self.controller.live_worker and self.controller.live_worker.isRunning():
            self.controller.stop_live_async()

        if hasattr(self.controller, "cooling_worker") and self.controller.cooling_worker.isRunning():
            self.controller.stop_cooling()
            self.controller.cooling_worker.wait()

        # reset controller state
        try:
            self.disconnect_cam()
        except:
            pass
        
        self.temp.setText("Temp: -- °C")
        self.shutter_current_state.setText("Shutter State: --")

def _safe_exit_close():
    """
    atexit handler that performs a best-effort camera shutdown even if an
    unhandled exception kills the application before closeEvent fires.
 
    Attempts to warm the camera, disconnect it, and disconnect the spectrometer
    by reaching the controller through the active QApplication window.
    All steps are individually guarded so failures are non-fatal.
    """
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
        
        window.display_msg("Camera disconnected")

    except Exception as e:
        print("[EXIT] Error in atexit shutdown:", e)

# Register handler
atexit.register(_safe_exit_close)

def excepthook(exc_type, exc_value, exc_traceback):
    """
    Custom sys.excepthook that routes unhandled exceptions to the GUI status bar
    instead of crashing silently.
 
    For KeyboardInterrupt and SystemExit, runs _safe_exit_close() then delegates
    to the default excepthook.  For all other exceptions, attempts to show the
    error in the status bar; falls back to a console print if the window is gone.
 
    Args:
        exc_type:      Exception class.
        exc_value:     Exception instance.
        exc_traceback: Traceback object.
    """
    traceback.print_exception(exc_type, exc_value, exc_traceback)

    # allow normal hard-exit cases
    if issubclass(exc_type, (KeyboardInterrupt, SystemExit)):
        _safe_exit_close()
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    app = QApplication.instance()
    window = app.activeWindow() if app else None

    if window and hasattr(window, "display_msg"):
        try:
            window.display_msg(f"Unexpected error: {exc_value}")
            return
        except Exception:
            pass

    print(f"[GUI] Unhandled non-fatal exception: {exc_value}")

sys.excepthook = excepthook

def main():
    """
    Application entry point.
 
    Creates the QApplication, applies the dark stylesheet, maximises the
    MainWindow, and enters the Qt event loop.
    """
    app = QApplication(sys.argv)
    app.setStyleSheet("""

        QWidget#leftPanel {
            background-color: #2b2b2b;
        }

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

        QPushButton {
            background-color: #4a5258;
            border: 1px solid #555555;
            padding: 5px;
        }

        QPushButton:pressed {
            background-color: #3f464c;
        }

        QPushButton:hover {
            background-color: #555e66;
        }

        QPushButton:disabled {
            background-color: #2a2a2a;
            border: 1px solid #333333;
            color: #777777;
        }
    """)

    window = MainWindow()
    window.move(0,0)
    window.showMaximized()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()

