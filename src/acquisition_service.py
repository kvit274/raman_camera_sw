import time
import json
import numpy as np
import pylablib as pll
from pylablib.devices import Andor
from pathlib import Path
import matplotlib.pyplot as plt
from pprint import pformat
from typing import Optional
from datetime import datetime
from functools import wraps
import ramanspy as rp

class AcquisitionService:

    def __init__(self):
        """
        Initialise the AcquisitionService and create default output directories
        (./data, ./data/csv, ./data/images) if they do not already exist.
        """
        self.acquisition_settings = None
        self.save_path_csv = Path("./data/csv")
        self.save_path_csv.mkdir(parents=True,exist_ok=True)
        self.save_path_image = Path("./data/images")
        self.save_path_image.mkdir(parents=True,exist_ok=True)
        self.save_path = Path("./data")
        self.save_path.mkdir(parents=True,exist_ok=True)

    def get_save_path(self):
        """Return the current root save directory as a Path object."""
        return self.save_path

    def set_save_frame_path(self,path):
        """
        Set the root save directory for all output files (images, CSV, NPZ).
 
        Args:
            path: New save directory (str or Path).
        """
        self.save_path = path
        self.save_path_image = path
        self.save_path_csv = path

    def combine_frames(self, frames, acq_mode="single", num_frames=1, result_mode="sum"):
        """
        Combine frames according to acquisition mode.

        For kinetic / fast_kinetic:
            frames contains multiple real frames, so sum/avg across frames.

        For accum:
            hardware accumulation returns one already-summed frame.
            sum = that frame
            avg = that frame / num_frames
        """
        if isinstance(frames, np.ndarray):
            frames = [frames]

        if not frames:
            raise RuntimeError("No frames to combine")

        frames = [np.asarray(f) for f in frames]

        if acq_mode == "accum":
            combined = frames[0]

            if result_mode == "avg":
                combined = combined.astype(np.float64) / num_frames

            return combined

        if acq_mode in ["kinetic", "fast_kinetic"]:
            combined = np.sum(
                [f.astype(np.float64) for f in frames],
                axis=0
            )

            if result_mode == "avg":
                combined = combined / num_frames

            return combined

        return frames[0]
    
    def convert_to_spectrum(self,frame, roi):
        """
        Collapse a 2-D detector frame into a 1-D spectrum by averaging over rows,
        and build the corresponding pixel-index x-axis from the ROI.
 
        Args:
            frame: 2-D ndarray (rows × pixels) or 1-D ndarray already collapsed.
            roi:   6-tuple (hstart, hend, vstart, vend, hbin, vbin) describing the
                   active detector region and binning.
 
        Returns:
            Tuple (x_detector, y) where x_detector is the pixel indices array and
            y is the intensity array.
 
        Raises:
            ValueError: If the length of x and y do not match.
        """
        hstart, hend, vstart, vend, hbin, vbin = roi

        if frame.ndim == 2:
            y = frame.mean(axis=0)

        else:
            y = frame.copy()

        x_detector = np.arange(hstart,hend,hbin,dtype=float)

        if len(x_detector) != len(y):
            raise ValueError(f"x/y lenght missmatch: len(x):{len(x_detector)}, len(y)={len(y)}")
        
        return x_detector, y

    
    def build_pixel_intensity_data(self, combined_frame, roi):
        """
        Build a pixel-index array and a matching intensity matrix suitable for CSV export.
 
        Each row of the returned intensity matrix corresponds to one detector pixel;
        columns correspond to separate accumulations/scans when the frame is 2-D.
 
        Args:
            combined_frame: 1-D or 2-D ndarray of acquired intensity data.
            roi:            6-tuple (hstart, hend, vstart, vend, hbin, vbin).
 
        Returns:
            Tuple (pixel, intensities) where pixel is a 1-D int array of 1-based pixel
            indices and intensities is a 2-D ndarray of shape (n_pixels, n_columns).
 
        Raises:
            ValueError: If frame dimensions are not 1 or 2, or if pixel/frame length mismatch.
        """
        hstart, hend, vstart, vend, hbin, vbin = roi

        pixel = np.arange(hstart, hend, hbin, dtype=int) + 1

        frame = np.asarray(combined_frame)

        if frame.ndim == 1:
            intensities = frame.reshape(-1, 1)
        elif frame.ndim == 2:
            intensities = frame.T
        else:
            raise ValueError(f"Unsupported frame ndim: {frame.ndim}")

        if len(pixel) != intensities.shape[0]:
            raise ValueError(
                f"pixel/frame mismatch: len(pixel)={len(pixel)}, "
                f"intensity_rows={intensities.shape[0]}"
            )

        return pixel, intensities

    def bit_shift(self, frames, roi, shift_pixels=0, shift_vstart=None, shift_vend=None):
        """
        Apply a horizontal pixel shift to a sub-region of each frame to correct for
        spectral offset introduced by the readout electronics.
 
        The shift is only applied when hbin == vbin == 1 and the frame is 2-D.
        Rows outside [shift_vstart, shift_vend] are left unchanged.
 
        Args:
            frames:         List of 2-D ndarrays.
            roi:            6-tuple (hstart, hend, vstart, vend, hbin, vbin).
            shift_pixels:   Number of pixels to shift (negative = left).  0 = no-op.
            shift_vstart:   First detector row (absolute) to include in the shift region.
            shift_vend:     Last detector row (exclusive, absolute) of the shift region.
 
        Returns:
            List of ndarrays with the shift applied.
        """
        shifted_frames = []

        hstart, hend, roi_vstart, roi_vend, hbin, vbin = roi

        for frame in frames:
            frame = np.asarray(frame)

            if frame.ndim != 2 or shift_pixels == 0:
                shifted_frames.append(frame)
                continue

            if hbin != 1 or vbin != 1:
                shifted_frames.append(frame)
                continue

            frame_copy = frame.copy()
            frame_h = frame_copy.shape[0]

            if shift_vstart is None:
                local_vstart = 0
            else:
                local_vstart = max(0, shift_vstart - roi_vstart)

            if shift_vend is None:
                local_vend = frame_h
            else:
                local_vend = min(frame_h, shift_vend - roi_vstart)

            if local_vend > local_vstart:
                print(f"shifting!")
                frame_copy[local_vstart:local_vend, :] = np.roll(
                    frame_copy[local_vstart:local_vend, :],
                    -shift_pixels,
                    axis=1
                )

            shifted_frames.append(frame_copy)

        return shifted_frames

    def adjust_frame(self,frame):
        """
        Normalise a raw detector frame to 8-bit grayscale for display purposes.
 
        Args:
            frame: 2-D ndarray with arbitrary integer or float dtype.
 
        Returns:
            Tuple (frame8, h, w) where frame8 is a uint8 ndarray, h is the number
            of rows and w is the number of columns.
        """
        m = frame.max()
        if m == 0:
            frame8 = np.zeros_like(frame,dtype=np.uint8)
        else:
            frame8 = (frame / frame.max() * 255).astype(np.uint8) 
        h, w = frame8.shape
        return (frame8,h,w)

    def save_npz(self,spectrum_data, metadata=None,filename=None):
        """
        Save a spectrum (x, y arrays) and optional metadata dict to a NumPy NPZ file.
 
        Args:
            spectrum_data: Tuple (x, y) of 1-D ndarrays.
            metadata:      Optional dict to store alongside the spectrum.
            filename:      Output filename including extension.  If None a timestamp-based
                           name is generated automatically.
 
        Raises:
            RuntimeError: If spectrum_data is None.
        """
        if spectrum_data is None:
            raise RuntimeError("No spectrum to save")

        x,y = spectrum_data

        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            spe_path = self.save_path / f"{timestamp}.npz"
        else:
            spe_path = self.save_path / f"{filename}"

        np.savez(spe_path, pixel=x, spectrum=y, metadata=metadata if metadata else {})
        print(f"[SAVE] Spectrogram saved to {spe_path}")
        return

    def save_csv(self, combined_frame, roi, filename=None):
        """
        Save a combined frame as a CSV file with one row per detector pixel.
 
        The first column contains the 1-based pixel index; subsequent columns contain
        intensity values (one column per accumulation when the frame is 2-D).
 
        Args:
            combined_frame: 1-D or 2-D ndarray of intensity data.
            roi:            6-tuple (hstart, hend, vstart, vend, hbin, vbin).
            filename:       Output filename.  If None a timestamp-based name is used.
                            A '.npz' extension is automatically replaced with '.csv'.
 
        Raises:
            RuntimeError: If combined_frame is None.
        """
        if combined_frame is None:
            raise RuntimeError("No frame to save")

        pixel, intensities = self.build_pixel_intensity_data(combined_frame, roi)

        data = np.column_stack((pixel, intensities))

        if filename is None:
            filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

        csv_path = self.save_path / filename.replace(".npz", ".csv")

        np.savetxt(csv_path, data, delimiter=",", fmt="%d")
        print(f"[SAVE] CSV saved to {csv_path}")

    def save_image(self,frames,filename=None): 
        """
        Save one or more detector frames as a grayscale PNG file.
 
        Args:
            frames:   Single ndarray or list of ndarrays.  Each frame must be 2-D
                      (or 1-D, in which case it is reshaped to (1, width)).
            filename: Output filename.  If None a timestamp-based name is used.
                      A '.npz' extension is automatically replaced with '.png'.
 
        Raises:
            RuntimeError: If frames is None.
            ValueError:   If a frame has an unsupported number of dimensions.
        """

        if frames is None:
            raise RuntimeError("No frames to save")

        if isinstance(frames,np.ndarray):
            frames = [frames]

        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            png_path = self.save_path / f"{timestamp}.png"
        else:
            png_path = self.save_path / f"{filename.replace('.npz', '.png')}"

        if isinstance(frames,list) and len(frames) == 1 and isinstance(frames[0],list):
            frames = frames[0]

        for frame in frames:
            frame = np.asarray(frame)

            if frame.ndim == 1:
                frame = frame[np.newaxis, :]

            if frame.ndim != 2:
                raise ValueError(f"Invalid frame shape: {frame.shape}")

            if frame.dtype != np.uint8:
                m = frame.max()
                frame = (frame/m*255).astype(np.uint8) if m != 0 else frame.astype(np.uint8)

            plt.imsave(png_path, frame,cmap="gray")

        print(f"[SAVE] Frames saved to {png_path}")
        return
    
    # UNUSED
    def baseline_correct(self,spectrum,method="asls"):
        """
        RamanSPy baseline correction
        Returns: corrected baseline
        """

        y = np.asarray(spectrum, dtype=np.float64)

        sp = rp.Spectrum(y, spectral_axis=np.arange(len(y)))

        if method == "asls":
            processor = rp.preprocessing.baseline.ASLS(lam=5000, p=0.007)
        elif method == "modpoly":
            processor = rp.preprocessing.baseline.ModPoly(poly_order=3)
        else:
            raise ValueError("Unsupported baseline method")

        corrected_sp = processor.apply(sp)

        corrected = np.asarray(corrected_sp.spectral_data)
        baseline = y - corrected

        return corrected, baseline
    
    def expand_frame_for_display(self, frame, roi, read_mode):
        """
        Up-sample a binned or FVB frame so it fills the full ROI pixel dimensions,
        making it suitable for on-screen display at the correct aspect ratio.
 
        For FVB mode the single row is stretched horizontally to roi_w and repeated
        roi_h times.  For image mode with binning each source pixel is mapped to the
        nearest ROI pixel via linear index interpolation.
 
        Args:
            frame:     ndarray coming directly from the camera (possibly binned).
            roi:       6-tuple (hstart, hend, vstart, vend, hbin, vbin).
            read_mode: String describing the camera read mode ('fvb' or 'image').
 
        Returns:
            2-D ndarray of shape (roi_h, roi_w) ready for display.
        """
        frame = np.asarray(frame)
        hstart, hend, vstart, vend, hbin, vbin = roi

        roi_w = hend - hstart
        roi_h = vend - vstart

        # ---------- FVB ----------
        if read_mode == "fvb":
            if frame.ndim == 1:
                frame = frame.reshape(1, -1)
            elif frame.ndim == 2 and frame.shape[1] == 1 and frame.shape[0] > 1:
                frame = frame.T

            if frame.ndim == 2 and frame.shape[0] == 1:
                src_h, src_w = frame.shape
                x_idx = np.linspace(0, src_w - 1, roi_w).astype(int)
                expanded = frame[:, x_idx]
                expanded = np.repeat(expanded, roi_h, axis=0)
                return expanded

            return frame

        # ---------- IMAGE ----------
        if read_mode == "image" and frame.ndim == 2:
            if hbin == 1 and vbin == 1:
                return frame

            src_h, src_w = frame.shape

            y_idx = np.linspace(0, src_h - 1, roi_h).astype(int)
            x_idx = np.linspace(0, src_w - 1, roi_w).astype(int)

            expanded = frame[y_idx][:, x_idx]
            return expanded

        return frame