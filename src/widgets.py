import atexit
import sys
from PyQt5.QtWidgets import QSlider, QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QStackedWidget, QLineEdit, QPushButton, QFileDialog, QLabel, QComboBox, QMessageBox, QToolButton, QCheckBox, QSizePolicy
from PyQt5.QtGui import QIntValidator, QDoubleValidator, QImage, QPixmap, QPainter, QPen, QColor
from PyQt5.QtCore import pyqtSignal, QTimer, QThread, Qt, QRectF, QRect, QSize, QEvent
import pyqtgraph as pg
import os
from controller import RamanCameraController
from typing import Dict

class TemperaturePopUp(QWidget):
    def __init__(self,parent=None):
        """
        Initialise the temperature selection pop-up widget.
 
        Creates a compact (250×120 px) popup containing a label showing the
        currently selected temperature, a horizontal slider ranging from –90 °C
        to 0 °C (default –20 °C), and an "Apply" button.
 
        Args:
            parent: Optional parent widget.
        """
        super().__init__(parent,Qt.Popup)

        self.setFixedSize(250,120)

        layout = QVBoxLayout(self)
        
        self.label = QLabel("-20 °C")
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
        """
        Update the temperature label to reflect the current slider position.
 
        Connected to 'slider.valueChanged'; called automatically when the
        user drags the slider.
 
        Args:
            value: Current slider integer value in °C.
        """
        self.label.setText(f"{value} °C")
    
    def get_value(self):
        """
        Return the temperature currently selected on the slider.
 
        Returns:
            int: Selected temperature in °C.
        """
        return self.slider.value()

class PreviewWidget(QWidget):

    roi_changed = pyqtSignal(tuple)
    bit_shift_region_changed = pyqtSignal(object, object)

    def __init__(self):
        """
        Initialise the live-preview canvas widget.
 
        Creates a 1024×256 px black canvas that can display grayscale detector
        frames and optionally overlay an interactive ROI rectangle, a binning
        grid, and a draggable bit-shift row region.
 
        Signals emitted:
            roi_changed(tuple):                    ROI tuple changed by user drag.
            bit_shift_region_changed(vstart, vend): Bit-shift region changed by user drag.
        """
        super().__init__()

        self.setFixedSize(1024,256)
        self.setStyleSheet("background-color:black;")

        self.overlay_enabled = False
        self.roi = None
        self.frame = None
        self.show_roi = False
        self.show_grid = False
        self.frame_roi = None

        self.drag_mode = None
        self.drag_start = None
        self.handle_size = 6

        self.bit_shift_region = None 
        self.show_bit_shift_region = False

    def set_bit_shift_region(self, vstart, vend, show=False):
        """
        Define (and optionally display) the bit-shift correction row region.
 
        Args:
            vstart: Top row of the shift region in detector pixels.
            vend:   Bottom row (exclusive) of the shift region.
            show:   If 'True', render the region overlay immediately.
        """
        self.bit_shift_region = (vstart, vend) if vstart is not None and vend is not None else None
        self.show_bit_shift_region = show
        self.update()

    def set_roi(self, roi):
        """
        Update the stored ROI tuple and schedule a repaint.
 
        Args:
            roi: 6-tuple '(hstart, hend, vstart, vend, hbin, vbin)'.
        """
        self.roi = roi
        self.update()

    def set_frame(self,frame, roi=None):
        """
        Supply a new detector frame for display and schedule a repaint.
 
        Args:
            frame: Tuple '(frame8, h, w)' as returned by 'adjust_frame()',
                   where 'frame8' is a uint8 ndarray.
            roi:   Optional 6-tuple used to position the frame within the canvas.
                   If 'None' the frame is drawn from the top-left corner.
        """
        self.frame = frame
        self.frame_roi = roi
        self.update()

    def detect_bit_shift_handle(self, x, y):
        """
        Determine which part of the bit-shift region (if any) the cursor is over.
 
        Args:
            x: Cursor x-coordinate in widget pixels.
            y: Cursor y-coordinate in widget pixels.
 
        Returns:
            str | None: 'bit_shift_top', 'bit_shift_bottom',
            'bit_shift_move', or 'None' if the cursor is not near the region.
        """
        if not (self.show_bit_shift_region and self.bit_shift_region):
            return None

        vstart, vend = self.bit_shift_region
        hs = self.handle_size + 2

        if abs(y - vstart) < hs:
            return "bit_shift_top"
        if abs(y - vend) < hs:
            return "bit_shift_bottom"
        if vstart < y < vend:
            return "bit_shift_move"

        return None

    def detect_handle(self,x,y):
        """
        Determine which ROI handle (if any) the cursor is over.
 
        Args:
            x: Cursor x-coordinate in widget pixels.
            y: Cursor y-coordinate in widget pixels.
 
        Returns:
            str | None: 'left', 'right', 'top', 'bottom',
            'move', or 'None' if the cursor is not near any handle.
        """
        if not self.roi:
            return None

        hstart,hend,vstart,vend,_,_ = self.roi
        hs = self.handle_size

        if abs(x-hstart) < hs:
            return "left"
        if abs(x-hend) < hs:
            return "right"
        if abs(y-vstart) < hs:
            return "top"
        if abs(y-vend) < hs:
            return "bottom"
        if hstart < x < hend and vstart < y < vend:
            return "move"

        return None

    def mousePressEvent(self, event):
        """
        Begin a drag operation when the user clicks on a ROI or bit-shift handle.
 
        Bit-shift region handles take priority over ROI handles.
 
        Args:
            event: QMouseEvent from the Qt framework.
        """
        x = event.x()
        y = event.y()

        mode = self.detect_bit_shift_handle(x, y)

        if mode:
            self.drag_mode = mode
            self.drag_start = (x, y)
            return

        if not self.roi:
            return

        mode = self.detect_handle(x, y)

        if mode:
            self.drag_mode = mode
            self.drag_start = (x, y)

    def mouseMoveEvent(self, event):
        """
        Update the ROI or bit-shift region during a drag operation.
 
        Enforces canvas bounds and minimum region sizes, then emits the
        appropriate signal and schedules a repaint.
 
        Args:
            event: QMouseEvent from the Qt framework.
        """
        if not self.drag_mode:
            return

        x = event.x()
        y = event.y()
        dx = x - self.drag_start[0]
        dy = y - self.drag_start[1]

        if self.drag_mode in {"bit_shift_top", "bit_shift_bottom", "bit_shift_move"}:
            if not self.bit_shift_region:
                return

            shift_vstart, shift_vend = self.bit_shift_region

            if self.drag_mode == "bit_shift_move":
                height = shift_vend - shift_vstart
                new_vstart = shift_vstart + dy
                new_vstart = max(0, min(256 - height, new_vstart))
                shift_vstart = new_vstart
                shift_vend = shift_vstart + height

            elif self.drag_mode == "bit_shift_top":
                shift_vstart += dy

            elif self.drag_mode == "bit_shift_bottom":
                shift_vend += dy

            shift_vstart = max(0, min(256, shift_vstart))
            shift_vend = max(0, min(256, shift_vend))

            if shift_vend <= shift_vstart + 1:
                return

            self.bit_shift_region = (shift_vstart, shift_vend)
            self.drag_start = (x, y)
            self.bit_shift_region_changed.emit(shift_vstart, shift_vend)
            self.update()
            return

        if not self.roi:
            return

        hstart,hend,vstart,vend,hbin,vbin = self.roi

        dx = x - self.drag_start[0]
        dy = y - self.drag_start[1]

        if self.drag_mode == "move":
            
            width = hend - hstart
            height = vend - vstart

            new_hstart = hstart + dx
            new_vstart = vstart + dy

            new_hstart = max(0,min(1024-width,new_hstart))
            new_vstart = max(0,min(256-height,new_vstart))

            hstart = new_hstart
            hend = hstart + width
            vstart = new_vstart
            vend = vstart + height

        elif self.drag_mode == "left":
            hstart += dx

        elif self.drag_mode == "right":
            hend += dx

        elif self.drag_mode == "top":
            vstart += dy

        elif self.drag_mode == "bottom":
            vend += dy

        hstart = max(0,min(1024,hstart))
        hend = max(1,min(1024,hend))
        vstart = max(0,min(256,vstart))
        vend = max(1,min(256,vend))

        if hend <= hstart+1:
            return

        if vend <= vstart+1:
            return

        self.roi = (hstart,hend,vstart,vend,hbin,vbin)

        self.drag_start = (x,y)

        self.roi_changed.emit(self.roi)

        self.update()

    def mouseReleaseEvent(self,event):
        """
        End the active drag operation.
 
        Args:
            event: QMouseEvent from the Qt framework.
        """
        self.drag_mode = None

    def paintEvent(self,event):
        """
        Render the detector frame, ROI overlay, binning grid, and bit-shift region.
 
        Draws the frame (if set) at its correct canvas position, then — when the
        overlay is enabled — draws the ROI rectangle in yellow, the binning grid
        in yellow, and the bit-shift region boundaries in green.
 
        Args:
            event: QPaintEvent from the Qt framework.
        """
        painter = QPainter(self)
        painter.fillRect(self.rect(),Qt.black)

        if self.frame:
            frame8,h,w = self.frame
            qimg = QImage(frame8.tobytes(),w,h,w,QImage.Format_Grayscale8)

            if self.frame_roi:
                hstart,hend,vstart,vend,_,_ = self.frame_roi
                painter.drawImage(hstart,vstart,qimg)
            else:
                painter.drawImage(0,0,qimg)

        if self.overlay_enabled and self.roi:

            hstart,hend,vstart,vend,hbin,vbin = self.roi

            pen = QPen(Qt.yellow)
            pen.setWidth(1)
            painter.setPen(pen)

            if self.show_roi:

                painter.drawLine(hstart,vstart,hend,vstart)
                painter.drawLine(hstart,vend,hend,vend)
                painter.drawLine(hstart,vstart,hstart,vend)
                painter.drawLine(hend,vstart,hend,vend)

            if self.show_grid:

                if hbin>1:
                    for x in range(hstart,hend,hbin):
                        painter.drawLine(x,vstart,x,vend)

                if vbin>1:
                    for y in range(vstart,vend,vbin):
                        painter.drawLine(hstart,y,hend,y)

        if self.overlay_enabled and self.show_bit_shift_region and self.bit_shift_region:
            shift_vstart, shift_vend = self.bit_shift_region

            shift_vstart = max(0, min(256, shift_vstart))
            shift_vend = max(0, min(256, shift_vend))

            if shift_vend > shift_vstart:
                green_pen = QPen(Qt.green)
                green_pen.setWidth(2)
                painter.setPen(green_pen)

                painter.drawLine(0, shift_vstart, self.width(), shift_vstart)
                painter.drawLine(0, shift_vend, self.width(), shift_vend)


class RulerContainer(QWidget):
    def __init__(self, preview_widget):
        """
        Wrap a 'PreviewWidget' with pixel-coordinate rulers on the left and top edges.
 
        Args:
            preview_widget: The 'PreviewWidget' instance to embed.
        """
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
        """
        Draw horizontal (top) and vertical (left) pixel-coordinate rulers.
 
        Tick marks and labels are rendered relative to the embedded preview
        widget's geometry.  The x-axis uses a 256-pixel step; the y-axis uses
        a 64-pixel step.  Axis titles ("Horizontal Pixel" / "Vertical Pixel")
        are also drawn.
 
        Args:
            event: QPaintEvent from the Qt framework.
        """
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

        painter.drawText(image_rect.center().x() - 30, image_rect.top() - 30, "Horizontal Pixel")

        # ---------- Y axis (LEFT) ----------
        step_y = 64
        for y in range(0, detector_h + 1, step_y):
            py = image_rect.top() + int(
                y * image_rect.height() / detector_h
            )

            painter.drawLine(image_rect.left() + 6, py,
                            image_rect.left(), py)

            painter.drawText(5, py + 5, str(y))

        painter.save()
        painter.translate(18, image_rect.center().y() + 30)
        painter.rotate(-90)
        painter.drawText(image_rect.center().x() - image_rect.center().x() - 10, 30, "Vertical Pixel")
        painter.restore()

class QNoScrollComboBox(QComboBox):
    """
    A QComboBox that ignores mouse-wheel events to prevent accidental value changes.
    """

    def wheelEvent(self,event):
        """
        Ignore wheel events so the combo box value cannot be changed by scrolling.
 
        Args:
            event: QWheelEvent from the Qt framework.
        """
        event.ignore()


class CollapsibleSection(QWidget):
    def __init__(self, title):
        """
        Initialise a collapsible panel with a toggle button and a hidden content area.
 
        The panel starts collapsed.  Clicking the toggle button reveals or hides
        'content_area' and updates the arrow indicator accordingly.
 
        Args:
            title: Label text displayed on the toggle button.
        """
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
        """
        Expand or collapse the content area and update the arrow direction.
 
        Called automatically when the toggle button is clicked.
        """
        expanded = self.toggle_button.isChecked()
        self.toggle_button.setArrowType(
            Qt.DownArrow if expanded else Qt.RightArrow
        )
        self.content_area.setVisible(expanded)

    def setContentLayout(self, content_layout):
        """
        Set the layout that populates the collapsible content area.
 
        Args:
            content_layout: Any QLayout instance to install in 'content_area'.
        """
        self.content_area.setLayout(content_layout)

# ---- READ MODE WIDGETS ----

class MultiTrackWidget(QWidget):
    """
    Read-mode configuration widget for multi-track acquisition.
 
    Number is the number of rows (or row sets) to read, height is the number
    of rows in one row set (1 for a single row), offset is the distance between
    row sets.  Returns a dict with keys 'number', 'height', and 'offset'.
    """

    def __init__(self):
        """
        Build the multi-track settings form with three integer input fields.
        """
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

    def get_params(self):
        """
        Collect the multi-track settings entered by the user.
 
        Returns:
            dict: Keys are 'mode' (always 'multi_track'), and optionally
            'number', 'height', and 'offset' if the fields are non-empty.
        """
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

    """
    Read-mode configuration widget for single-track acquisition.
 
    Center and width specify the selection of rows to be averaged together.
    """
    
    def __init__(self):
        """
        Build the single-track settings form with center and width input fields.
        """
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

    def get_params(self):
        """
        Collect the single-track settings entered by the user.
 
        Returns:
            dict: Keys are 'mode' (always 'single_track'), and optionally
            'center' and 'width' if the fields are non-empty.
        """
        params = {"mode": "single_track"}
        center, width = self.center_input.text(), self.width_input.text()
        if center != "":
            params["center"] = center
        if width != "":
            params["width"] = width
        return params

class FVBWidget(QWidget):
    """
    Read-mode configuration widget for Full-Vertical-Binning (FVB) mode.
 
    No user-configurable parameters are needed; all detector rows are binned
    into a single output row automatically.
    """
    def __init__(self):
        """
        Initialise the FVB widget (no controls required).
        """
        super().__init__()

    def get_params(self):
        """
        Return the FVB mode identifier.
 
        Returns:
            dict: {'mode': 'fvb'}.
        """
        params = {"mode": "fvb"}
        return params

class ImageWidget(QWidget):
    """
    Read-mode configuration widget for full-image (2-D) acquisition.
 
    Exposes ROI preset selection, manual ROI bounds, a processing-mode switcher
    (binning vs. bit-shift correction), binning presets, and the bit-shift
    row region controls.
 
    Signals:
        roi_visual_changed(roi, show_roi, show_grid, bit_shift_vstart,
                           bit_shift_vend, show_bit_shift):
            Emitted whenever any ROI-related field changes, so the
            'PreviewWidget' overlay can be updated.
        bit_shift_region_changed(vstart, vend):
            Re-emitted when the bit-shift row region changes.
    """
    roi_visual_changed = pyqtSignal(tuple, bool, bool, object, object, bool)
    bit_shift_region_changed = pyqtSignal(object, object)

    def __init__(self):
        """
        Build the image ROI / binning / bit-shift configuration panel.
 
        Wires all input fields and checkboxes to 'emit_visual_update' so that
        the preview overlay stays in sync, and connects the processing-mode
        combo box to 'update_processing_ui' to toggle visible sub-widgets.
        """
        super().__init__()

        layout = QVBoxLayout(self)
        label = QLabel("Image ROI settings")
        layout.addWidget(label)

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

        layout.addWidget(QLabel("Processing Mode"))
        self.processing_mode_input = QNoScrollComboBox()
        self.processing_mode_input.addItems(["bit_shift", "binning"])
        self.processing_mode_input.setCurrentText("binning")
        layout.addWidget(self.processing_mode_input)

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

        self.show_bit_shift_region_checkbox = QCheckBox("Show bit-shift region")
        layout.addWidget(self.show_bit_shift_region_checkbox)

        self.bit_shift_pixels_input = QLineEdit()
        self.bit_shift_pixels_input.setPlaceholderText("Bit shift left by N pixels")
        self.bit_shift_pixels_input.setValidator(QIntValidator())
        layout.addWidget(self.bit_shift_pixels_input)

        self.bit_shift_vstart_input = QLineEdit()
        self.bit_shift_vstart_input.setPlaceholderText("Bit shift row start")
        self.bit_shift_vstart_input.setValidator(QIntValidator())
        layout.addWidget(self.bit_shift_vstart_input)

        self.bit_shift_vend_input = QLineEdit()
        self.bit_shift_vend_input.setPlaceholderText("Bit shift row end")
        self.bit_shift_vend_input.setValidator(QIntValidator())
        layout.addWidget(self.bit_shift_vend_input)

        self.binning_widgets = [
            self.show_grid_checkbox,
            self.bin_preset_input,
            self.roi_hbin_input,
            self.roi_vbin_input,
        ]

        self.bit_shift_widgets = [
            self.bit_shift_pixels_input,
            self.bit_shift_vstart_input,
            self.bit_shift_vend_input,
            self.show_bit_shift_region_checkbox,
        ]

        self.roi_preset_input.currentTextChanged.connect(self.apply_roi_preset)
        self.bin_preset_input.currentTextChanged.connect(self.apply_bin_preset)
        for field in [self.roi_hstart_input,self.roi_hend_input,self.roi_vstart_input,self.roi_vend_input,self.roi_hbin_input,self.roi_vbin_input]:
            field.textChanged.connect(self.emit_visual_update)
        self.show_roi_checkbox.stateChanged.connect(self.emit_visual_update)
        self.show_grid_checkbox.stateChanged.connect(self.emit_visual_update)

        self.processing_mode_input.currentTextChanged.connect(self.update_processing_ui)
        self.update_processing_ui(self.processing_mode_input.currentText())

        self.show_bit_shift_region_checkbox.stateChanged.connect(self.on_toggle_bit_shift_region)

        self.bit_shift_pixels_input.textChanged.connect(self.emit_visual_update)
        self.bit_shift_vstart_input.textChanged.connect(self.emit_visual_update)
        self.bit_shift_vend_input.textChanged.connect(self.emit_visual_update)
        self.processing_mode_input.currentTextChanged.connect(self.emit_visual_update)

    def update_processing_ui(self, mode):
        """
        Show or hide sub-widgets based on the selected processing mode.
 
        In 'binning' mode the binning controls are visible and the
        bit-shift controls are hidden (and hbin/vbin inputs are enabled).
        In 'bit_shift' mode the reverse applies and hbin/vbin are forced to 1.
 
        Args:
            mode: Currently selected processing mode string – 'binning'
                  or 'bit_shift'.
        """
        use_binning = (mode == "binning")

        for w in self.binning_widgets:
            w.setVisible(use_binning)

        for w in self.bit_shift_widgets:
            w.setVisible(not use_binning)

        self.roi_hbin_input.setEnabled(use_binning)
        self.roi_vbin_input.setEnabled(use_binning)

        self.bit_shift_pixels_input.setEnabled(not use_binning)
        self.bit_shift_vstart_input.setEnabled(not use_binning)
        self.bit_shift_vend_input.setEnabled(not use_binning)

        if not use_binning:
            self.roi_hbin_input.setText("1")
            self.roi_vbin_input.setText("1")

        self.emit_visual_update()

    def emit_visual_update(self):
        """
        Read all ROI and overlay fields and emit 'roi_visual_changed'.
 
        Silently ignores conversion errors (e.g. empty fields) so that the
        signal is not emitted with invalid data during partial user input.
        """
        try:
            roi = (
                int(self.roi_hstart_input.text() or 0),
                int(self.roi_hend_input.text() or 0),
                int(self.roi_vstart_input.text() or 0),
                int(self.roi_vend_input.text() or 0),
                int(self.roi_hbin_input.text() or 1),
                int(self.roi_vbin_input.text() or 1)
            )
            bit_shift_vstart = int(self.bit_shift_vstart_input.text()) if self.bit_shift_vstart_input.text() else None
            bit_shift_vend = int(self.bit_shift_vend_input.text()) if self.bit_shift_vend_input.text() else None

            self.roi_visual_changed.emit(
                roi,
                self.show_roi_checkbox.isChecked(),
                self.show_grid_checkbox.isChecked(),
                bit_shift_vstart,
                bit_shift_vend,
                self.show_bit_shift_region_checkbox.isChecked()
            )

        except:
            pass

    def on_toggle_bit_shift_region(self,state):
        """
        Populate default bit-shift row bounds when the region is first enabled.
 
        If the user enables the "Show bit-shift region" checkbox but neither
        'vstart' nor 'vend' has been entered, sensible defaults are written
        to the input fields (centred on the detector with a ±10 row half-height).
 
        Args:
            state: Checkbox state integer from Qt (non-zero = checked).
        """
        if state:

            vstart = self.bit_shift_vstart_input.text()
            vend = self.bit_shift_vend_input.text()

            if not vstart or not vend:

                center = 256 // 2
                half = 10

                vstart = center - half
                vend = center + half

                self.bit_shift_vstart_input.setText(str(vstart))
                self.bit_shift_vend_input.setText(str(vend))

        self.emit_visual_update()


    def apply_roi_preset(self, text):
        """
        Fill the ROI input fields with centred coordinates for a standard size preset.
 
        Has no effect when 'text' is 'Custom'.
 
        Args:
            text: Preset label string (e.g. '512x128'), or 'Custom'.
        """
        if text == "Custom":
            return

        full_w = 1024
        full_h = 256

        roi_w, roi_h = map(int, text.split("x"))

        hstart = (full_w - roi_w) // 2
        vstart = (full_h - roi_h) // 2
        hend = hstart + roi_w
        vend = vstart + roi_h

        self.roi_hstart_input.setText(str(hstart))
        self.roi_hend_input.setText(str(hend))
        self.roi_vstart_input.setText(str(vstart))
        self.roi_vend_input.setText(str(vend))


    def apply_bin_preset(self, text):
        """
        Fill the horizontal and vertical bin input fields from a standard preset.
 
        Has no effect when 'text' is 'Custom'.
 
        Args:
            text: Preset label string (e.g. '2x2'), or 'Custom'.
        """
        if text == "Custom":
            return

        hbin, vbin = map(int, text.split("x"))
        self.roi_hbin_input.setText(str(hbin))
        self.roi_vbin_input.setText(str(vbin))

    def get_params(self):
        """
        Collect all image-mode settings from the form inputs.
 
        Returns:
            dict: Contains 'mode' ('image'), ROI bounds ('hstart',
            'hend', 'vstart', 'vend'), binning ('hbin', 'vbin'),
            'processing_mode', and the three bit-shift fields
            ('bit_shift_pixels', 'bit_shift_vstart', 'bit_shift_vend').
        """
        params = {"mode": "image"}
        params["hstart"] = self.roi_hstart_input.text()
        params["hend"] = self.roi_hend_input.text()
        params["vstart"] = self.roi_vstart_input.text()
        params["vend"] = self.roi_vend_input.text()
        params["hbin"] = self.roi_hbin_input.text() or "1"
        params["vbin"] = self.roi_vbin_input.text() or "1"

        params["processing_mode"] = self.processing_mode_input.currentText()
        params["bit_shift_pixels"] = self.bit_shift_pixels_input.text() or "0"
        params["bit_shift_vstart"] = self.bit_shift_vstart_input.text()
        params["bit_shift_vend"] = self.bit_shift_vend_input.text()
        return params

class RandomTrackWidget(QWidget):
    """
    Read-mode configuration widget for random-track acquisition.
 
    Allows the user to specify a single arbitrary row span (start / stop).
    """
    def __init__(self):
        """
        Build the random-track settings form with start and stop integer inputs.
        """
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
        """
        Collect the random-track row span entered by the user.
 
        Returns:
            dict: Keys are 'mode' (always 'random_track'), and optionally
            'start' and 'stop' if the fields are non-empty.
        """
        params = {"mode": "random_track"}
        start, stop = self.start_input.text(), self.stop_input.text()
        if start != "":
            params["start"] = start
        if stop != "":
            params["stop"] = stop
        return params


# ---- ACQUISITION MODE WIDGETS ----

class AccumWidget(QWidget):
    """
    Acquisition-mode configuration widget for accumulation mode.
 
    'num_acc' is the number of frames to accumulate on-chip;
    'cycle_time_acc' is the acquisition period (defaults to the minimum
    possible value based on exposure and transfer time).
    """

    def __init__(self):
        """
        Build the accumulation mode settings form.
        """
        super().__init__()
        layout = QVBoxLayout(self)
        label = QLabel("Accumulative Aquisition Mode Settings")

        self.num_acc_input = QLineEdit()
        self.num_acc_input.setPlaceholderText("Number of Accumulated frames")
        self.num_acc_input.setValidator(QIntValidator())

        self.cycle_time_acc_input = QLineEdit()
        self.cycle_time_acc_input.setPlaceholderText("Aquisition Period (s)")
        self.cycle_time_acc_input.setValidator(QDoubleValidator())

        self.result_mode_input = QNoScrollComboBox()
        self.result_mode_input.addItems(["sum", "avg"])

        layout.addWidget(label)
        layout.addWidget(self.num_acc_input)
        layout.addWidget(self.cycle_time_acc_input)
        layout.addWidget(QLabel("Result Processing"))
        layout.addWidget(self.result_mode_input)

        self.num_acc_input.setMinimumWidth(0)
        self.cycle_time_acc_input.setMinimumWidth(0)

    def get_params(self):
        """
        Collect the accumulation mode settings entered by the user.
 
        Returns:
            dict: Keys are 'mode' (always 'accum'), 'result_mode',
            and optionally 'num_acc' and 'cycle_time_acc' if non-empty.
        """
        params = {"mode": "accum"}
        num_acc = self.num_acc_input.text()
        cycle_time_acc = self.cycle_time_acc_input.text()

        if num_acc != "":
            params["num_acc"] = num_acc
        if cycle_time_acc != "":
            params["cycle_time_acc"] = cycle_time_acc
        params["result_mode"] = self.result_mode_input.currentText()

        return params

class KineticWidget(QWidget):
    """
    Acquisition-mode configuration widget for kinetic series mode.
 
    'num_cycle' is the number of kinetic cycles;
    'cycle_time' is the acquisition period between accumulation frames;
    'num_accum' is the number of accumulated frames per cycle;
    'cycle_time_acc' is the accumulation acquisition period;
    'num_prescan' is the number of pre-scan frames.
    """

    def __init__(self):
        """
        Build the kinetic series settings form.
        """
        super().__init__()
        layout = QVBoxLayout(self)
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

        self.result_mode_input = QNoScrollComboBox()
        self.result_mode_input.addItems(["sum", "avg"])

        layout.addWidget(label)
        layout.addWidget(self.num_cycle_input)
        layout.addWidget(self.cycle_time_input)
        layout.addWidget(self.num_acc_input)
        layout.addWidget(self.cycle_time_acc_input)
        layout.addWidget(self.num_prescan)
        layout.addWidget(QLabel("Result Processing"))
        layout.addWidget(self.result_mode_input)

    def get_params(self):
        """
        Collect the kinetic series settings entered by the user.
 
        Returns:
            dict: Keys are 'mode' (always 'kinetic'), 'result_mode',
            and optionally 'num_cycle', 'cycle_time', 'num_acc',
            'cycle_time_acc', and 'num_prescan' if their fields are non-empty.
        """
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
        params["result_mode"] = self.result_mode_input.currentText()
    
        return params
    
class FastKineticWidget(QWidget):
    """
    Acquisition-mode configuration widget for fast-kinetic mode.
 
    'num_acc' is the number of frames in the burst;
    'cycle_time_acc' is the acquisition period (defaults to the minimum
    possible based on exposure and transfer time).
    """

    def __init__(self):
        """
        Build the fast-kinetic mode settings form.
        """
        super().__init__()
        layout = QVBoxLayout(self)
        label = QLabel("Fast Kinetic Aquisition Mode Settings")

        self.num_acc_input = QLineEdit()
        self.num_acc_input.setPlaceholderText("Number of Accumulated frames")
        self.num_acc_input.setValidator(QIntValidator())

        self.cycle_time_acc_input = QLineEdit()
        self.cycle_time_acc_input.setPlaceholderText("Aquisition Period (s)")
        self.cycle_time_acc_input.setValidator(QDoubleValidator())

        self.result_mode_input = QNoScrollComboBox()
        self.result_mode_input.addItems(["sum", "avg"])

        layout.addWidget(label)
        layout.addWidget(self.num_acc_input)
        layout.addWidget(self.cycle_time_acc_input)
        layout.addWidget(QLabel("Result Processing"))
        layout.addWidget(self.result_mode_input)

    def get_params(self):
        """
        Collect the fast-kinetic mode settings entered by the user.
 
        Returns:
            dict: Keys are 'mode' (always 'fast_kinetic'), 'result_mode',
            and optionally 'num_acc' and 'cycle_time_acc' if non-empty.
        """
        params = {"mode": "fast_kinetic"}
        num_acc = self.num_acc_input.text()
        cycle_time_acc = self.cycle_time_acc_input.text()
        if num_acc != "":
            params["num_acc"] = num_acc
        if cycle_time_acc != "":
            params["cycle_time_acc"] = cycle_time_acc
        params["result_mode"] = self.result_mode_input.currentText()

        return params

class ContinuousWidget(QWidget):
    """
    Acquisition-mode configuration widget for continuous (video) mode.
 
    'cycle_time' is the acquisition period (defaults to the minimum possible
    based on exposure and transfer time).
    """
    
    def __init__(self):
        """
        Build the continuous mode settings form with a single cycle-time input.
        """
        super().__init__()
        layout = QHBoxLayout(self)
        label = QLabel("Continuous Acquisition Mode Settings")

        self.cycle_time = QLineEdit()
        self.cycle_time.setPlaceholderText("Acquisition Period (s)")
        self.cycle_time.setValidator(QDoubleValidator())


    def get_params(self):
        """
        Collect the continuous mode settings entered by the user.
 
        Returns:
            dict: Keys are 'mode' (always 'cont'), and optionally
            'cycle_time' if the field is non-empty.
        """
        params = {"mode": "cont"}
        cycle_time = self.cycle_time.text()
        if cycle_time != "":
            params["cycle_time"] = cycle_time
        return params

class SingleWidget(QWidget):
    """
    Acquisition-mode configuration widget for single-frame mode.
 
    No parameters are required; one frame is captured per trigger event.
    """
    def __init__(self):
        """
        Initialise the single-frame widget (no controls required).
        """
        super().__init__()

    def get_params(self):
        """
        Return the single-frame mode identifier.
 
        Returns:
            dict: '{"mode": "single"}'.
        """
        params = {"mode": "single"}
        return params
