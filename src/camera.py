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

class RamanCameraModel:
    def __init__(self):

        self.cam = None
        self.is_live = False    # if camera is capturing live images
        self.busy = False
        self.cancel_cooling = False

        # acquisiton settings
        self.acquisition_settings = None
        # default paths:
        self.save_path_csv = Path("./data/csv")
        self.save_path_csv.mkdir(parents=True,exist_ok=True)
        self.save_path_image = Path("./data/images")
        self.save_path_image.mkdir(parents=True,exist_ok=True)
        self.save_path = Path("./data")
        self.save_path.mkdir(parents=True,exist_ok=True)


    # ==== DECORATORS =====
    def requires_cam_connected(func):
        def wrapper(self, *args, **kwargs):
            if not self.cam:
                raise RuntimeError("Camera not connected")
                return None
            return func(self, *args, **kwargs)
        return wrapper

    def requires_live_stopped(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            if self.is_live:
                self.stop_live()
            return func(self, *args, **kwargs)
        return wrapper

    # def requires_stopped_acquisition(func):
    #     @wraps(func)
    #     def wrapper(self, *args, **kwargs):
    #         if self.cam.acquisition_in_progress():
    #             self.cam.stop_acquistion()
    #         return func(self, *args, **kwargs)
    #     return wrapper

    # ===== CAMERA SETTINGS =====

    def connect_cam(self):
        """
        When connecting all the parameters are usually set in the slowest mode (amplifier,vertical/horizontal scan speed, etc.)
        Default shutter is ("closed")
        """
        if self.cam:
            print("Camera already connected")
            return

        available = Andor.get_cameras_number_SDK2()
        print(f"Found {available} camera")

        try:
            self.cam = Andor.AndorSDK2Camera()

            info = self.cam.get_device_info()
            cam_name = f"{info.controller_model} | {info.head_model} | SN {info.serial_number}"

            print(f"Connected to: {cam_name}")
            return
        except:
            raise ConnectionError("Could not connect to device")

    
    @requires_cam_connected
    def get_cam_params(self,save_path=Path("./cam_params.txt")):
        """
        Collect and save camera parameters in readable format.
        """

        info = {}

        info["device_info"]=self.cam.get_device_info()
        info["status"]=self.cam.get_status()
        info["capabilities"]=self.cam.get_capabilities()
        info["pixel_size_um"]=self.cam.get_pixel_size()
        info["temperature_setpoint"]=self.cam.get_temperature_setpoint()
        info["temperature_range"]=self.cam.get_temperature_range()
        info["current_amp_mode"]=self.cam.get_amp_mode()
        info["available_amp_modes"]=self.cam.get_all_amp_modes()
        info["preamp_index"]=self.cam.get_preamp()
        info["preamp_gain"]=self.cam.get_preamp_gain()
        info["max_vertical_shift_speed"]=self.cam.get_max_vsspeed()
        info["all_vertical_shift_speeds"]=self.cam.get_all_vsspeeds()
        info["output_amp_index"]=self.cam.get_oamp()
        info["output_amp_description"]=self.cam.get_oamp_desc()
        info["horizontal_shift_speed"]=self.cam.get_hsspeed()
        info["hsspeed_frequency_MHz"]=self.cam.get_hsspeed_frequency()
        info["shutter_mode"]=self.cam.get_shutter()
        info["trigger_mode"]=self.cam.get_trigger_mode()
        info["acquisition_mode"]=self.cam.get_acquisition_mode()
        info["accumulation_params"]=self.cam.get_accum_mode_parameters()
        info["exposure_time_s"]=self.cam.get_exposure()
        info["readout_mode"]=self.cam.get_read_mode()
        info["detector_size"]=self.cam.get_detector_size()
        info["roi"]=self.cam.get_roi()
        info["roi_limits"]=self.cam.get_roi_limits()
        info["buffer_size_bytes"]=self.cam.get_buffer_size()
        info["frame_format"]=self.cam.get_frame_format()
        info["full_device_info"]=self.cam.get_full_info(0)

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
        return self.cam.get_detector_size()
    
    @requires_cam_connected
    def get_data_dim(self):
        """
        Returns the dimensions of the data (width,height) after binning and ROI
        """
        return self.cam.get_data_dimensions()
    
    @requires_cam_connected
    def set_default_settings(self):
        """
        Initializes default (safe) parameters for the camera
        (might delete in future)
        """
        self.cam.init_amp_mode()
        w,h = self.cam.get_detector_size()  # get the size of the camera
        self.cam.setup_image_mode(hstart=0,hend=w,vstart=0,vend=h,hbin=1,vbin=1)         # takes extreme values by default, but just a precaution
        self.cam.set_read_mode("image")     # reads images (read about this one, not sure)

        self.cam.set_frame_format("list")   # 2D array
        self.cam.set_image_indexing("rct")  # (row,column) format of the image indexing

        print(f"Camera initialized")
        return

    @requires_cam_connected
    def restore_acquisition_settings(self):
        """
        Return last used settings before the live preview
        """
        return self.acquisition_settings

    @requires_cam_connected
    def save_acquisition_settings(self):
        """
        Save acquisition settings from the camera
        """
        self.acquisition_settings = self.cam.get_settings(include=-10)
        return

    
    # ===== ROI MANAGEMENT =====

    @requires_cam_connected
    def get_roi_limits(self,hbin:int=1,vbin:int=1):
        """
        Returns two elements list: [horizontal_limits, vertical_limits]
        Each element is a limit 5-tuple:
        (min, max, pstep, sstep, maxbin) minimal and maximal size, position and size step, and the maximal binning.
        """
        return self.cam.get_roi_limits(hbin=hbin,vbin=vbin)

    @requires_cam_connected
    def get_roi(self):
        """Return tuple (hstart, hend, vstart, vend, hbin, vbin)."""
        return self.cam.get_roi()

    @requires_cam_connected
    def set_roi(self,hstart:int, hend:Optional[int], vstart:int, vend:Optional[int], hbin:int, vbin:int):
        """Set ROI with given parameters."""

        self.validate_roi(hstart, hend, vstart, vend, hbin, vbin)
        self.cam.set_roi(hstart, hend, vstart, vend, hbin, vbin)
        return


    # ==== READ MODE ====

    @requires_cam_connected
    def set_read_mode(self, read_mode:Optional[str]="fvb"):
        self.validate_read_mode(read_mode)
        self.cam.set_read_mode(read_mode)
        print(f"Read mode set to: {read_mode}")
        return

    @requires_cam_connected
    def get_read_mode(self):
        """Return current read mode."""
        return self.cam.get_read_mode()

    @requires_cam_connected
    def setup_single_track_mode(self,center:int=0, width:int=1, mode:Optional[str]="single"):
        self.validate_single_track_mode(center, width)
        # do smth with center and width
        self.cam.setup_single_track_mode(center,width)
        return

    @requires_cam_connected
    def get_single_track_mode_params(self):
        """
        Returns a tuple (center, width) specifying the selection of rows to be averaged together
        """
        return self.cam.get_single_track_mode_parameters()

    @requires_cam_connected
    def setup_multi_track_mode(self, number:int=1, height:int=1, offset:int=0, mode:Optional[str]="multi_track"):
        self.validate_multi_track_mode(number, height, offset)
        # do smth with number, height, offset
        self.cam.setup_multi_track_mode(number,height,offset)
        return

    @requires_cam_connected
    def get_multi_track_mode_params(self):
        """
        Returns a tuple (number, height, offset) specifying the multi-track read mode parameters
        """
        return self.cam.get_multi_track_mode_parameters()

    @requires_cam_connected
    def setup_random_track_mode(self, tracks=None, mode:Optional[str]="random_track"):
        """
        tracks is a list of tuples (start, stop) specifying track span (start are inclusive, stop are exclusive, starting from 0). 
        Note that it does not affect the current read mode, which should be set using set_read_mode()
        """
        # do smth with tracks
        self.cam.setup_random_track_mode(tracks)
        return

    @requires_cam_connected
    def get_random_track_mode_params(self):
        """
        Returns a list of tuples (start, stop) specifying the random track mode parameters
        """
        return self.cam.get_random_track_mode_parameters()
    
    @requires_cam_connected
    def setup_image_mode(self, hstart:int=0, hend:Optional[int]=None, vstart:int=0, vend:Optional[int]=None, hbin:int=1, vbin:int=1, mode:Optional[str]="image"):
        """
        
        """
        hstart,hend,vstart,vend,hbin,vbin = self.validate_roi(hstart, hend, vstart, vend, hbin, vbin)
        self.cam.setup_image_mode(hstart,hend,vstart,vend,hbin,vbin)
        print(f"Setting up image mode... Real mode:{self.cam.get_read_mode()}")
        return

    @requires_cam_connected
    def get_image_mode_parameters(self):
        """
        Return image read mode parameters, (hstart, hend, vstart, vend, hbin, vbin)
        """
        return self.cam.get_image_mode_parameters()


    # ==== SHUTTER SETUP ====

    @requires_cam_connected
    def get_shutter_parameters(self):
        """
        Returns shutter parameters as a tuple (mode, ttl_mode, open_time, close_time)
        """
        return self.cam.get_shutter_parameters()

    @requires_cam_connected
    def setup_shutter(self, mode:str, ttl_mode:int=0, open_time:Optional[float]=None, close_time:Optional[float]=None):
        """
        Set shutter parameters.
        ttl_mode: 0 - low is open, 1 - high is open
        mode: "auto", "open", "close"
        open_time, close_time: in ms???????
        """
        self.validate_shutter_settings(mode, ttl_mode, open_time, close_time)
        self.cam.setup_shutter(mode, ttl_mode, open_time, close_time)
        return

    @requires_cam_connected
    def get_min_shutter_times(self):
        """
        Returns minimal opening and closing times in ms????
        """
        return self.cam.get_min_shutter_times()

    @requires_cam_connected
    def get_shutter(self):
        """
        Returns current shutter state: "auto", "open", "close"
        """
        return self.cam.get_shutter()

    
    # ===== ACQUISITION MODE =====

    ## validation TOD0

    @requires_cam_connected
    def setup_single_mode(self):
        self.cam.set_acquisition_mode("single",setup_params=True)
        print(f"Trying to change acquisition mode to single.. Actual: {self.cam.get_acquisition_mode()}")
        return

    @requires_cam_connected
    def setup_accum_mode(self, num_acc:int, cycle_time_acc:Optional[float]=0, mode:Optional[str]="accum"):
        # validation?
        self.cam.setup_accum_mode(num_acc, cycle_time_acc)
        return

    @requires_cam_connected
    def setup_kinetic_mode(self, num_cycle:int, cycle_time:Optional[float]=0, num_acc:Optional[int]=1, cycle_time_acc:Optional[float]=0, num_prescan:Optional[int]=0, mode:Optional[str]="kinetic"):
        # validation?
        self.cam.setup_kinetic_mode(num_cycle, cycle_time, num_acc, cycle_time_acc, num_prescan)
        return

    @requires_cam_connected
    def setup_fast_kinetic_mode(self, num_acc:int, cycle_time_acc:Optional[float]=0, mode:Optional[str]="fast_kinetic"):
        # validation?
        self.cam.setup_fast_kinetic_mode(num_acc, cycle_time_acc)
        return
    
    @requires_cam_connected
    def setup_cont_mode(self, cycle_time:Optional[float]=0, mode:Optional[str]="cont"):
        # validation?
        self.cam.setup_cont_mode(cycle_time)
        return
    
    # ===== TRIGGER MODE =====

    @requires_cam_connected
    def set_trigger_mode(self,mode:str):
        """
        Can be "int" (internal), "ext" (external), "ext_start" (external start), "ext_exp" (external exposure), "ext_fvb_em" (external FVB EM), "software" (software trigger) or "ext_charge_shift" (external charge shifting).
        """
        self.validate_trigger_mode(mode)
        self.cam.set_trigger_mode(mode)
        return

    # ==== EXPOSURE ====

    @requires_cam_connected
    def set_exposure(self,exposure:float):
        self.validate_exposure(exposure)
        self.cam.set_exposure(exposure)
        return

    # ==== AMP MODE ====

    @requires_cam_connected
    def get_all_amp_modes(self):
        return self.cam.get_all_amp_modes()

    @requires_cam_connected
    def set_amp_mode(self,channel:Optional[int],oamp:Optional[int],hsspeed:Optional[int],preamp:Optional[int]):
        self.validate_amp(channel,oamp,hsspeed,preamp)
        self.cam.set_amp_mode(channel,oamp,hsspeed,preamp)
        return

    # ==== VSSPEED ====

    @requires_cam_connected
    def get_all_vsspeeds(self):
        return self.cam.get_all_vsspeeds()

    @requires_cam_connected
    def set_vsspeed(self,vsspeed_idx:int):
        # no need for validation?
        self.cam.set_vsspeed(vsspeed_idx)
        return

    # ==== EMCCD gain ====
    
    @requires_cam_connected
    def set_EMCCD_gain(self,emccd_gain, advanced=False):
        self.validate_EMCCD_gain(emccd_gain,advanced)
        self.cam.set_EMCCD_gain(emccd_gain,advanced)


    # ===== TEMPERATURE CONTROL =====

    @requires_cam_connected
    def cool_cam(self,target_temp:float=-85.0):
        self.busy = True
        self.cancel_cooling = False
        self.cam.set_temperature(target_temp, enable_cooler=True)
        self.cam.set_fan_mode("full")
        print(f"Fan mode set to: {self.cam.get_fan_mode()}")
        # t0 = time.time()

        while not self.cancel:
            
            try:
                temp = round(self.cam.get_temperature(),2)
                print(f"Cooling: {temp}, Status: {self.cam.get_temperature_status()}")
            except:
                break

            if temp <= target_temp:      # GET RID OF 20!!
                print(f"Temperature stabilized, Status: {self.cam.get_temperature_status()}")
                break

            time.sleep(1)

        self.busy = False

    @requires_cam_connected
    def warm_cam(self,safe_temp:float=-20):
        self.cam.set_fan_mode("off")
        self.busy = True
        self.cancel_cooling = True

        self.cam.set_cooler(on=False)
        print("Warming (cooler OFF)")

        while True:

            t = round(self.cam.get_temperature(),2)
            print(f"Warming T = {t:.1f}")

            if t >= safe_temp:
                break

            time.sleep(1)
        self.busy = False
        
    def get_temp(self):
        if not self.cam:
            return "--",""
        return round(self.cam.get_temperature(),3), self.cam.get_temperature_status()

    
    # ==== DISCONNECT CAMERA =====
    @requires_live_stopped
    def safe_close(self):
        """
        Turn off the cooler and wait until the temperature is at least -20
        Disconnect the camera
        """
        if not self.cam:
            return
        
        self.cancel_cooling=True
        
        try:
            if self.cam.acquisition_in_progress():
                self.cam.stop_acquisition()
        except:
            pass

        # self.warm_cam()
        
        self.close_cam()
        return

    @requires_live_stopped
    def close_cam(self):
        if self.cam:
            self.cam.set_fan_mode("off")
            self.cam.close()
            self.cam = None
            print("Camera disconnected safely")
    

    # ===== LIVE VIDEO =====

    @requires_cam_connected
    def start_live(self):
        """
        Start capturing what camera sees until stop live is clicked.
        """
        if self.is_live:
            return
    
        self.save_acquisition_settings()
        self.cam.set_acquisition_mode("single",setup_params=True)    # not sure
        h_limits, v_limits = self.get_roi_limits(hbin=1,vbin=1)   # get full ROI
        print(f"ROI limits for live preview: h_limits={h_limits}, v_limits={v_limits}")
        hmin,hmax,_,_,_ = h_limits
        vmin,vmax,_,_,_ = v_limits
        self.setup_image_mode(hmin,hmax,vmin,vmax,1,1)
        self.cam.set_exposure(0.01)
        self.is_live = True  
        print("Live mode started")
        return

    @requires_cam_connected
    def stop_live(self):
        if not self.is_live:
            return
        self.cam.stop_acquisition()      # stop acquisition if it is already in progress
        self.cam.clear_acquisition()    # clear the buffer
        self.is_live=False
        print("Live mode stopped")
        return

    @requires_cam_connected
    def get_live_frame(self):
        if not self.is_live:
            print(f"Could not obtain the frame for the preview. Cam: {self.cam} | live state: {self.is_live}")
            return None
        return self.cam.snap(timeout=5.0,return_info=False)    # temperary change to use snap instead of acquition


    # ===== ACQUISITION =====

    @requires_cam_connected
    def acquisition_in_progress(self):
        """ Return True if acquisition is in progress, False otherwise. """
        return self.cam.acquisition_in_progress()

    @requires_cam_connected
    def get_acquisition_progress(self):
        """
        Returns tuple (frames done, acc done)
        """
        return self.cam.get_acquisition_progress()

    @requires_cam_connected
    @requires_live_stopped
    def single_preview(self):
        """
        Perform single snap to preview the result
        """
        self.cam.stop_acquisition()      # stop acquisition if it is already in progress
        try:
            frame = self.cam.snap(timeout=5,return_info=False)
        finally:
            self.cam.stop_acquisition()      # stop acquisition after grabbing frames
            self.cam.clear_acquisition()    # clear the buffer

        if frame is None or not frame.any():     # replace following to frame.any() or frame.all() ??
            raise RuntimeError("Could not obtain frame for single preview")
            return
        return frame

    @requires_cam_connected
    @requires_live_stopped
    def start_acquisition(self):
        if self.is_live:
            self.stop_live()

        print(f"Acquisition parameters: {self.cam.get_acquisition_parameters()}")
        print(f"Acquisition mode: {self.cam.get_acquisition_mode()}")
        print(f"Status before start: {self.cam.get_status()}")
        self.cam.stop_acquisition()      # stop acquisition if it is already in progress, just in case
        acquisition_mode = self.cam.get_acquisition_mode()
        frames = None

        try:
            if acquisition_mode == "single":
                self.cam.set_acquisition_mode("single",setup_params=True)    # testing this
                print(f"Acquisition parameters after enforcing: {self.cam.get_acquisition_parameters()}")
                frames = [self.cam.snap(timeout=5,return_info=False)]
            elif acquisition_mode == "accum":
                self.cam.set_acquisition_mode("accum",setup_params=True)    # testing this
                frames = [self.cam.snap(timeout=5,return_info=False)]       # since 1 frame produced
            elif acquisition_mode == "kinetic":
                self.cam.set_acquisition_mode("kinetic",setup_params=True)    # testing this
                num_frames = self.cam.get_kinetic_mode_parameters()[0]
                frames = self.cam.grab(nframes=num_frames, frame_timeout=5.0, missing_frame='skip', return_info=False, buff_size=None)
            elif acquisition_mode == "fast_kinetic":
                self.cam.set_acquisition_mode("fast_kinetic",setup_params=True)    # testing this
                num_frames = self.cam.get_fast_kinetic_mode_parameters()[0]
                frames = self.cam.grab(nframes=num_frames, frame_timeout=5.0, missing_frame='skip', return_info=False, buff_size=None)
            elif acquisition_mode == "cont":
                raise RuntimeError("Continuous mode cannot be used for save acquisition")

        finally:
            self.cam.stop_acquisition()      # stop acquisition after grabbing frames
            self.cam.clear_acquisition()    # clear the buffer

        if frames is None:
            raise RuntimeError("No frames were obtained")
            return
        return frames

    @requires_cam_connected
    def stop_acquisition(self):
        self.cam.stop_acquisition()
        self.cam.clear_acquisition()
        return

    @requires_cam_connected
    @requires_live_stopped
    def simple_acq(self,num_frames:int=0):
        
        if self.is_live:
            self.stop_live()

        if num_frames == 0:
            frame = self.cam.snap()   # grab single frame
            print("Single frame acquired")
            return frame
        else:
            frames = self.cam.grab(num_frames)  # grab 10 frames
            print("Multiple frames acquired")
            return frames


    # ==== VALIDAION =====

    def validate_EMCCD_gain(self,emccd_gain:float,advanced:bool):
        if emccd_gain < 0:
            raise ValueError(f"Invalid EMCCD gain {emccd_gain}, can not be negative")
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

    def validate_single_track_mode(self, center:int, width:int):
        #TOD0
        return

    def validate_multi_track_mode(self, number:int, height:int, offset:int):
        #TOD0
        return

    def validate_read_mode(self, read_mode:str):
        valid_modes = {"fvb", "image", "single_track", "multi_track", "random_track"}
        if read_mode not in valid_modes:
            raise ValueError(f"Invalid read mode: {read_mode}. Valid modes are: {valid_modes}")

    def validate_shutter_settings(self, mode:str, ttl_mode:int, open_time:Optional[float], close_time:Optional[float]):
        """
        Validate shutter settings before applying them.
        Raises ValueError if any parameter is invalid.
        """
        valid_modes = ["auto", "open", "closed"]
        if mode not in valid_modes:
            raise ValueError(f"Invalid shutter mode: {mode}. Valid modes are: {valid_modes}.")
        
        if ttl_mode not in [0, 1]:
            raise ValueError("TTL mode must be 0 (low is open) or 1 (high is open).")
        
        min_open, min_close = self.get_min_shutter_times()
        
        if open_time is not None and open_time < min_open:
            raise ValueError(f"Open time {open_time} ms is less than minimum allowed {min_open} ms.")
        
        if close_time is not None and close_time < min_close:
            raise ValueError(f"Close time {close_time} ms is less than minimum allowed {min_close} ms.")
        
        return True

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

    def validate_roi(self,hstart:int, hend:Optional[int], vstart:int, vend:Optional[int], hbin:int, vbin:int):
        """
        Check if the given ROI parameters are valid.
        Raises ValueError if any parameter is invalid.
        """
        if hbin is None or hbin < 1:
            hbin = 1
        if vbin is None or vbin < 1:
            vbin = 1
        
        h_limits, v_limits = self.get_roi_limits(hbin=hbin,vbin=vbin)   # get limits for current binning
        hmin,hmax,hpstep,hsstep,hmaxbin = h_limits
        vmin,vmax,vpstep,vsstep,vmaxbin = v_limits
        print(f"horizontal limits: hmin={hmin}, hmax={hmax}, hpstep={hpstep}, hsstep={hsstep}, hmaxbin={hmaxbin}")
        print(f"vertical limits: vmin={vmin}, vmax={vmax}, vpstep={vpstep}, vsstep={vsstep}, vmaxbin={vmaxbin}")
        if hbin > hmaxbin:      # what?
            hbin = hmaxbin
        if vbin > vmaxbin:
            vbin = vmaxbin

        if hstart is None or hstart < hmin:
            hstart = hmin
        if vstart is None or vstart < vmin:
            vstart = vmin
        if hend is None or hend > hmax:
            hend = hmax
        if vend is None or vend > vmax:
            vend = vmax

        if hend <= hstart or vend <= vstart:
            raise ValueError("ROI end positions must be greater than start positions.")
        
        if hstart % hpstep != 0 or (hend - hstart) % hsstep != 0:
            raise ValueError(f"Horizontal ROI positions must align with steps: hstart step {hpstep}, width step {hsstep}.")
        if vstart % vpstep != 0 or (vend - vstart) % vsstep != 0:
            raise ValueError(f"Vertical ROI positions must align with steps: vstart step {vpstep}, height step {vsstep}.")
        
        if (hend - hstart) % hbin != 0 or (vend - vstart) % vbin != 0:
            raise ValueError("ROI width and height must be divisible by binning factors.")
        return hstart, hend, vstart, vend, hbin, vbin


    # ===== FILE MANAGEMENT =====

    def save_frames(self,frames):
        """
        Save a single acquired frame as PNG + raw CSV
        """

        if frames is None:
            raise RuntimeError("No frames to save")

        if isinstance(frames,np.ndarray):
            frames = [frames]

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        for idx,frame in enumerate(frames):

            if frame.size == 0:
                print("Empty frame")
                return

            png_path = self.save_path_image / f"{idx+1}.{timestamp}.png"
            csv_path = self.save_path_csv / f"{idx+1}.{timestamp}.csv"

            plt.imsave(png_path, frame,cmap="gray")
            np.savetxt(csv_path,frame,delimiter=",",fmt="%d")

        print(f"[SAVE] Frames saved to {png_path}")
        return        

    def set_save_frame_path(self,path):
        # validation TOD0
        self.save_path = path
        self.save_path_image = path
        self.save_path_csv = path
    
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


    # ==== DISPLAY DATA =====

    def display_spectrogram(self, frames):
        if frames is not None:
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
        if frame.ndim == 2:
            spectrum = frame.sum(axis=0)
        else:
            spectrum = frame
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
