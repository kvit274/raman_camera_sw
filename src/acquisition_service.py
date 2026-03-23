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
            spectrum = frame.sum(axis=0)

        else:
            spectrum = frame.copy()

        spectrum = spectrum[:1024]
        spectrum[:hstart] = 0
        spectrum[hend:] = 0

        return spectrum

    def bit_shift(self, frames):
        shifted_frames = []

        for frame in frames:
            if frame.ndim == 2:
                frame_copy = frame.copy()
                frame_copy[-1, :] = np.roll(frame_copy[-1, :], -2)
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

    def save_npz(self,spectrum, metadata=None,filename=None):
        """
        Save spectrogram + metadata to NPZ format
        """
        if spectrum is None:
            raise RuntimeError("No spectrum to save")

        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            spe_path = self.save_path / f"{timestamp}.npz"
        else:
            spe_path = self.save_path / f"{filename}"

        np.savez(spe_path, spectrum=spectrum, metadata=metadata if metadata else {})
        print(f"[SAVE] Spectrogram saved to {spe_path}")
        return

    def save_csv(self, spectrum, filename=None):
        """
        Save spectrum to CSV format
        """
        if spectrum is None:
            raise RuntimeError("No spectrum to save")

        pixels = np.arange(len(spectrum))
        if filename is None:
            filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        csv_path = self.save_path / filename.replace(".npz", ".csv")

        with open(csv_path, "w") as f:
            f.write("pixel,intensity,wavelength,wavenumber,processed\n")

            for p,i in zip(pixels, spectrum):
                f.write(f"{p},{i},,,\n")

        print(f"[SAVE] CSV saved to {csv_path}")
        return

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