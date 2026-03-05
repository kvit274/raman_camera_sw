import atexit
import sys
from PyQt5.QtWidgets import QSlider, QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QStackedWidget, QLineEdit, QPushButton, QFileDialog, QLabel, QComboBox, QMessageBox, QToolButton, QCheckBox
from PyQt5.QtGui import QIntValidator, QDoubleValidator, QImage, QPixmap, QPainter, QPen, QColor
from PyQt5.QtCore import pyqtSignal, QTimer, QThread, Qt, QRectF, QRect, QSize, QEvent
import pyqtgraph as pg
import os
from controller import RamanCameraController
from typing import Dict

# Temperature pop up

class TemperaturePopUp(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent,Qt.Popup)

        self.setFixedSize(250,120)

        layout = QVBoxLayout(self)
        
        self.label = QLabel("-20 C")
        self.label.setAlignment(Qt.AlignCenter)

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setMinimum(-90)
        self.slider.setMaximum(0)
        self.slider.setValue(-20)

        self.apply_btn = QPushButton("Apply")

        layout.addWidget(self.label)
        layout.addWidget(self.slider)
        layout.addWidget(self.apply_btn)

        self.slider.valueChanged.connect(self.update_label)

    def update_label(self,value):
        self.label.setText(f"{value} C")
    
    def get_value(self):
        return self.slider.value()


# ==== PAINT ON PREVIEW ====


class PreviewWidget(QWidget):
    def __init__(self):
        super().__init__()

        self.setFixedSize(1024,256)  # ideally not hardcoded
        self.setStyleSheet("background-color:black;")

        self.overlay_enabled = False
        self.roi = None
        self.frame = None
        self.show_roi = False
        self.show_grid = False

    def set_roi(self, roi):
        self.roi = roi
        self.update()

    def set_frame(self,frame):
        self.frame = frame
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.black)

        # Draw frame
        if self.frame:
            frame8, h, w = self.frame
            qimg = QImage(frame8.tobytes(), w, h, w, QImage.Format_Grayscale8)
            painter.drawImage(0,0, qimg)

        # Draw ROI + grid (same logic, but inside image_rect)
        if self.overlay_enabled and self.roi:
            hstart, hend, vstart, vend, hbin, vbin = self.roi

            pen = QPen(Qt.yellow)
            pen.setWidth(1)
            painter.setPen(pen)

            if self.show_roi:
                painter.drawLine(hstart,vstart,hend-1,vstart)
                painter.drawLine(hstart,vend-1,hend-1,vend-1)
                painter.drawLine(hstart,vstart,hstart,vend-1)
                painter.drawLine(hend-1,vstart,hend-1,vend-1)

            if self.show_grid:
                if hbin > 1:
                    for x in range(hstart, hend, hbin):
                        painter.drawLine(x, vstart, x, vend-1)

                if vbin > 1:
                    for y in range(vstart, vend, vbin):
                        painter.drawLine(hstart, y, hend-1, y)

# ==== Draw Rulers ====

class RulerContainer(QWidget):
    def __init__(self, preview_widget):
        super().__init__()

        self.preview = preview_widget

        self.ruler_left = 60
        self.ruler_top = 40
        self.margin_right = 20
        self.margin_bottom = 20

        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            self.ruler_left,
            self.ruler_top,
            self.margin_right,
            self.margin_bottom
        )
        layout.addWidget(self.preview)

        self.setObjectName("rulerContainer")

    def paintEvent(self, event):
        super().paintEvent(event)

        painter = QPainter(self)
        painter.setPen(QPen(Qt.white))

        image_rect = self.preview.geometry()

        detector_w = 1024
        detector_h = 256

        # ---------- X axis (TOP) ----------
        step_x = 256
        for x in range(0, detector_w + 1, step_x):
            px = image_rect.left() + int(
                x * image_rect.width() / detector_w
            )

            painter.drawLine(px, image_rect.top() - 6, px, image_rect.top())
            painter.drawText(px - 15, image_rect.top() - 10, str(x))

        # ---------- Y axis (LEFT) ----------
        step_y = 64
        for y in range(0, detector_h + 1, step_y):
            py = image_rect.top() + int(
                y * image_rect.height() / detector_h
            )

            painter.drawLine(image_rect.left() - 6, py,
                            image_rect.left(), py)

            painter.drawText(5, py + 5, str(y))


# ==== UNSCROLLABLE COMBO BOX ====

class QNoScrollComboBox(QComboBox):
    """
    Avoids accidental scrolling between option
    """

    def wheelEvent(self,event):
        event.ignore()

# ==== LEFT PART LAYOUT ====

class CollapsibleSection(QWidget):
    def __init__(self, title):
        super().__init__()

        self.toggle_button = QToolButton()
        self.toggle_button.setText(title)
        self.toggle_button.setCheckable(True)
        self.toggle_button.setChecked(False)
        self.toggle_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.toggle_button.setArrowType(Qt.RightArrow)
        self.toggle_button.clicked.connect(self.toggle)

        self.content_area = QWidget()
        self.content_area.setVisible(False)

        self.content_area.setStyleSheet("sectionContent")

        layout = QVBoxLayout(self)
        layout.addWidget(self.toggle_button)
        layout.addWidget(self.content_area)
        layout.setContentsMargins(0, 0, 0, 0)

    def toggle(self):
        expanded = self.toggle_button.isChecked()
        self.toggle_button.setArrowType(
            Qt.DownArrow if expanded else Qt.RightArrow
        )
        self.content_area.setVisible(expanded)

    def setContentLayout(self, content_layout):
        self.content_area.setLayout(content_layout)

# ===== READ MODE WIDGETS =====

class MultiTrackWidget(QWidget):

    """
    Number is the number of rows (or row sets) to read, height is number of one row set (1 for a single row), offset is the distance between the row sets.
    Return a tuple (number, height, offset, top, gap), where top is the offset of the first row from the top, and gap is the gap between the tracks.
    """

    def __init__(self):
        super().__init__()
        layout = QHBoxLayout(self)
        label = QLabel("Multi-Track Settings")

        self.number_input = QLineEdit()
        self.number_input.setPlaceholderText("Number of rows")
        self.number_input.setValidator(QIntValidator())

        self.height_input = QLineEdit()
        self.height_input.setPlaceholderText("Height (number of 1 row sets)")
        self.height_input.setValidator(QIntValidator())

        self.offset_input = QLineEdit()
        self.offset_input.setPlaceholderText("Offset (distance between row sets)")
        self.offset_input.setValidator(QIntValidator())
        layout.addWidget(label)
        layout.addWidget(self.number_input)
        layout.addWidget(self.height_input)
        layout.addWidget(self.offset_input)

        # self.setLayout(layout)

    def get_params(self):
        params = {"mode": "multi_track"}
        number, height, offset = self.number_input.text(), self.height_input.text(), self.offset_input.text()
        if number != "":
            params["number"] = number
        if height != "":
            params["height"] = height
        if offset != "":
            params["offset"] = offset
        return params

class SingleTrackWidget(QWidget):

    """"Center and width specify selection of the rows to be averaged together"""
    
    def __init__(self):
        super().__init__()
        layout = QHBoxLayout(self)
        label = QLabel("Single-Track Settings")

        self.center_input = QLineEdit()
        self.center_input.setPlaceholderText("Center")
        self.center_input.setValidator(QIntValidator())

        self.width_input = QLineEdit()
        self.width_input.setPlaceholderText("Track Width")
        self.width_input.setValidator(QIntValidator())

        layout.addWidget(label)
        layout.addWidget(self.center_input)
        layout.addWidget(self.width_input)

        # self.setLayout(layout)

    def get_params(self):
        params = {"mode": "single_track"}
        center, width = self.center_input.text(), self.width_input.text()
        if center != "":
            params["center"] = center
        if width != "":
            params["width"] = width
        return params

class FVBWidget(QWidget):

    def __init__(self):
        super().__init__()

        # self.setLayout(layout)

    def get_params(self):
        params = {"mode": "fvb"}
        return params

class ImageWidget(QWidget):

    roi_visual_changed = pyqtSignal(tuple,bool,bool)        # roi tuple, show roi, show grid

    def __init__(self):
        super().__init__()

        layout = QVBoxLayout(self)
        label = QLabel("Image ROI settings")
        layout.addWidget(label)

        # ROI preset selector
        self.roi_preset_input = QNoScrollComboBox()
        self.roi_preset_input.addItems(["1024x256", "512x128", "256x64", "128x32", "Custom"])
        self.roi_preset_input.setCurrentText("Custom")
        self.show_roi_checkbox = QCheckBox("Show ROI")
        layout.addWidget(QLabel("ROI Presets"))
        layout.addWidget(self.show_roi_checkbox)
        layout.addWidget(self.roi_preset_input)

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

        layout.addWidget(self.roi_hstart_input)
        layout.addWidget(self.roi_hend_input)
        layout.addWidget(self.roi_vstart_input)
        layout.addWidget(self.roi_vend_input)

        # Binning preset selector
        self.bin_preset_input = QNoScrollComboBox()
        self.bin_preset_input.addItems(["1x1","2x2","4x4","8x8","Custom"])
        self.bin_preset_input.setCurrentText("Custom")
        self.show_grid_checkbox = QCheckBox("Show binning grid")
        layout.addWidget(QLabel("Binning Preset"))
        layout.addWidget(self.show_grid_checkbox)
        layout.addWidget(self.bin_preset_input)

        self.roi_hbin_input = QLineEdit()
        self.roi_hbin_input.setPlaceholderText("ROI H Bin")
        self.roi_hbin_input.setValidator(QIntValidator())

        self.roi_vbin_input = QLineEdit()
        self.roi_vbin_input.setPlaceholderText("ROI V Bin")
        self.roi_vbin_input.setValidator(QIntValidator())
        
        layout.addWidget(self.roi_hbin_input)
        layout.addWidget(self.roi_vbin_input)

        self.roi_preset_input.currentTextChanged.connect(self.apply_roi_preset)
        self.bin_preset_input.currentTextChanged.connect(self.apply_bin_preset)
        for field in [self.roi_hstart_input,self.roi_hend_input,self.roi_vstart_input,self.roi_vend_input,self.roi_hbin_input,self.roi_vbin_input]:
            field.textChanged.connect(self.emit_visual_update)
        self.show_roi_checkbox.stateChanged.connect(self.emit_visual_update)
        self.show_grid_checkbox.stateChanged.connect(self.emit_visual_update)

    def emit_visual_update(self):
        try:
            roi = (
                int(self.roi_hstart_input.text() or 0),
                int(self.roi_hend_input.text() or 0),
                int(self.roi_vstart_input.text() or 0),
                int(self.roi_vend_input.text() or 0),
                int(self.roi_hbin_input.text() or 1),
                int(self.roi_vbin_input.text() or 1)
            )

            self.roi_visual_changed.emit(roi,self.show_roi_checkbox.isChecked(),self.show_grid_checkbox.isChecked())
        except:
            pass

    def apply_roi_preset(self, text):
        if text == "Custom":
            return

        full_w = 1024
        full_h = 256

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

    def get_params(self):
        params = {"mode": "image"}
        hstart, hend = self.roi_hstart_input.text(), self.roi_hend_input.text()
        vstart, vend = self.roi_vstart_input.text(), self.roi_vend_input.text()
        hbin, vbin = self.roi_hbin_input.text(), self.roi_vbin_input.text()
        params["hstart"] = hstart
        params["hend"] = hend
        params["vstart"] = vstart
        params["vend"] = vend
        params["hbin"] = hbin
        params["vbin"] = vbin
        return params

class RandomTrackWidget(QWidget):

    def __init__(self):
        super().__init__()
        layout = QHBoxLayout(self)
        label = QLabel("Random-Track Settings")

        self.start_input = QLineEdit()
        self.start_input.setPlaceholderText("Start")
        self.start_input.setValidator(QIntValidator())

        self.stop_input = QLineEdit()
        self.stop_input.setPlaceholderText("Stop")
        self.stop_input.setValidator(QIntValidator())

        layout.addWidget(label)
        layout.addWidget(self.start_input)
        layout.addWidget(self.stop_input)

    def get_params(self):
        params = {"mode": "random_track"}
        start, stop = self.start_input.text(), self.stop_input.text()
        if start != "":
            params["start"] = start
        if stop != "":
            params["stop"] = stop
        return params


# ===== ACQUISITION MODE WIDGETS =====

class AccumWidget(QWidget):
    """
    num_acc is the number of accumulated frames,
    cycle_time_acc is the acquisition period (by default the minimal possible based on exposure and transfer time).
    """

    def __init__(self):
        super().__init__()
        layout = QHBoxLayout(self)
        label = QLabel("Accumulative Aquisition Mode Settings")

        self.num_acc_input = QLineEdit()
        self.num_acc_input.setPlaceholderText("Number of Accumulated frames")
        self.num_acc_input.setValidator(QIntValidator())

        self.cycle_time_acc_input = QLineEdit()
        self.cycle_time_acc_input.setPlaceholderText("Aquisition Period (s)")
        self.cycle_time_acc_input.setValidator(QDoubleValidator())

        layout.addWidget(label)
        layout.addWidget(self.num_acc_input)
        layout.addWidget(self.cycle_time_acc_input)

    def get_params(self):
        params = {"mode": "accum"}
        num_acc = self.num_acc_input.text()
        cycle_time_acc = self.cycle_time_acc_input.text()

        if num_acc != "":
            params["num_acc"] = num_acc
        if cycle_time_acc != "":
            params["cycle_time_acc"] = cycle_time_acc
        return params

class KineticWidget(QWidget):
    """
    num_cycle is the number of kinetic cycles frames, 
    cycle_time is the acquisition period between accum frames, 
    num_accum is the number of accumulated frames, 
    cycle_time_acc is the accum acquisition period, 
    num_prescan is the number of prescans.
    """

    def __init__(self):
        super().__init__()
        layout = QHBoxLayout(self)
        label = QLabel("Kinetic Aquisition Mode Settings")

        self.num_cycle_input = QLineEdit()
        self.num_cycle_input.setPlaceholderText("Number of Cycles")
        self.num_cycle_input.setValidator(QIntValidator())

        self.cycle_time_input = QLineEdit()
        self.cycle_time_input.setPlaceholderText("Acquisition Period between accum frames (s)")
        self.cycle_time_input.setValidator(QDoubleValidator())

        self.num_acc_input = QLineEdit()
        self.num_acc_input.setPlaceholderText("Number of Accumulated frames")
        self.num_acc_input.setValidator(QIntValidator())

        self.cycle_time_acc_input = QLineEdit()
        self.cycle_time_acc_input.setPlaceholderText("Aquisition Period (s)")
        self.cycle_time_acc_input.setValidator(QDoubleValidator())

        self.num_prescan = QLineEdit()
        self.num_prescan.setPlaceholderText("Number of Prescan Frames")
        self.num_prescan.setValidator(QIntValidator())

        layout.addWidget(label)
        layout.addWidget(self.num_cycle_input)
        layout.addWidget(self.cycle_time_input)
        layout.addWidget(self.num_acc_input)
        layout.addWidget(self.cycle_time_acc_input)
        layout.addWidget(self.num_prescan)

    def get_params(self):
        params = {"mode": "kinetic"}
        num_cycle = self.num_cycle_input.text()
        cycle_time = self.cycle_time_input.text()
        num_acc = self.num_acc_input.text()
        cycle_time_acc = self.cycle_time_acc_input.text()
        num_prescan = self.num_prescan.text()

        if num_cycle != "":
            params["num_cycle"] = num_cycle
        if cycle_time != "":
            params["cycle_time"] = cycle_time
        if num_acc != "":
            params["num_acc"] = num_acc
        
        if cycle_time_acc != "":
            params["cycle_time_acc"] = cycle_time_acc
        if num_prescan != "":
            params["num_prescan"] = num_prescan
        return params

class FastKineticWidget(QWidget):
    """
    num_acc is the number of accumulated frames, 
    cycle_time_acc is the acquisition period (by default the minimal possible based on exposure and transfer time).
    """

    def __init__(self):
        super().__init__()
        layout = QHBoxLayout(self)
        label = QLabel("Fast Kinetic Aquisition Mode Settings")

        self.num_acc_input = QLineEdit()
        self.num_acc_input.setPlaceholderText("Number of Accumulated frames")
        self.num_acc_input.setValidator(QIntValidator())

        self.cycle_time_acc_input = QLineEdit()
        self.cycle_time_acc_input.setPlaceholderText("Aquisition Period (s)")
        self.cycle_time_acc_input.setValidator(QDoubleValidator())

        layout.addWidget(label)
        layout.addWidget(self.num_acc_input)
        layout.addWidget(self.cycle_time_acc_input)

    def get_params(self):
        params = {"mode": "fast_kinetic"}
        num_acc = self.num_acc_input.text()
        cycle_time_acc = self.cycle_time_acc_input.text()
        if num_acc != "":
            params["num_acc"] = num_acc
        if cycle_time_acc != "":
            params["cycle_time_acc"] = cycle_time_acc
        return params

class ContinuousWidget(QWidget):
    """cycle_time is the acquisition period (by default the minimal possible based on exposure and transfer time)."""
    
    def __init__(self):
        super().__init__()
        layout = QHBoxLayout(self)
        label = QLabel("Continuous Acquisition Mode Settings")

        self.cycle_time = QLineEdit()
        self.cycle_time.setPlaceholderText("Acquisition Period (s)")
        self.cycle_time.setValidator(QDoubleValidator())


    def get_params(self):
        params = {"mode": "cont"}
        cycle_time = self.cycle_time.text()
        if cycle_time != "":
            params["cycle_time"] = cycle_time
        return params

class SingleWidget(QWidget):
    def __init__(self):
        super().__init__()

    def get_params(self):
        params = {"mode": "single"}
        return params
