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
    """
    Hardware abstraction layer for an Andor SDK2 camera used in Raman spectroscopy.
 
    All public methods that require an active camera connection are guarded by the
    @requires_cam_connected decorator, which raises RuntimeError if self.cam is None.
    """
    def __init__(self):
        """
        Initialise the model with no camera connected and default output directories.
 
        Creates ./data, ./data/csv, and ./data/images if they do not exist.
        Also initialises bit-shift correction parameters to their off state.
        """

        self.cam = None
        self.cancel_cooling = False
        self.acquisition_settings = None

        # default paths:
        self.save_path_csv = Path("./data/csv")
        self.save_path_csv.mkdir(parents=True,exist_ok=True)
        self.save_path_image = Path("./data/images")
        self.save_path_image.mkdir(parents=True,exist_ok=True)
        self.save_path = Path("./data")
        self.save_path.mkdir(parents=True,exist_ok=True)

        # bit shifting info
        self.bit_shift_pixels = 0
        self.bit_shift_vstart = None
        self.bit_shift_vend = None


    # ==== DECORATORS =====
    def requires_cam_connected(func):
        """
        Decorator that guards a method against being called when no camera is open.
 
        Raises:
            RuntimeError: If self.cam is None (camera not connected).
        """
        def wrapper(self, *args, **kwargs):
            if not self.cam:
                raise RuntimeError("Camera not connected")
                return None
            return func(self, *args, **kwargs)
        return wrapper

    # ===== CAMERA SETTINGS =====

    def connect_cam(self):
        """
        Open a connection to the first available Andor SDK2 camera.
 
        Does nothing if a camera is already connected.  Sets self.cam to an
        AndorSDK2Camera instance on success.
 
        Raises:
            ConnectionError: If no camera can be opened.
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
    def get_device_info(self):
        """
        Return camera device info (controller model, head model, serial number, etc.).
 
        Returns:
            DeviceInfo named-tuple from pylablib.
        """
        return self.cam.get_device_info()

    
    @requires_cam_connected
    def get_cam_params(self,save_path=Path("./cam_params.txt")):
        """
        Collect all available camera parameters and write them to a human-readable
        text file at save_path.
 
        Captures device info, status, capabilities, pixel size, temperature settings,
        amplifier modes, shift speeds, shutter, trigger, acquisition, ROI, and more.
 
        Args:
            save_path: Destination file path (default ./cam_params.txt).
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
        Return the full detector size in pixels, unaffected by the current ROI.
 
        Returns:
            Tuple (width, height) in pixels.
        """
        return self.cam.get_detector_size()
    
    @requires_cam_connected
    def get_data_dim(self):
        """
        Return the effective data dimensions (width, height) after applying the
        current ROI and binning settings.
 
        Returns:
            Tuple (width, height) in pixels.
        """
        return self.cam.get_data_dimensions()
    
    @requires_cam_connected
    def set_default_settings(self):
        """
        Apply a minimal safe set of default camera parameters (single acquisition mode).
 
        Note: Currently commented out in the controller and may be removed in future.
        """
        self.setup_single_mode()

        print(f"Camera initialized")
        return

    @requires_cam_connected
    def get_settings(self,include=-10):
        """
        Return a dict of the camera's current hardware settings.
 
        Args:
            include: Bitmask / depth passed to pylablib get_settings (default –10 = all).
 
        Returns:
            Dict of setting name → value pairs.
        """
        return self.cam.get_settings(include=include)

    @requires_cam_connected
    def restore_acquisition_settings(self):
        """
        Return the last settings snapshot saved by save_acquisition_settings().
 
        Returns:
            Previously saved settings dict, or None if never saved.
        """
        return self.acquisition_settings

    @requires_cam_connected
    def save_acquisition_settings(self):
        """
        Snapshot the current camera settings into self.acquisition_settings so they
        can be restored later via restore_acquisition_settings().
        """
        self.acquisition_settings = self.cam.get_settings(include=-10)
        return
    
    @requires_cam_connected
    def calc_frame_timeout(self, extra=5.0):
        """
        Calculate a safe frame capture timeout based on the current frame timings.
 
        Args:
            extra: Additional safety margin in seconds to add to the frame period.
 
        Returns:
            Float timeout in seconds (minimum 5.0 s).
        """
        exp, frame_period = self.cam.get_frame_timings()
        return max(frame_period + extra, 5.0)
    
    @requires_cam_connected
    def get_exposure(self):
        """
        Return the current exposure time set on the camera.
 
        Returns:
            Exposure time in seconds (float).
        """
        return self.cam.get_exposure()

    
    # ===== ROI MANAGEMENT =====

    @requires_cam_connected
    def get_roi_limits(self,hbin:int=1,vbin:int=1):
        """
        Return the hardware ROI limits for the given binning factors.
 
        Returns:
            List of two 5-tuples [h_limits, v_limits] where each tuple is
            (min, max, position_step, size_step, max_bin).
        """
        return self.cam.get_roi_limits(hbin=hbin,vbin=vbin)

    @requires_cam_connected
    def get_roi(self):
        """
        Return the current ROI as a 6-tuple.
 
        Returns:
            Tuple (hstart, hend, vstart, vend, hbin, vbin).
        """
        return self.cam.get_roi()

    @requires_cam_connected
    def set_roi(self,hstart:int, hend:Optional[int], vstart:int, vend:Optional[int], hbin:int, vbin:int):
        """
        Validate and apply a new ROI to the camera.
 
        Args:
            hstart: Horizontal start pixel (inclusive, 0-based).
            hend:   Horizontal end pixel (exclusive).  None = detector width.
            vstart: Vertical start pixel (inclusive, 0-based).
            vend:   Vertical end pixel (exclusive).  None = detector height.
            hbin:   Horizontal binning factor.
            vbin:   Vertical binning factor.
        """

        self.validate_roi(hstart, hend, vstart, vend, hbin, vbin)
        self.cam.set_roi(hstart, hend, vstart, vend, hbin, vbin)
        return


    # ==== READ MODE ====

    @requires_cam_connected
    def set_read_mode(self, read_mode:Optional[str]="fvb"):
        """
        Set the detector readout mode.
 
        Args:
            read_mode: One of 'fvb', 'image', 'single_track', 'multi_track',
                       'random_track'.
 
        Raises:
            ValueError: If read_mode is not one of the supported modes.
        """
        self.validate_read_mode(read_mode)
        self.cam.set_read_mode(read_mode)
        print(f"Read mode set to: {read_mode}")
        return

    @requires_cam_connected
    def get_read_mode(self):
        """
        Return the current detector readout mode string.
 
        Returns:
            String such as 'fvb', 'image', 'single_track', etc.
        """
        return self.cam.get_read_mode()

    @requires_cam_connected
    def setup_single_track_mode(self,center:int=0, width:int=1, mode:Optional[str]="single"):
        """
        Configure single-track readout to bin a horizontal strip of rows.
 
        Args:
            center: Centre row of the track (0-based).
            width:  Number of rows to include in the track.
            mode:   Read mode label (informational, not sent to camera).
        """
        self.validate_single_track_mode(center, width)
        self.cam.setup_single_track_mode(center,width)
        return

    @requires_cam_connected
    def get_single_track_mode_params(self):
        """
        Return the current single-track mode parameters.
 
        Returns:
            Tuple (center, width).
        """
        return self.cam.get_single_track_mode_parameters()

    @requires_cam_connected
    def setup_multi_track_mode(self, number:int=1, height:int=1, offset:int=0, mode:Optional[str]="multi_track"):
        """
        Configure multi-track readout with evenly spaced horizontal strips.
 
        Args:
            number: Number of tracks.
            height: Height of each track in rows.
            offset: Offset between track centres in rows.
            mode:   Read mode label (informational, not sent to camera).
        """
        self.validate_multi_track_mode(number, height, offset)
        self.cam.setup_multi_track_mode(number,height,offset)
        return

    @requires_cam_connected
    def get_multi_track_mode_params(self):
        """
        Return the current multi-track mode parameters.
 
        Returns:
            Tuple (number, height, offset).
        """
        return self.cam.get_multi_track_mode_parameters()

    @requires_cam_connected
    def setup_random_track_mode(self, tracks=None, mode:Optional[str]="random_track"):
        """
        Configure random-track readout with arbitrary row spans.
 
        Args:
            tracks: List of (start, stop) tuples defining each track (start inclusive,
                    stop exclusive, 0-based rows).
            mode:   Read mode label (informational, not sent to camera).
        """
        self.cam.setup_random_track_mode(tracks)
        return

    @requires_cam_connected
    def get_random_track_mode_params(self):
        """
        Return the current random-track mode parameters.
 
        Returns:
            List of (start, stop) tuples.
        """
        return self.cam.get_random_track_mode_parameters()
    
    @requires_cam_connected
    def setup_image_mode(self, hstart:int=0, hend:Optional[int]=None, vstart:int=0, vend:Optional[int]=None, hbin:int=1, vbin:int=1, mode:Optional[str]="image"):
        """
        Configure the camera for full-image readout with optional ROI and binning.
 
        Validates the supplied ROI before applying it to the hardware.
 
        Args:
            hstart: Horizontal start pixel (inclusive, 0-based).
            hend:   Horizontal end pixel (exclusive).  None = detector width.
            vstart: Vertical start pixel (inclusive, 0-based).
            vend:   Vertical end pixel (exclusive).  None = detector height.
            hbin:   Horizontal binning factor.
            vbin:   Vertical binning factor.
            mode:   Read mode label (informational).
        """
        hstart,hend,vstart,vend,hbin,vbin = self.validate_roi(hstart, hend, vstart, vend, hbin, vbin)
        self.cam.setup_image_mode(hstart,hend,vstart,vend,hbin,vbin)
        print(f"Setting up image mode... Real mode:{self.cam.get_read_mode()}")
        return

    def setup_bit_shifting(self,bit_shift_pixels,bit_shift_vstart,bit_shift_vend):
        """
        Validate and store bit-shift correction parameters used during frame processing.
 
        Args:
            bit_shift_pixels: Number of pixels to shift (0 = disabled).
            bit_shift_vstart: Absolute detector row where the shift region starts.
            bit_shift_vend:   Absolute detector row where the shift region ends.
        """
        bit_shift_pixels,bit_shift_vstart,bit_shift_vend = self.validate_bit_shift(bit_shift_pixels,bit_shift_vstart,bit_shift_vend)
        self.bit_shift_pixels = bit_shift_pixels
        self.bit_shift_vstart = bit_shift_vstart
        self.bit_shift_vend = bit_shift_vend
        return

    def get_bit_shifting(self):
        """
        Return the currently stored bit-shift correction parameters.
 
        Returns:
            Tuple (bit_shift_pixels, bit_shift_vstart, bit_shift_vend).
        """
        return self.bit_shift_pixels,self.bit_shift_vstart,self.bit_shift_vend

    @requires_cam_connected
    def get_image_mode_parameters(self):
        """
        Return the current image-mode ROI and binning parameters.
 
        Returns:
            Tuple (hstart, hend, vstart, vend, hbin, vbin).
        """
        return self.cam.get_image_mode_parameters()


    # ==== SHUTTER SETUP ====

    @requires_cam_connected
    def get_shutter_parameters(self):
        """
        Return the current shutter configuration.
 
        Returns:
            Tuple (mode, ttl_mode, open_time, close_time).
        """
        return self.cam.get_shutter_parameters()

    @requires_cam_connected
    def setup_shutter(self, mode:str, ttl_mode:int=0, open_time:Optional[float]=None, close_time:Optional[float]=None):
        """
        Configure the mechanical shutter.
 
        Args:
            mode:       'auto', 'open', or 'closed'.
            ttl_mode:   0 = low TTL opens the shutter; 1 = high TTL opens the shutter.
            open_time:  Shutter opening time in ms (None = hardware default).
            close_time: Shutter closing time in ms (None = hardware default).
 
        Raises:
            ValueError: If mode is invalid, ttl_mode is not 0 or 1, or timing
                        values are below the hardware minimum.
        """
        self.validate_shutter_settings(mode, ttl_mode, open_time, close_time)
        self.cam.setup_shutter(mode, ttl_mode, open_time, close_time)
        return

    @requires_cam_connected
    def get_min_shutter_times(self):
        """
        Return the hardware minimum opening and closing times for the shutter.
 
        Returns:
            Tuple (min_open_ms, min_close_ms).
        """
        return self.cam.get_min_shutter_times()

    @requires_cam_connected
    def get_shutter(self):
        """
        Return the current shutter state string.
 
        Returns:
            One of 'auto', 'open', 'closed'.
        """
        return self.cam.get_shutter()

    
    # ===== ACQUISITION MODE =====

    @requires_cam_connected
    def setup_single_mode(self):
        """Set the camera to single-frame acquisition mode."""
        self.cam.set_acquisition_mode("single",setup_params=True)
        print(f"Trying to change acquisition mode to single.. Actual: {self.cam.get_acquisition_mode()}")
        return

    @requires_cam_connected
    def setup_accum_mode(self, num_acc:int, cycle_time_acc:Optional[float]=0, mode:Optional[str]="accum",result_mode="sum"):
        """
        Configure accumulation acquisition mode.
 
        Args:
            num_acc:        Number of sub-exposures to accumulate.
            cycle_time_acc: Minimum cycle time between accumulations in seconds.
            mode:           Mode label (informational).
            result_mode:    Unused in camera layer; handled by AcquisitionService.
        """
        self.cam.setup_accum_mode(num_acc, cycle_time_acc)
        return

    @requires_cam_connected
    def setup_kinetic_mode(self, num_cycle:int, cycle_time:Optional[float]=0, num_acc:Optional[int]=1, cycle_time_acc:Optional[float]=0, num_prescan:Optional[int]=0, mode:Optional[str]="kinetic",result_mode="sum"):
        """
        Configure kinetic series acquisition mode.
 
        Args:
            num_cycle:      Number of kinetic cycles (frames).
            cycle_time:     Minimum cycle time in seconds.
            num_acc:        Accumulations per cycle.
            cycle_time_acc: Minimum accumulation cycle time in seconds.
            num_prescan:    Number of pre-scan cycles.
            mode:           Mode label (informational).
            result_mode:    Unused in camera layer; handled by AcquisitionService.
        """
        self.cam.setup_kinetic_mode(num_cycle, cycle_time, num_acc, cycle_time_acc, num_prescan)
        return

    @requires_cam_connected
    def setup_fast_kinetic_mode(self, num_acc:int, cycle_time_acc:Optional[float]=0, mode:Optional[str]="fast_kinetic",result_mode="sum"):
        """
        Configure fast-kinetic acquisition mode.
 
        Args:
            num_acc:        Number of fast-kinetic frames.
            cycle_time_acc: Minimum cycle time in seconds.
            mode:           Mode label (informational).
            result_mode:    Unused in camera layer; handled by AcquisitionService.
        """
        self.cam.setup_fast_kinetic_mode(num_acc, cycle_time_acc)
        return
    
    @requires_cam_connected
    def setup_cont_mode(self, cycle_time:Optional[float]=0, mode:Optional[str]="cont"): 
        """
        Configure continuous (run-till-abort) acquisition mode.
 
        Args:
            cycle_time: Minimum cycle time in seconds (0 = fastest possible).
            mode:       Mode label (informational).
        """
        self.cam.setup_cont_mode(cycle_time)
        return
    
    # ===== TRIGGER MODE =====

    @requires_cam_connected
    def set_trigger_mode(self,mode:str):
        """
        Set the acquisition trigger source.
 
        Args:
            mode: One of 'int', 'ext', 'ext_start', 'ext_exp', 'ext_fvb_em',
                  'software', 'ext_charge_shift'.
 
        Raises:
            ValueError: If mode is not one of the supported values.
        """
        self.validate_trigger_mode(mode)
        self.cam.set_trigger_mode(mode)
        return

    # ==== EXPOSURE ====

    @requires_cam_connected
    def set_exposure(self,exposure:float):
        """
        Set the sensor exposure time.
 
        Args:
            exposure: Exposure time in seconds (must be > 0).
 
        Raises:
            ValueError: If exposure is negative.
        """
        self.validate_exposure(exposure)
        self.cam.set_exposure(exposure)
        return

    # ==== AMP MODE ====

    @requires_cam_connected
    def get_all_amp_modes(self):
        """
        Return all amplifier modes supported by the camera hardware.
 
        Returns:
            List of amp-mode descriptors from pylablib.
        """
        return self.cam.get_all_amp_modes()

    @requires_cam_connected
    def set_amp_mode(self,channel:Optional[int],oamp:Optional[int],hsspeed:Optional[int],preamp:Optional[int]):
        """
        Configure the output amplifier and horizontal shift speed.
 
        Args:
            channel:  ADC channel index (None = leave unchanged).
            oamp:     Output amplifier index (None = leave unchanged).
            hsspeed:  Horizontal shift speed index (None = leave unchanged).
            preamp:   Pre-amplifier gain index (None = leave unchanged).
        """
        self.validate_amp(channel,oamp,hsspeed,preamp)
        self.cam.set_amp_mode(channel,oamp,hsspeed,preamp)
        return

    # ==== VSSPEED ====

    @requires_cam_connected
    def get_all_vsspeeds(self):
        """
        Return all available vertical shift speed options supported by the camera.
 
        Returns:
            List of vertical shift speed values from pylablib.
        """
        return self.cam.get_all_vsspeeds()

    @requires_cam_connected
    def set_vsspeed(self,vsspeed_idx:int):
        """
        Set the vertical clock shift speed by index.
 
        Args:
            vsspeed_idx: Index into the list returned by get_all_vsspeeds().
        """
        self.cam.set_vsspeed(vsspeed_idx)
        return

    # ==== EMCCD gain ====
    
    @requires_cam_connected
    def set_EMCCD_gain(self,emccd_gain, emccd_advanced=False):
        """
        Set the EMCCD multiplication gain register.
 
        Args:
            emccd_gain:     Gain value (0–300 in normal mode; up to 1000 in advanced mode).
            emccd_advanced: If True, allows gain values above 300 (use with caution –
                            risk of sensor damage at very high gains).
 
        Raises:
            ValueError: If gain is negative, or > 300 without advanced mode enabled.
        """
        self.validate_EMCCD_gain(emccd_gain, emccd_advanced)
        self.cam.set_EMCCD_gain(emccd_gain, emccd_advanced)


    # ===== TEMPERATURE CONTROL =====

    @requires_cam_connected
    def cool_cam(self,target_temp:float=-85.0):
        """
        Enable the TEC cooler and block until the sensor reaches within 20 °C of
        target_temp, or until cancel_cooling is set to True.
 
        Args:
            target_temp: Desired sensor temperature in °C (default –85 °C).
        """
        self.cancel_cooling = False
        self.cam.set_temperature(target_temp, enable_cooler=True)
        self.cam.set_fan_mode("full")
        print(f"Fan mode set to: {self.cam.get_fan_mode()}")

        while not self.cancel_cooling:
            
            try:
                temp = round(self.cam.get_temperature(),2)
                print(f"Cooling: {temp}, Status: {self.cam.get_temperature_status()}")
            except:
                break

            if temp <= target_temp+20:      
                print(f"Temperature stabilized, Status: {self.cam.get_temperature_status()}")
                break

            time.sleep(1)

    @requires_cam_connected
    def stop_cooling(self):
        """
        Request an early exit from the cool_cam() loop by setting cancel_cooling = True.
        """
        self.cancel_cooling = True

    @requires_cam_connected
    def warm_cam(self,safe_temp:float=-20):
        """
        Turn off the cooler and fan to begin warming the sensor.
 
        Note: This method returns immediately; the sensor continues to warm passively.
 
        Args:
            safe_temp: Intended safe temperature threshold (currently unused –
                       the cooler is simply disabled without waiting).
        """
        self.cam.set_fan_mode("off")
        self.cancel_cooling = True

        self.cam.set_cooler(on=False)
        print("Warming (cooler OFF)")

        
    def get_temp(self):
        """
        Return the current sensor temperature and status string.
 
        Returns:
            Tuple (temperature_float, status_str) or ('--', '') if no camera is connected.
        """
        if not self.cam:
            return "--",""
        return round(self.cam.get_temperature(),3), self.cam.get_temperature_status()

    
    # ==== DISCONNECT CAMERA =====

    def safe_close(self):
        """
        Safely disconnect the camera: cancel any in-progress cooling or acquisition,
        then call close_cam() to release the SDK handle.
        """
        if not self.cam:
            return
        
        self.cancel_cooling=True
        
        try:
            if self.cam.acquisition_in_progress():
                self.cam.stop_acquisition()
        except:
            pass
        
        self.close_cam()
        return

    def close_cam(self):
        """
        Turn off the fan and release the Andor SDK camera handle.
 
        Sets self.cam to None after closing.
        """
        if self.cam:
            self.cam.set_fan_mode("off")
            self.cam.close()
            self.cam = None
            print("Camera disconnected safely")
    

    # ===== LIVE VIDEO =====

    @requires_cam_connected
    def start_live(self,acquisition_mode="single"):
        """
        Capture one 'tick' of live preview by acquiring the configured number of frames.
 
        For single mode: one snap.
        For accum mode:  num_acc sequential snaps collected into a list.
        For kinetic / fast_kinetic: a grab of num_frames frames.
        Continuous mode is not supported here (raises RuntimeError).
 
        Args:
            acquisition_mode: One of 'single', 'accum', 'kinetic', 'fast_kinetic'.
 
        Returns:
            List of ndarrays, one per acquired frame.
 
        Raises:
            RuntimeError: If no frames were obtained or continuous mode was requested.
        """
        print("Live mode started")

        timeout = self.calc_frame_timeout()
        self.cam.stop_acquisition() 
        frames = None

        try:
            if acquisition_mode == "single":
                self.cam.set_acquisition_mode("single",setup_params=True)  
                frames = [self.cam.snap(timeout=timeout,return_info=False)]

            elif acquisition_mode == "accum":
                num_frames = self.cam.get_accum_mode_parameters()[0]
                self.cam.set_acquisition_mode("single",setup_params=True)  
                print("accum params:", self.cam.get_accum_mode_parameters())
                frames = []
                for _ in range(num_frames):
                    frames.append(self.cam.snap(timeout=timeout,return_info=False))
                    self.cam.stop_acquisition()      
                    self.cam.clear_acquisition()    

            elif acquisition_mode == "kinetic":
                self.cam.set_acquisition_mode("kinetic",setup_params=True)   
                num_frames = self.cam.get_kinetic_mode_parameters()[0]
                frames = self.cam.grab(nframes=num_frames, frame_timeout=timeout, missing_frame='skip', return_info=False, buff_size=None)

            elif acquisition_mode == "fast_kinetic":
                self.cam.set_acquisition_mode("fast_kinetic",setup_params=True)   
                num_frames = self.cam.get_fast_kinetic_mode_parameters()[0]
                frames = self.cam.grab(nframes=num_frames, frame_timeout=timeout, missing_frame='skip', return_info=False, buff_size=None)

            elif acquisition_mode == "cont":
                raise RuntimeError("Continuous mode cannot be used for save acquisition")

        finally:
            self.cam.stop_acquisition()    
            self.cam.clear_acquisition()    

        if frames is None:
            raise RuntimeError("No frames were obtained")
            return
        return frames

    @requires_cam_connected
    def stop_live(self):
        """Stop any in-progress acquisition and clear the hardware frame buffer."""
        self.cam.stop_acquisition()     
        self.cam.clear_acquisition()  
        print("Live mode stopped")
        return

    @requires_cam_connected
    def get_live_frame(self):
        """
        Capture a single snap for live preview purposes (5 s timeout).
 
        Returns:
            2-D ndarray or None if the camera is unavailable.
        """
        if not self.cam:
            print(f"Could not obtain the frame for the preview. Cam: {self.cam}")
            return None
        return self.cam.snap(timeout=5.0,return_info=False)  


    # ===== ACQUISITION =====

    @requires_cam_connected
    def acquisition_in_progress(self):
        """
        Check whether the camera is currently running an acquisition.
 
        Returns:
            True if an acquisition is active, False otherwise.
        """
        return self.cam.acquisition_in_progress()

    @requires_cam_connected
    def get_acquisition_progress(self):
        """
        Return acquisition progress counters from the hardware.
 
        Returns:
            Tuple (frames_done, accumulations_done).
        """
        return self.cam.get_acquisition_progress()

    @requires_cam_connected
    def single_preview(self):
        """
        Perform a single snap to preview the current settings without saving.
 
        Returns:
            2-D ndarray of the acquired frame.
 
        Raises:
            RuntimeError: If no frame was returned by the hardware.
        """
        timeout = self.calc_frame_timeout()
        self.cam.stop_acquisition()     
        try:
            frame = self.cam.snap(timeout=timeout,return_info=False)
        finally:
            self.cam.stop_acquisition()     
            self.cam.clear_acquisition()  

        if frame is None or not frame.any():   
            raise RuntimeError("Could not obtain frame for single preview")
            return
        return frame

    @requires_cam_connected
    def start_acquisition(self):
        """
        Execute a full acquisition (single, accum, kinetic, or fast_kinetic) using
        the mode currently configured on the hardware.
 
        Returns:
            List of ndarrays – one per acquired frame.
 
        Raises:
            RuntimeError: If continuous mode is attempted or no frames are returned.
        """
        timeout = self.calc_frame_timeout()

        print(f"Acquisition parameters: {self.cam.get_acquisition_parameters()}")
        print(f"Acquisition mode: {self.cam.get_acquisition_mode()}")
        print(f"Status before start: {self.cam.get_status()}")
        self.cam.stop_acquisition()  
        acquisition_mode = self.cam.get_acquisition_mode()
        frames = None

        try:
            if acquisition_mode == "single":
                self.cam.set_acquisition_mode("single",setup_params=True)  
                frames = [self.cam.snap(timeout=timeout,return_info=False)]
            elif acquisition_mode == "accum":
                num_frames = self.cam.get_accum_mode_parameters()[0]
                self.cam.set_acquisition_mode("single",setup_params=True)  
                print("accum params:", self.cam.get_accum_mode_parameters())
                frames = []
                for _ in range(num_frames):
                    frames.append(self.cam.snap(timeout=timeout,return_info=False))
                    self.cam.stop_acquisition()     
                    self.cam.clear_acquisition()   

            elif acquisition_mode == "kinetic":
                self.cam.set_acquisition_mode("kinetic",setup_params=True)  
                num_frames = self.cam.get_kinetic_mode_parameters()[0]
                frames = self.cam.grab(nframes=num_frames, frame_timeout=timeout, missing_frame='skip', return_info=False, buff_size=None)
            elif acquisition_mode == "fast_kinetic":
                self.cam.set_acquisition_mode("fast_kinetic",setup_params=True)  
                num_frames = self.cam.get_fast_kinetic_mode_parameters()[0]
                frames = self.cam.grab(nframes=num_frames, frame_timeout=timeout, missing_frame='skip', return_info=False, buff_size=None)
            elif acquisition_mode == "cont":
                raise RuntimeError("Continuous mode cannot be used for save acquisition")

        finally:
            self.cam.stop_acquisition()      
            self.cam.clear_acquisition()  

        if frames is None:
            raise RuntimeError("No frames were obtained")
            return
        return frames

    @requires_cam_connected
    def stop_acquisition(self):
        """Abort any in-progress acquisition and clear the hardware buffer."""
        self.cam.stop_acquisition()
        self.cam.clear_acquisition()
        return

    @requires_cam_connected
    def simple_acq(self,num_frames:int=0):
        """
        Convenience wrapper for quick acquisitions without mode configuration.
 
        Args:
            num_frames: 0 = single snap; any positive value = grab that many frames.
 
        Returns:
            Single ndarray (num_frames == 0) or list of ndarrays.
        """
        if num_frames == 0:
            frame = self.cam.snap()  
            print("Single frame acquired")
            return frame
        else:
            frames = self.cam.grab(num_frames) 
            print("Multiple frames acquired")
            return frames


    # ==== VALIDAION =====

    def validate_EMCCD_gain(self,emccd_gain:float,advanced:bool):
        """
        Validate the requested EMCCD gain value.
 
        Args:
            emccd_gain: Gain value to validate.
            advanced:   If True, values above 300 are permitted.
 
        Raises:
            ValueError: If gain > 300 without advanced mode.
 
        Note: Negative values are silently clamped to 0.
        """
        if emccd_gain < 0:
            emccd_gain = 0
        if emccd_gain > 300 and not advanced:
            raise ValueError(f"Invalid EMCCD gain {emccd_gain}, to set above 300 use advanced option")
        return

    def validate_exposure(self,exposure:float):
        """
        Validate the requested exposure time.
 
        Args:
            exposure: Exposure time in seconds.
 
        Raises:
            ValueError: If exposure is negative.
        """
        if exposure < 0:
            raise ValueError(f"Invalid exposure time {exposure}, can not be negative")
        return

    def validate_amp(self,channel:Optional[int],oamp:Optional[int],hsspeed:Optional[int],preamp:Optional[int]):
        return

    def validate_single_track_mode(self, center:int, width:int):
        return

    def validate_multi_track_mode(self, number:int, height:int, offset:int):
        return

    def validate_read_mode(self, read_mode:str):
        """
        Validate the read mode string against the set of supported modes.
 
        Args:
            read_mode: Mode string to validate.
 
        Raises:
            ValueError: If read_mode is not in the supported set.
        """
        valid_modes = {"fvb", "image", "single_track", "multi_track", "random_track"}
        if read_mode not in valid_modes:
            raise ValueError(f"Invalid read mode: {read_mode}. Valid modes are: {valid_modes}")

    def validate_shutter_settings(self, mode:str, ttl_mode:int, open_time:Optional[float], close_time:Optional[float]):
        """
        Validate shutter parameters before applying them to the hardware.
 
        Silently clamps open_time / close_time values to the hardware minimums
        if they are below them.
 
        Args:
            mode:       Shutter mode string ('auto', 'open', 'closed').
            ttl_mode:   0 = low is open; 1 = high is open.
            open_time:  Requested opening time in ms, or None.
            close_time: Requested closing time in ms, or None.
 
        Returns:
            True on success.
 
        Raises:
            ValueError: If mode is invalid or ttl_mode is not 0 or 1.
        """
        valid_modes = ["auto", "open", "closed"]
        if mode not in valid_modes:
            raise ValueError(f"Invalid shutter mode: {mode}. Valid modes are: {valid_modes}.")
        
        if ttl_mode not in [0, 1]:
            raise ValueError("TTL mode must be 0 (low is open) or 1 (high is open).")
        
        min_open, min_close = self.get_min_shutter_times()
        
        if open_time is not None and open_time < min_open:
            open_time = min_open
        
        if close_time is not None and close_time < min_close:
            close_time = min_close
        
        return True

    def validate_acquisition_mode(self, mode:str):
        """
        Validate the acquisition mode string.
 
        Args:
            mode: Acquisition mode string to check.
 
        Returns:
            True on success.
 
        Raises:
            ValueError: If mode is not in the supported set.
        """
        valid_modes = ["single", "accum", "kinetic", "fast_kinetic", "cont"]
        if mode not in valid_modes:
            raise ValueError(f"Invalid acquisition mode: {mode}. Valid modes are: {valid_modes}.")

        return True

    def validate_trigger_mode(self, mode:str):
        """
        Validate the trigger mode string.
 
        Args:
            mode: Trigger mode string to check.
 
        Returns:
            True on success.
 
        Raises:
            ValueError: If mode is not in the supported set.
        """
        valid_modes = ["int","ext","ext_start","ext_exp","ext_fvb_em","software","ext_charge_shift"]
        if mode not in valid_modes:
            raise ValueError(f"Invalid trigger mode: {mode}. Valid modes are: {valid_modes}.")
        
        return True

    def validate_roi(self,hstart:int, hend:Optional[int], vstart:int, vend:Optional[int], hbin:int, vbin:int):
        """
        Validate and clamp ROI parameters against hardware limits for the given binning.
 
        None values and out-of-range values are silently replaced with valid defaults.
 
        Args:
            hstart: Horizontal start pixel.
            hend:   Horizontal end pixel (None = hardware max).
            vstart: Vertical start pixel.
            vend:   Vertical end pixel (None = hardware max).
            hbin:   Horizontal binning factor.
            vbin:   Vertical binning factor.
 
        Returns:
            Validated/clamped tuple (hstart, hend, vstart, vend, hbin, vbin).
 
        Raises:
            ValueError: If end <= start or the ROI size is not divisible by the
                        binning factor.
        """
        if hbin is None or hbin < 1:
            hbin = 1
        if vbin is None or vbin < 1:
            vbin = 1
        
        h_limits, v_limits = self.get_roi_limits(hbin=hbin,vbin=vbin)
        hmin,hmax,hpstep,hsstep,hmaxbin = h_limits
        vmin,vmax,vpstep,vsstep,vmaxbin = v_limits
        print(f"horizontal limits: hmin={hmin}, hmax={hmax}, hpstep={hpstep}, hsstep={hsstep}, hmaxbin={hmaxbin}")
        print(f"vertical limits: vmin={vmin}, vmax={vmax}, vpstep={vpstep}, vsstep={vsstep}, vmaxbin={vmaxbin}")

        if hstart is None or hstart < 0:
            hstart = 0
        if vstart is None or vstart < 0:
            vstart = 0
        if hend is None or hend > hmax:
            hend = hmax
        if vend is None or vend > vmax:
            vend = vmax

        if hend <= hstart or vend <= vstart:
            raise ValueError("ROI end positions must be greater than start positions.")

        if (hend - hstart+1) % hbin != 0 or (vend - vstart+1) % vbin != 0:
            raise ValueError(f"ROI width and height must be divisible by binning factors.{(hend - hstart+1) % hbin}")
        return hstart, hend, vstart, vend, hbin, vbin

    def validate_bit_shift(self,bit_shift_pixels,bit_shift_vstart,bit_shift_vend):
        """
        Validate and clamp bit-shift parameters against the current ROI boundaries.
 
        Args:
            bit_shift_pixels: Pixel shift amount.
            bit_shift_vstart: Start row of the shift region (clamped to ROI vstart).
            bit_shift_vend:   End row of the shift region (clamped to ROI vend).
 
        Returns:
            Validated tuple (bit_shift_pixels, bit_shift_vstart, bit_shift_vend).
 
        Raises:
            ValueError: If the resulting vstart > vend.
        """
        if bit_shift_pixels is None:
            bit_shift_pixels

        _,_,vstart,vend,_,_ = self.get_roi()
        if bit_shift_vstart is None or bit_shift_vstart<vstart:
            bit_shift_vstart = vstart
        if bit_shift_vend is None or bit_shift_vend>vend:
            bit_shift_vend = vend
        if bit_shift_vstart > bit_shift_vend:
            raise ValueError(f"Bit shift region should be between {vstart} - {vend}")
        return bit_shift_pixels,bit_shift_vstart,bit_shift_vend


    # ===== FILE MANAGEMENT =====

    #UNUSED
    def save_image(self,frames,filename=None):   
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
        else:
            png_path = self.save_path / f"{filename.replace('.npz', '.png')}"

        for idx,frame in enumerate(frames):

            if frame.size == 0:
                print("Empty frame")
                return

            plt.imsave(png_path, frame,cmap="gray")

        print(f"[SAVE] Frames saved to {png_path}")
        return

    #UNUSED
    def get_save_path(self):
        return self.save_path

    #UNUSED
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

    #UNUSED
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

    #UNUSED
    def set_save_frame_path(self,path):
        self.save_path = path
        self.save_path_image = path
        self.save_path_csv = path

    def set_dlls_path(self,dlls_path):
        pll.par["devices/dll/andor_sdk2"] = dlls_path
    
    #UNUSED
    def save_data(self, frame, spectrum, timestamp):
        np.savetxt(self.save_path / f"{timestamp}_frame.csv", frame, delimiter=",", fmt="%d") 
        np.savetxt(self.save_path / f"{timestamp}_spectrum.csv", spectrum, delimiter=",", fmt="%d")    
    
    #UNUSED
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

    #UNUSED
    def display_spectrogram(self, frames):
        if frames is not None:
            frame = frames[-1]

            if frame.ndim == 2:
                spectrum = frame.sum(axis=0)
            else:
                spectrum = frame

            self.view.show_calibration_result(frame, spectrum)

    #UNUSED
    def plot_spec(self,spectrum,exp_time):

        self.save_path.mkdir(parents=True, exist_ok=True)
        plt.figure()
        plt.plot(spectrum)
        plt.title("Spectrum")
        plt.savefig(self.save_path / f"{exp_time}_plot.png", dpi=200)


    # ==== MATH =====

    #UNUSED
    def combine_frames(self,frames,acq_mode="single",num_frames=1,result_mode="sum"):
        if isinstance(frames, np.ndarray):
            frames = [frames]

        if acq_mode in ["kinetic", "fast_kinetic"]:
            combined = np.sum(frames, axis=0)

            if result_mode == "avg":
                combined = combined / num_frames

        else:
            frame = frames[-1]

            if acq_mode == "accum":

                if result_mode == "avg":
                    frame = frame / num_frames

            combined = frame

        return combined

    #UNUSED
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

    #UNUSED
    def adjust_frame(self,frame):
        m = frame.max()
        if m == 0:
            frame8 = np.zeros_like(frame,dtype=np.uint8)
        else:
            frame8 = (frame / frame.max() * 255).astype(np.uint8) 
        h, w = frame8.shape
        return (frame8,h,w)
