import atexit
import sys
from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QStackedWidget, QLineEdit, QPushButton, QFileDialog, QLabel, QComboBox, QMessageBox
from PyQt5.QtGui import QIntValidator, QDoubleValidator, QImage, QPixmap
from PyQt5.QtCore import pyqtSignal, QTimer, QThread
import os
from controller import RamanCameraController
from typing import Dict


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

    def __init__(self):
        super().__init__()
        layout = QHBoxLayout(self)
        label = QLabel("Image ROI settings")

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

        layout.addWidget(label)
        layout.addWidget(self.roi_hstart_input)
        layout.addWidget(self.roi_hend_input)
        layout.addWidget(self.roi_vstart_input)
        layout.addWidget(self.roi_vend_input)
        layout.addWidget(self.roi_hbin_input)
        layout.addWidget(self.roi_vbin_input)

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
        self.cycle_time_acc_input.setPlaceholderText("Aquisition Period (ms)")
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
        self.cycle_time_input.setPlaceholderText("Acquisition Period between accum frames (ms)")
        self.cycle_time_input.setValidator(QDoubleValidator())

        self.num_acc_input = QLineEdit()
        self.num_acc_input.setPlaceholderText("Number of Accumulated frames")
        self.num_acc_input.setValidator(QIntValidator())

        self.cycle_time_acc_input = QLineEdit()
        self.cycle_time_acc_input.setPlaceholderText("Aquisition Period (ms)")
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
        self.cycle_time_acc_input.setPlaceholderText("Aquisition Period (ms)")
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
        label = QLabel("Continuous Aquisition Mode Settings")

        self.cycle_time = QLineEdit()
        self.cycle_time.setPlaceholderText("Acquisition Period (ms)")
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