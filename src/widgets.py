import atexit
import sys
from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QStackedWidget, QLineEdit, QPushButton, QFileDialog, QLabel, QComboBox, QMessageBox
from PyQt5.QtGui import QIntValidator, QDoubleValidator, QImage, QPixmap
from PyQt5.QtCore import pyqtSignal, QTimer, QThread
import os
from controller import RamanCameraController
from typing import Dict

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

    def get_params(self):
        params = {"mode": "image"}
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