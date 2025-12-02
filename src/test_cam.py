import time
import json
import numpy as np
import pylablib as pll
from pylablib.devices import Andor
from pathlib import Path
import matplotlib.pyplot as plt
from pprint import pformat


class TestCameraModel:
    def __init__(self):

        self.cam = None
        self.is_live = False    # if camera is capturing live images
        self.busy = False
        self.temp = 20.0  # current temperature

        # default paths:
        self.save_path = Path("./data")
        self.save_path.mkdir(exist_ok=True)




    # ===== CAMERA SETTINGS =====

    def connect_cam(self):
        """
        When connecting all the parameters are usually set in the slowest mode (amplifier,vertical/horizontal scan speed, etc.)
        Default shutter is ("closed")
        """
        self.cam = "Andor Newton"
    
    def get_cam_params(self,save_path=Path("./cam_params.txt")):
        """
        Collect and save camera parameters in readable format.
        """

        info = {}

        info["params"]="These are camera parameters"
        

        readable_text="=== Andor Newton Camera Parameters ===\n"
        readable_text+=pformat(info, indent=2, width=120)

        with open(save_path, "w") as f:
            f.write(readable_text)
        return
    
    def detect_cam_size(self):
        """
        Return tuple (width, height) pixels of the camera
        Not affected by ROI
        """
        return (128,256)
    
    def get_data_dim(self):
        """
        Returns the dimensions of the data (width,height) after binning and ROI
        """
        return (64,128)
    
    def set_default_settings(self):
        """
        Initializes default (safe) parameters for the camera
        (might delete in future)
        """
        print("Default camera settings applied")
        return


    # def set_cam_settings(self, exposure, hbin,vbin,read_mode,acq_mode,accum_n=None,roi=None):
    #     # self.cam.set_acquisition(
    #     #     exposure=exposure,
    #     #     hbin=hbin,
    #     #     vbin=vbin,
    #     #     read_mode=read_mode,
    #     #     acq_mode=acq_mode,
    #     # )
        
    #     # cfg = self._acq_cfg
    #     # cfg["exposure"] = exposure
    #     # cfg["hbin"] = hbin
    #     # cfg["vbin"] = vbin
    #     # cfg["read_mode"] = read_mode
    #     # cfg["acq_mode"] = acq_mode
    #     # cfg["accum_n"] = accum_n
    #     # cfg["roi"] = roi

    #     # self.cam.set_trigger_mode("int")  # internal trigger | exposure starts immediately

    #     self.cam.set_shutter(0, 0, "auto")  # fully electronic shutter


    #     self.cam.set_shutter(opening_time=0, closing_time=0)  # if no shutter
    #     # self.cam.set_shutter(0, 0, "open")  # fully electronic shutter

    #     self.cam.set_exposure(exposure)
    #     self.cam.set_read_mode(read_mode)

    #     if read_mode == "image":
    #         width, height = self.cam.get_detector_size()
    #         if roi is None:
    #             hstart, hend = 0, width
    #             vstart, vend = 0, height
    #         else:
    #             x,y,w_roi,h_roi = roi
    #             hstart, hend = x, x + w_roi
    #             vstart, vend = y, y + h_roi
            
    #         self.cam.setup_image_mode(
    #             hstart=hstart,
    #             hend=hend,
    #             vstart=vstart,
    #             vend=vend,
    #             hbin=hbin,
    #             vbin=vbin,
    #         )

    #     self.cam.set_acquisition_mode("single")

    #     # what?
    #     # set vertical shift speed
    #     vsspeeds = self.cam.get_vsspeeds()
    #     self.cam.set_vsspeed(vsspeeds[0])   # slowest = highest quality

    #     # set horizontal shift speed
    #     hsspeeds = self.cam.get_hsspeeds(0)
    #     self.cam.set_hsspeed(0, hsspeeds[0])  # amplifier index 0, slowest speed

    #     # pre amp gain
    #     gains = self.cam.get_preampgains()
    #     self.cam.set_preampgain(gains[1])  # medium gain recommended


    #     # acq_mode="single"   # 'single' | 'accumulate' | 'kinetic' | 'run_till_abort'
    #     # acq_mode = "run_till_abort" # run until stopped
    #     # acq_mode="accumulate" # might use for accumulate feature
    

    def set_roi(self,roi,hbin,vbin):
        print(f"ROI set to: {roi} with hbin: {hbin}, vbin: {vbin}")
    
    def cool_cam(self,target_temp=-80.0):
        self.busy = True
        self.cancel = False
        print(f"Cooling to {target_temp} C")
        
        self.temp = 20.0 # starting temp
        while True:
            if self.cancel:
                print("Cooling canceled")
                break

            self.temp -= 20
            print(f"Cooling: {self.temp}, Status: Stabilizing")

            if self.temp <= target_temp:
                print(f"Temperature stabilized, Status: Stabilized")
                break
            # if time.time() - t0 > time_out:
            #     raise RuntimeError("Cooling timeout")

            time.sleep(1)
        self.busy = False

    def warm_cam(self,safe_temp=-20):
        self.busy = True
        self.cancel = True

        print("Warming (cooler OFF)")
        self.temp = -80.0  # starting temp

        while True:
            print(f"Warming T = {self.temp} C")

            if self.temp >= safe_temp:
                break
            self.temp += 20
            time.sleep(1)

        self.busy = False

    def safe_close(self):
        """
        Turn off the cooler and wait until the temperature is at least -20
        Disconnect the camera
        """
        if not self.cam:
            return
        
        self.cancel=True
        
        # try:
        #     if self.cam.acquisition_in_progress():
        #         self.cam.stop_acquisition()
        # except:
        #     pass

        # self.warm_cam()
        
        self.close_cam()
        return

    def close_cam(self):
        if self.cam:
            print("Camera disconnected")
            self.cam = None
    
    def get_temp(self):
        if not self.cam:
            return "--",""
        
        return self.temp, "Some status"



    # ===== LIVE VIDEO =====

    def start_live(self):
        """
        Start capturing what camera sees until stop live is clicked.
        """
        if self.is_live or not self.cam:
            return
        self.is_live = True
    
        print("Live mode started")
        return

    def end_live(self):
        if not self.cam or not self.is_live:
            return

        print("Live mode stopped")
        return

    def get_live_frame(self):
        if self.cam is None or not self.is_live:
            print(f"Could not obtain the frame for the preview. Cam: {self.cam} | live state: {self.is_live}")
            return None
        
        frame = self.generate_fake_frame()
        return frame

    # ===== ACQUISITION =====

    def simple_acq(self,num_frames=0):
        if not self.cam:
            print("No camera detected for a snap")
            return None
        
        if self.is_live:
            self.end_live()

        if num_frames == 0:
            frame = self.generate_fake_frame()
            print("Single frame acquired")
            return frame
        else:
            frames = [self.generate_fake_frame() for _ in range(num_frames)]
            print("Multiple frames acquired")
            return frames


    
        


    # def aquire_frame(self):
    #     frames = self.cam.grab(nframes=1)

    #     if isinstance(frames, list):
    #         frame = frames[0]
    #     else:
    #         # For frame_format="array", 'frames' can be a 3D array
    #         frame = frames[0]
        
    #     frame = np.array(frame)

    #     if frame.ndim == 2:
    #         spectrum = frame.sum(axis=0).astype(np.int64)
    #     else:
    #         spectrum = frame.reshape(-1).astype(np.int64)

    #     return frame, spectrum

    # def acquire_single(self):
    #     self.cam.start_acquisition()
    #     print(f"Camera acquiring: {self.cam.get_attribute_value('CameraAcquiring')}") # check if the camera is acquiring
    #     frame = self.cam.wait_for_frame()
    #     spectrum = frame.sum(axis=0).astype(np.int32)   # turn raw 2D into 1D spectrum by summing the column pixels (more score -> brighter -> higher score)

    #     return frame, spectrum
    
    # def acquire_accumulate(self,n):
    #     self.cam.set_number_accumulations(n)
    #     self.cam.start_acquisition()
    #     frame = self.cam.wait_for_frame()
    #     spectrum = frame.sum(axis=0).astype(np.int32)
    #     return frame, spectrum
    
    # def acquire_rta(self):
    #     self.cam.start_acquisition()    
    #     try:
    #         while True:
    #             frame = self.cam.wait_for_frame(timeout=5.0)
    #             spectrum = frame.sum(axis=0).astype(np.int32)
    #     except KeyboardInterrupt:
    #         pass
    #     finally:
    #         self.cam.abort_acquisition()
    #         return frame, spectrum
        
    # def acquire_kinetic(self):
    #     # To do
    #     pass




    # ===== FILE MANAGEMENT =====

    def set_save_path(self,save_path):
        self.save_path = save_path
    
    def set_dlls_path(self,dlls_path):
        pll.par["devices/dll/andor_sdk2"] = dlls_path
    
    def save_data(self, frame, spectrum, timestamp):
        np.savetxt(self.save_path / f"{timestamp}_frame.csv", frame, delimiter=",", fmt="%d")   # save image
        np.savetxt(self.save_path / f"{timestamp}_spectrum.csv", spectrum, delimiter=",", fmt="%d")     # save spectrum
    
    # def save_meta(self, frame, exposure, hbin, vbin, roi, temp, timestamp):
    #     meta = {
    #         "camera_model": self.cam.get_model(),
    #         "serial": self.cam.get_serial_number(),
    #         "exposure_s": exposure,
    #         "binning": {"h": hbin, "v": vbin},
    #         "roi": roi,
    #         "cooling_setpoint_C": temp,
    #         "frame_shape": frame.shape,
    #         "timestamp": timestamp,
    #     }
    #     (self.save_path / f"meta_{timestamp}.json").write_text(json.dumps(meta, indent=2))

        # ask what to save??



    # ==== DISPLAY DATA =====

    def plot_spec(self,spectrum,exp_time):

        self.save_path.mkdir(parents=True, exist_ok=True)
        plt.figure()
        plt.plot(spectrum)
        plt.title("Spectrum")
        plt.savefig(self.save_path / f"{exp_time}_plot.png", dpi=200) # dpi is dots per inch -> more dots - better quality


    # ==== MATH =====
    def adjust_frame(self,frame):
        frame8 = (frame / frame.max() * 255).astype(np.uint8)   # 8bit grayscale
        h, w = frame8.shape
        return (frame8,h,w)

    def generate_fake_frame(self):
        base = np.linspace(0, 1, 256)
        gradient = np.tile(base, (128, 1))
        noise = np.random.normal(0, 0.05, size=(128, 256))
        frame = gradient + noise
        frame = np.clip(frame, 0, 1)
        return frame.astype(np.float32)