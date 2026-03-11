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

class TestCameraModel:
    def __init__(self):

        self.cam = None
        self.is_live = False    # if camera is capturing live images
        self.busy = False
        self.temp = 20.0  # current temperature

        # roi params
        self.hstart = 0
        self.hend = None
        self.vstart = 0
        self.vend = None
        self.hbin = 1
        self.vbin = 1

        # shutter params
        self.shutter_mode = "auto"
        self.ttl_mode = 0
        self.open_time = 5
        self.close_time = 5

        # Read mode
        self.read_mode = "image"

        # Acquisition mode
        self.acquisition_mode = "single"

        # Trigger mode
        self.trigger_mode = "int"

        # Exposure
        self.exposure = 1

        # Amp mode
        self.all_amp_modes = [
            TAmpModeFull(channel=1, bitdepth=16, oamp=1, oamp_kind="Standard", hsspeed=0.3, hsspeed_MHz=0.3, preamp=0, preamp_gain=1),
            TAmpModeFull(channel=1, bitdepth=16, oamp=2, oamp_kind="Standard", hsspeed=1.0, hsspeed_MHz=1.0, preamp=0, preamp_gain=1),
            TAmpModeFull(channel=1, bitdepth=16, oamp=3, oamp_kind="Standard", hsspeed=2.0, hsspeed_MHz=2.0, preamp=1, preamp_gain=1),
            TAmpModeFull(channel=1, bitdepth=16, oamp=4, oamp_kind="Standard", hsspeed=3.0, hsspeed_MHz=3.0, preamp=2, preamp_gain=1)
        ]
        self.amp_mode = TAmpModeFull(channel=1, bitdepth=16, oamp=1, oamp_kind="Standard", hsspeed=0.3, hsspeed_MHz=0.3, preamp=0, preamp_gain=1)

        # vsspeed
        self.all_vsspeeds =  [0.9,1.7,3.2,6.8,12.5]
        self.vsspeed = 1.7

        # EMCCD gain
        self.emccd_gain = 0

        # default paths:
        self.save_path_csv = Path("./data/csv")
        self.save_path_csv.mkdir(exist_ok=True)
        self.save_path_image = Path("./data/images")
        self.save_path_image.mkdir(exist_ok=True)
        self.save_path = Path("./data")
        self.save_path.mkdir(exist_ok=True)

        # transfer frame mode:
        self.enable_frame_transfer_mode = None


    # ==== DECORATORS =====

    def requires_cam_connected(func):
        def wrapper(self, *args, **kwargs):
            if not self.cam:
                raise RuntimeError("Camera not connected")
            return func(self, *args, **kwargs)
        return wrapper


    # ===== CAMERA SETTINGS =====

    def get_device_info(self):
        return "Andor Newton, Serial: 12345, Firmware: 1.0.0"

    def connect_cam(self):
        """
        When connecting all the parameters are usually set in the slowest mode (amplifier,vertical/horizontal scan speed, etc.)
        Default shutter is ("closed")
        """
        if self.cam:
            raise RuntimeError("Camera already connected")
        self.cam = "Andor Newton"
        self.cool_cam()

        # hend, vend = self.detect_cam_size()
        # self.set_roi(hstart=0, hend=hend, vstart=0, vend=vend, hbin=1, vbin=1)

    @requires_cam_connected
    def enable_frame_transfer_mode(self,mode:bool=True):
        self.enable_frame_transfer_mode = mode

    @requires_cam_connected
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
    
    @requires_cam_connected
    def detect_cam_size(self):
        """
        Return tuple (width, height) pixels of the camera
        Not affected by ROI
        """
        return (1024,256)
    
    @requires_cam_connected
    def get_data_dim(self):
        """
        Returns the dimensions of the data (width,height) after binning and ROI
        """
        return (64,128)

    
    # ==== ROI and Binning =====

    @requires_cam_connected
    def get_max_binning(self):
        return (4,4)

    @requires_cam_connected
    def get_roi(self):
        return (self.hstart, self.hend, self.vstart, self.vend, self.hbin, self.vbin)

    @requires_cam_connected
    def set_roi(self,hstart:int=0, hend:Optional[int]=None, vstart:int=0, vend:Optional[int]=None, hbin:int=1, vbin:int=1):
        self.validate_roi_settings(hstart, hend, vstart, vend, hbin, vbin)
        self.hstart = hstart
        self.hend = hend
        self.vstart = vstart
        self.vend = vend
        self.hbin = hbin
        self.vbin = vbin
        print(f"ROI set to: x={hstart}->{hend} | y={vstart}->{vend} | hbin: {hbin}, vbin: {vbin}")

    @requires_cam_connected
    def get_roi_limits(self):
        # TOD0
        return


    # ==== SHUTTER SETUP ====

    @requires_cam_connected
    def get_shutter_parameters(self):
        """
        Returns shutter parameters as a tuple (mode, ttl_mode, open_time, close_time)
        """
        return (self.shutter_mode, self.ttl_mode, self.open_time, self.close_time)

    @requires_cam_connected
    def setup_shutter(self, mode:str, ttl_mode:int=0, open_time:Optional[float]=None, close_time:Optional[float]=None):
        """
        Set shutter parameters.
        ttl_mode: 0 - low is open, 1 - high is open
        mode: "auto", "open", "close"
        open_time, close_time: in ms???????
        """
        self.validate_shutter_settings(mode, ttl_mode, open_time, close_time)
        self.shutter_mode = mode
        print(f"model: {mode}")
        self.ttl_mode = ttl_mode
        self.open_time = open_time
        self.close_time = close_time
        return

    @requires_cam_connected
    def get_min_shutter_times(self):
        """
        Returns minimal opening and closing times in ms????
        """
        return (5, 5)

    @requires_cam_connected
    def get_shutter(self):
        """
        Returns current shutter state: "auto", "open", "close"
        """
        return self.shutter_mode
    

    @requires_cam_connected
    def set_default_settings(self):
        """
        Initializes default (safe) parameters for the camera
        (might delete in future)
        """
        print("Default camera settings applied")
        return

    @requires_cam_connected
    def get_settings(self,include=-10):
        settings = {'image_indexing': 'rcb', 'frame_format': 'list', 'frame_info_format': 'namedtuple', 'frame_info_period': 1, 'roi': (2, 1024, 2, 256, 1, 1), 'temperature': -85, 'cooler': True, 'channel': 0, 'oamp': 0, 'hsspeed': 0, 'preamp': 1, 'vsspeed': 1, 'shutter': ('open', 0, 0, 0), 'fan_mode': 'full', 'trigger_mode': 'int', 'acq_parameters/accum': (1, 0), 'acq_parameters/kinetic': (1, 0.0, 1, 0, 0), 'acq_parameters/fast_kinetic': (1, 0.0), 'acq_parameters/cont': 0, 'acq_mode': 'single', 'frame_transfer': None, 'read_parameters/single_track': (0, 1), 'read_parameters/multi_track': (1, 1, 0), 'read_parameters/random_track': [(0, 1)], 'read_parameters/image': (2, 1024, 2, 256, 1, 1), 'read_mode': 'image', 'exposure': 0.05000000074505806, 'frame_period': 0.1457899957895279}
        return settings

    # ==== READ MODE =====

    @requires_cam_connected
    def set_read_mode(self, read_mode:str):
        self.validate_read_mode(read_mode)
        self.read_mode = read_mode
        print(f"Read mode set to: {read_mode}")
        return

    @requires_cam_connected
    def get_read_mode(self):
        return self.read_mode

    @requires_cam_connected
    def setup_single_track_mode(self, mode,center:int=0, width:int=1):
        self.validate_single_track_mode(center, width)
        # do smth with center and width
        self.set_read_mode("single_track")
        return

    @requires_cam_connected
    def get_single_track_mode_params(self):
        """
        Returns a tuple (center, width) specifying the selection of rows to be averaged together
        """
        return (0, 1)

    @requires_cam_connected
    def setup_multi_track_mode(self,mode, number:int=1, height:int=1, offset:int=0):
        self.validate_multi_track_mode(number, height, offset)
        # do smth with number, height, offset
        print("Trying to set multi-track mode")
        self.set_read_mode("multi_track")
        return

    @requires_cam_connected
    def get_multi_track_mode_params(self):
        """
        Returns a tuple (number, height, offset) specifying the multi-track read mode parameters
        """
        return (1, 1, 0)

    @requires_cam_connected
    def setup_random_track_mode(self,mode, tracks=None):
        """
        tracks is a list of tuples (start, stop) specifying track span (start are inclusive, stop are exclusive, starting from 0). 
        Note that it does not affect the current read mode, which should be set using set_read_mode()
        """
        # do smth with tracks
        return

    @requires_cam_connected
    def get_random_track_mode_params(self):
        """
        Returns a list of tuples (start, stop) specifying the random track mode parameters
        """
        return (10,20)

    @requires_cam_connected
    def setup_image_mode(self,mode,hstart:int=0, hend:Optional[int]=None, vstart:int=0, vend:Optional[int]=None, hbin:int=1, vbin:int=1):
        """
        
        """
        self.validate_roi_settings(hstart, hend, vstart, vend, hbin, vbin)
        self.set_roi(hstart, hend, vstart, vend, hbin, vbin)
        self.set_read_mode("image")
        return 

    @requires_cam_connected
    def get_image_mode_parameters(self):
        """
        Return image read mode parameters, (hstart, hend, vstart, vend, hbin, vbin)
        """
        return (0,None,0,None,1,1)

    
    # ===== ACQUISITION MODE =====

    ## validation TOD0

    @requires_cam_connected
    def acquisition_in_progress(self):
        return False

    @requires_cam_connected
    def get_acquisition_progress(self):
        return (0,0)

    @requires_cam_connected
    def setup_single_mode(self):
        self.acquisition_mode = "single"
        return

    @requires_cam_connected
    def setup_accum_mode(self,mode,num_acc:int, cycle_time_acc:Optional[float]=0):
        # validation?
        self.acquisition_mode = "accum"
        return

    @requires_cam_connected
    def setup_kinetic_mode(self,mode, num_cycle:int, cycle_time:Optional[float]=0, num_acc:Optional[int]=1, cycle_time_acc:Optional[float]=0, num_prescan:Optional[int]=0):
        # validation?
        self.acquisition_mode = "kinetic"
        return

    @requires_cam_connected
    def setup_fast_kinetic_mode(self, mode,num_acc:int, cycle_time_acc:Optional[float]=0):
        # validation?
        self.acquisition_mode = "fast_kinetic"
        return
    
    @requires_cam_connected
    def setup_cont_mode(self,mode, cycle_time:Optional[float]=0):
        # validation?
        self.acquisition_mode = "cont"
        return

    
    # ===== TRIGGER MODE =====

    @requires_cam_connected
    def set_trigger_mode(self,mode:str):
        """
        Can be "int" (internal), "ext" (external), "ext_start" (external start), "ext_exp" (external exposure), "ext_fvb_em" (external FVB EM), "software" (software trigger) or "ext_charge_shift" (external charge shifting).
        """
        self.validate_trigger_mode(mode)
        self.trigger_mode = mode
        return

    # ==== EXPOSURE ====

    @requires_cam_connected
    def set_exposure(self,exposure:float):
        self.validate_exposure(exposure)
        self.exposure = exposure
        return

    # ==== AMP MODE ====

    @requires_cam_connected
    def get_all_amp_modes(self):
        return self.all_amp_modes

    @requires_cam_connected
    def set_amp_mode(self,channel:Optional[int],oamp:Optional[int],hsspeed:Optional[int],preamp:Optional[int]):
        self.validate_amp(channel,oamp,hsspeed,preamp)
        self.amp_mode.set_mode(channel,oamp,hsspeed,preamp)
        return

    # ==== VSSPEED ====

    @requires_cam_connected
    def get_all_vsspeeds(self):
        return self.all_vsspeeds

    @requires_cam_connected
    def set_vsspeed(self,vsspeed_idx:int):
        self.vsspeed = self.all_vsspeeds[vsspeed_idx]
        print(f"Vsspeed set to: {self.vsspeed}")
        return

    # ==== EMCCD GAIN ====

    @requires_cam_connected
    def set_EMCCD_gain(self,emccd_gain, emccd_advanced=False):
        self.validate_EMCCD_gain(emccd_gain, emccd_advanced)
        self.emccd_gain = emccd_gain
        print(f"EMCCD gain set to: {self.emccd_gain}")
        return
    
    # ===== COOLING =====

    def get_temp(self):
        if not self.cam:
            return "--",""
        
        return self.temp, "Some status"

    @requires_cam_connected
    def cool_cam(self,target_temp:float=-85.0):
        self.busy = True
        self.cancel = False
        print(f"Cooling to {target_temp} C")
        
        self.temp = 20.0 # starting temp
        while True:
            if self.cancel:
                print("Cooling canceled")
                break

            self.temp -= 5
            # print(f"Cooling: {self.temp}, Status: Stabilizing")

            if self.temp <= target_temp:
                print(f"Temperature stabilized, Status: Stabilized")
                break
            # if time.time() - t0 > time_out:
            #     raise RuntimeError("Cooling timeout")

            time.sleep(0.1)
        self.busy = False

    @requires_cam_connected
    def warm_cam(self,safe_temp:float=-20):
        self.busy = True
        self.cancel = True

        print("Warming (cooler OFF)")
        self.temp = -80.0  # starting temp

        while True:
            print(f"Warming T = {self.temp} C")

            if self.temp >= safe_temp:
                break
            self.temp += 20
            time.sleep(0.1)

        self.busy = False


    # ===== DISCONNECT =====

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
    

    # ===== LIVE VIDEO =====

    @requires_cam_connected
    def start_live(self):
        """
        Start capturing what camera sees until stop live is clicked.
        """
        if not self.is_live:
            self.is_live = True
            print("Live mode started")
        
        frame = self.generate_fake_frame()

        return frame

    @requires_cam_connected
    def stop_live(self):
        if not self.cam or not self.is_live:
            return

        print("Live mode stopped")
        return

    @requires_cam_connected
    def get_live_frame(self):
        if self.cam is None or not self.is_live:
            print(f"Could not obtain the frame for the preview. Cam: {self.cam} | live state: {self.is_live}")
            return None
        
        frame = self.generate_fake_frame()
        return frame


    # ==== VALIDATION ====

    def validate_EMCCD_gain(self,emccd_gain:float,advanced:bool):
        if emccd_gain < 0:
            emccd_gain = 0
        if emccd_gain > 300 and not advanced:
            raise ValueError(f"Invalid EMCCD gain {emccd_gain}, to set above 300 use advanced option")
        return

    def validate_exposure(self,exposure:float):
        if exposure < 0:
            raise ValueError(f"Invalid exposure time {exposure}, can not be negative")
        return

    def validate_amp(self,channel:Optional[int],oamp:Optional[int],hsspeed:Optional[int],preamp:Optional[int]):
        # Not needed?
        return

    def validate_read_mode(self, read_mode:str):
        valid_modes = {"fvb", "image", "single_track", "multi_track", "random_track"}
        
        if read_mode not in valid_modes:
            raise ValueError(f"Invalid read mode: {read_mode}. Valid modes are: {valid_modes}")

    def validate_single_track_mode(self, center:int, width:int):
        #TOD0
        return

    def validate_multi_track_mode(self, number:int, height:int, offset:int):
        #TOD0
        return

    def validate_shutter_settings(self, mode:str, ttl_mode:int, open_time:Optional[float], close_time:Optional[float]):
        valid_modes = ["auto", "open", "close"]
        if mode not in valid_modes:
            raise ValueError(f"Invalid shutter mode: {mode}. Valid modes are: {valid_modes}")

        if ttl_mode not in [0, 1]:
            raise ValueError("TTL mode must be 0 (low is open) or 1 (high is open)")

        min_open_time, min_close_time = self.get_min_shutter_times()

        if open_time is not None and open_time < min_open_time:
            open_time = min_open_time
            # raise ValueError(f"Open time {open_time} ms is less than minimum allowed {min_open_time} ms.")

        if close_time is not None and close_time < min_close_time:
            close_time = min_close_time

    def validate_acquisition_mode(self, mode:str):
        """
        Validate acquisition mode before applying it.
        Raises ValueError if any parameter is invalid.
        """
        valid_modes = ["single", "accum", "kinetic", "fast_kinetic", "cont"]
        if mode not in valid_modes:
            raise ValueError(f"Invalid acquisition mode: {mode}. Valid modes are: {valid_modes}.")
            
        return True

    def validate_trigger_mode(self, mode:str):
        """
        Validate trigger mode before applying.
        Raises ValueError if any parameter is invalid.
        """
        valid_modes = ["int","ext","ext_start","ext_exp","ext_fvb_em","software","ext_charge_shift"]
        if mode not in valid_modes:
            raise ValueError(f"Invalid trigger mode: {mode}. Valid modes are: {valid_modes}.")
        
        return True

    def validate_roi_settings(self, hstart:int, hend:Optional[int], vstart:int, vend:Optional[int], hbin:int, vbin:int):
        # if hstart < 0 or hstart >= self.detect_cam_size()[0]:
        #     raise ValueError("Invalid horizontal start value")
        
        # if vstart < 0 or vstart >= self.detect_cam_size()[1]:
        #     raise ValueError("Invalid vertical start value")

        # if hend is not None:
        #     if hend <= hstart or hend > self.detect_cam_size()[0]:
        #         raise ValueError("Invalid horizontal end value")
        
        # if vend is not None:
        #     if vend <= vstart or vend > self.detect_cam_size()[1]:
        #         raise ValueError("Invalid vertical end value")

        # if hbin < 1 or hbin > self.get_max_binning()[0]:
        #     raise ValueError("Invalid horizontal binning value")

        # if vbin < 1 or vbin > self.get_max_binning()[1]:
        #     raise ValueError("Invalid vertical binning value")

        # except ValueError as ve:
        #     print(f"Error setting ROI: {ve}")
        return
        


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


    @requires_cam_connected
    def start_acquisition(self):
        return self.generate_fake_frame()


    @requires_cam_connected
    def stop_acquisition(self):
        return 

    # ===== FILE MANAGEMENT =====
    
    # import imageio.v2 as imageio
    def save_frames(self,frames,filename=None):
        """
        Save a single acquired frame as PNG + raw CSV
        """

        if frames is None:
            raise RuntimeError("No frames to save")

        if isinstance(frames,np.ndarray):
            frames = [frames]

        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            png_path = self.save_path_image / f"{timestamp}.png"
            # csv_path = self.save_path_csv / f"{timestamp}.csv"
        else:
            png_path = self.save_path_image / f"{filename.replace('.npz', '.png')}"
            # csv_path = self.save_path_csv / f"{filename.replace('.npz', '.csv')}"

        for idx,frame in enumerate(frames):

            if frame.size == 0:
                print("Empty frame")
                return

            plt.imsave(png_path, frame,cmap="gray")
            # np.savetxt(csv_path,frame,delimiter=",",fmt="%d")

        print(f"[SAVE] Frames saved to {png_path}")
        return
    
    def get_save_path(self):
        return self.save_path

    def save_npz(self,spectrum, metadata=None, filename=None):
        """
        Save spectrogram + metadata to NPZ format
        """
        if spectrum is None:
            raise RuntimeError("No spectrogram to save")

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

    def set_save_frame_path(self,path):
        # validation TOD0
        self.save_path = path
    
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

    def display_spectrogram(self, frames):
        if frames:
            frame = frames[-1]

            # Sum rows → 1D spectrum
            if frame.ndim == 2:
                spectrum = frame.sum(axis=0)
            else:
                spectrum = frame

            # Send to GUI
            self.view.show_calibration_result(frame, spectrum)

    def plot_spec(self,spectrum,exp_time):
        self.save_path.mkdir(parents=True, exist_ok=True)
        plt.figure()
        plt.plot(spectrum)
        plt.title("Spectrum")
        plt.savefig(self.save_path / f"{exp_time}_plot.png", dpi=200) # dpi is dots per inch -> more dots - better quality


    # ==== MATH =====

    def combine_frames(self,frames,acq_mode,num_frames,result_mode):
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
    
    def convert_to_spectrum(self,frame):

        hstart, hend, vstart, vend, hbin, vbin = self.get_roi()

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


    def generate_fake_frame(self):
        base = np.linspace(0, 1, 1024)
        gradient = np.tile(base, (256, 1))
        noise = np.random.normal(0, 0.05, size=(256, 1024))
        frame = gradient + noise
        frame = np.clip(frame, 0, 1)
        return [frame.astype(np.float32)]


class TAmpModeFull:
    def __init__(self,channel,bitdepth,oamp,oamp_kind,hsspeed,hsspeed_MHz,preamp,preamp_gain):
        self.channel = channel
        self.channel_bitdepth = bitdepth
        self.oamp = oamp
        self.oamp_kind = oamp_kind
        self.hsspeed = hsspeed
        self.hsspeed_MHz = hsspeed_MHz
        self.preamp = preamp
        self.preamp_gain = preamp_gain

    def set_mode(self,channel,oamp,hsspeed,preamp):
        self.channel = channel
        self.oamp = oamp
        self.hsspeed = hsspeed
        self.preamp = preamp

    def __repr__(self):
        return f"TAmpModeFull(channel={self.channel}, bitdepth={self.channel_bitdepth}, oamp={self.oamp}, oamp_kind={self.oamp_kind}, hsspeed={self.hsspeed}, hsspeed_MHz={self.hsspeed_MHz}, preamp={self.preamp}, preamp_gain={self.preamp_gain})"