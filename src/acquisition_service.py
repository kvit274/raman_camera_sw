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
        # acquisiton settings
        self.acquisition_settings = None
        # default paths:
        self.save_path_csv = Path("./data/csv")
        self.save_path_csv.mkdir(parents=True,exist_ok=True)
        self.save_path_image = Path("./data/images")
        self.save_path_image.mkdir(parents=True,exist_ok=True)
        self.save_path = Path("./data")
        self.save_path.mkdir(parents=True,exist_ok=True)

    def get_save_path(self):
        return self.save_path

    def set_save_frame_path(self,path):
        # validation TOD0
        self.save_path = path
        self.save_path_image = path
        self.save_path_csv = path

    def combine_frames(self,frames,acq_mode="single",num_frames=1,result_mode="sum"):
        # --- Normalize frames to list ---
        if isinstance(frames, np.ndarray):
            frames = [frames]

        # --- Combine frames correctly ---
        if acq_mode in ["kinetic", "fast_kinetic"]:
            # multiple independent frames
            combined = np.sum(frames, axis=0)

            if result_mode == "avg":
                combined = combined / num_frames

        else:
            # single OR accum
            frame = frames[-1]

            if acq_mode == "accum":

                if result_mode == "avg":
                    frame = frame / num_frames

            combined = frame

        return combined
    
    def convert_to_spectrum(self,frame, roi):
        # should consider binning>1 how to display?

        hstart, hend, vstart, vend, hbin, vbin = roi

        if frame.ndim == 2:
            y = frame.mean(axis=0)

        else:
            y = frame.copy()

        x_detector = np.arange(hstart,hend,hbin,dtype=float)

        if len(x_detector) != len(y):
            raise ValueError(f"x/y lenght missmatch: len(x):{len(x_detector)}, len(y)={len(y)}")
        
        return x_detector, y

        # spectrum = np.zeros(1024, dtype=local_spectrum.dtype)
        # spectrum[hstart:hend] = local_spectrum[:hend-hstart]
        # spectrum = spectrum[:1024]
        # spectrum[:hstart] = 0
        # spectrum[hend:] = 0

        # return spectrum
    
    def build_pixel_intensity_data(self, combined_frame, roi):
        hstart, hend, vstart, vend, hbin, vbin = roi

        pixel = np.arange(hstart, hend, hbin, dtype=int) + 1

        frame = np.asarray(combined_frame)

        if frame.ndim == 1:
            intensities = frame.reshape(-1, 1)
        elif frame.ndim == 2:
            # one CSV row per detector pixel
            intensities = frame.T
        else:
            raise ValueError(f"Unsupported frame ndim: {frame.ndim}")

        if len(pixel) != intensities.shape[0]:
            raise ValueError(
                f"pixel/frame mismatch: len(pixel)={len(pixel)}, "
                f"intensity_rows={intensities.shape[0]}"
            )

        return pixel, intensities

    def bit_shift(self, frames):
        shifted_frames = []

        for frame in frames:
            if frame.ndim == 2:
                frame_copy = frame.copy()
                frame_copy[-1, :] = np.roll(frame_copy[-1, :], -1)
                shifted_frames.append(frame_copy)
            else:
                shifted_frames.append(frame)

        return shifted_frames

    def adjust_frame(self,frame):
        m = frame.max()
        if m == 0:
            frame8 = np.zeros_like(frame,dtype=np.uint8)
        else:
            frame8 = (frame / frame.max() * 255).astype(np.uint8)   # 8bit grayscale
        h, w = frame8.shape
        return (frame8,h,w)
    
    def expand_fvb_frame(self, frame):
        frame = np.asarray(frame)

        if frame.ndim == 1:
            frame = frame[np.newaxis, :]

        if frame.ndim == 2 and frame.shape[0] == 1:
            return np.repeat(frame, 256, axis=0)

        return frame


    def save_npz(self,spectrum_data, metadata=None,filename=None):
        """
        Save spectrogram + metadata to NPZ format
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
        if combined_frame is None:
            raise RuntimeError("No frame to save")

        pixel, intensities = self.build_pixel_intensity_data(combined_frame, roi)

        data = np.column_stack((pixel, intensities))

        if filename is None:
            filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

        csv_path = self.save_path / filename.replace(".npz", ".csv")

        np.savetxt(csv_path, data, delimiter=",", fmt="%d")
        print(f"[SAVE] CSV saved to {csv_path}")

    def save_frames(self,frames,filename=None):     # should handle saving mulitiple files without overwritin files
        """
        Save a single acquired frame as PNG + raw CSV
        """

        if frames is None:
            raise RuntimeError("No frames to save")

        if isinstance(frames,np.ndarray):
            frames = [frames]

        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            png_path = self.save_path / f"{timestamp}.png"
            # csv_path = self.save_path_csv / f"{timestamp}.csv"
        else:
            png_path = self.save_path / f"{filename.replace('.npz', '.png')}"
            # csv_path = self.save_path_csv / f"{filename.replace('.npz', '.csv')}"

        for idx,frame in enumerate(frames):

            if frame.size == 0:
                print("Empty frame")
                return

            plt.imsave(png_path, frame,cmap="gray")
            # np.savetxt(csv_path,frame,delimiter=",",fmt="%d")

        print(f"[SAVE] Frames saved to {png_path}")
        return
    
    def save_csv_frame(self,frame,filename):
        new_filename = filename
        csv_frame_path = self.save_path / f"{new_filename.replace('.npz','')}_frame.csv"
        np.savetxt(csv_frame_path,frame,delimiter=",",fmt="%d")

    def baseline_correct(self,spectrum,method="asls"):
        """
        RamanSPy baseline correction
        Returns: corrected baseline
        """

        y = np.asarray(spectrum, dtype=np.float64)

        sp = rp.Spectrum(y, spectral_axis=np.arange(len(y)))   # spectral_axis should be wavenumbers after callibration is mplemented

        if method == "asls":
            processor = rp.preprocessing.baseline.ASLS(lam=5000, p=0.007)
        elif method == "modpoly":
            processor = rp.preprocessing.baseline.ModPoly(poly_order=3)
        else:
            raise ValueError("Unsupported baseline method")

        corrected_sp = processor.apply(sp)

        corrected = np.asarray(corrected_sp.spectral_data)
        baseline = y - corrected

        # corrected = np.clip(corrected, 0, None)

        return corrected, baseline