import time
import json
import numpy as np
import pylablib as pll
from pylablib.devices import Andor
from pathlib import Path
import matplotlib.pyplot as plt


class RamanCameraModel:
    def __init__(self):
        self.cam = None

        # default paths:
        self.save_path = Path("./data")
        self.save_path.mkdir(exist_ok=True)

    # ===== CAMERA SETTINGS =====

    def connect_cam(self):
        self.cam = Andor.AndorSDK2Camera()
        
        return self.cam.get_model()
    
    def set_cam_settings(self, exposure, hbin,vbin,read_mode,acq_mode):
        self.cam.set_acquisition(
            exposure=exposure,
            hbin=hbin,
            vbin=vbin,
            read_mode=read_mode,
            acq_mode=acq_mode,
        )
        # acq_mode="single"   # 'single' | 'accumulate' | 'kinetic' | 'run_till_abort'
        # acq_mode = "run_till_abort" # run until stopped
        # acq_mode="accumulate" # might use for accumulate feature

    def set_roi(self,roi,hbin,vbin):
        x,y,w,h = roi
        self.cam.set_roi(x,y,w,h,hbin=hbin,vbin=vbin)
    
    def cool_cam(self,temp):
        self.cam.set_cooling(True, temperature=temp)
        print(f"Cooling {self.cam.get_model()} to {temp}C°")
        while True:
            t = self.cam.get_temperature()
            if t == temp:
                print(f"Successfully cooled down to {temp}C°")
                break

    def close_cam(self):
        if self.cam:
            self.cam.close()
    
    # ===== ACQUISITION =====

    def acquire_single(self):
        self.cam.start_acquisition()
        print(f"Camera acquiring: {self.cam.get_attribute_value('CameraAcquiring')}") # check if the camera is acquiring
        frame = self.cam.wait_for_frame()
        spectrum = frame.sum(axis=0).astype(np.int32)   # turn raw 2D into 1D spectrum by summing the column pixels (more score -> brighter -> higher score)

        return frame, spectrum
    
    def acquire_accumulate(self,n):
        self.cam.set_number_accumulations(n)
        self.cam.start_acquisition()
        frame = self.cam.wait_for_frame()
        spectrum = frame.sum(axis=0).astype(np.int32)
        return frame, spectrum
    
    def acquire_rta(self):
        self.cam.start_acquisition()    
        try:
            while True:
                frame = self.cam.wait_for_frame(timeout=5.0)
                spectrum = frame.sum(axis=0).astype(np.int32)
        except KeyboardInterrupt:
            pass
        finally:
            self.cam.abort_acquisition()
            return frame, spectrum
        
    def acquire_kinetic(self):
        # To do
        pass

    # ===== FILE MANAGEMENT =====

    def set_save_path(self,save_path):
        self.save_path = save_path
    
    def set_dlls_path(self,dlls_path):
        pll.par["devices/dll/andor_sdk2"] = dlls_path
    
    def save_data(self, frame, spectrum, timestamp):
        np.savetxt(self.save_path / f"{timestamp}_frame.csv", frame, delimiter=",", fmt="%d")   # save image
        np.savetxt(self.save_path / f"{timestamp}_spectrum.csv", spectrum, delimiter=",", fmt="%d")     # save spectrum
    
    def save_meta(self, frame, exposure, hbin, vbin, roi, temp, timestamp):
        meta = {
            "camera_model": self.cam.get_model(),
            "serial": self.cam.get_serial_number(),
            "exposure_s": exposure,
            "binning": {"h": hbin, "v": vbin},
            "roi": roi,
            "cooling_setpoint_C": temp,
            "frame_shape": frame.shape,
            "timestamp": timestamp,
        }
        (self.save_path / f"meta_{timestamp}.json").write_text(json.dumps(meta, indent=2))

        # ask what to save??

    # ==== DISPLAY DATA =====

    def plot_spec(self,spectrum,exp_time):
        plt.figure()
        plt.plot(spectrum)
        plt.title("Spectrum")
        plt.savefig(self.save_path / f"{exp_time}_plot.png", dpi=200) # dpi is dots per inch -> more dots - better quality
