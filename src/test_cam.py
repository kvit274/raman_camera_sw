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
    """
        Initialise the TestCameraModel with default hardware-simulation parameters.
 
        Sets up ROI bounds, shutter settings, read/acquisition/trigger modes,
        exposure, amplifier modes, vertical shift speeds, EMCCD gain, output
        directories, frame-transfer mode flag, and bit-shift correction parameters.
        All directories (./data, ./data/csv, ./data/images) are created if absent.
        """
    def __init__(self):

        self.cam = None
        self.temp = 20.0 

        # roi params
        self.hstart = 0
        self.hend = 1024
        self.vstart = 0
        self.vend = 256
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


        # bit shifting info
        self.bit_shift_pixels = 0
        self.bit_shift_vstart = None
        self.bit_shift_vend = None


    # ==== DECORATORS =====

    def requires_cam_connected(func):
        """
        Decorator that guards a method against being called without an active camera.
 
        Raises:
            RuntimeError: If 'self.cam' is falsy (camera not connected).
        """
        def wrapper(self, *args, **kwargs):
            if not self.cam:
                raise RuntimeError("Camera not connected")
            return func(self, *args, **kwargs)
        return wrapper


    # ===== CAMERA SETTINGS =====

    def get_device_info(self):
        """
        Return a human-readable string describing the simulated camera device.
 
        Returns:
            str: Static device description including model, serial number, and firmware.
        """ 
        return "Andor Newton, Serial: 12345, Firmware: 1.0.0"

    def connect_cam(self):
        """
        Simulate connecting to the camera and initiating the cooling sequence.
 
        On a real device, hardware parameters are set to their slowest/safest defaults
        and the shutter is closed.  In the test model this sets 'self.cam' and calls
        'cool_cam()'.
 
        Raises:
            RuntimeError: If the camera is already connected.
        """
        if self.cam:
            raise RuntimeError("Camera already connected")
        self.cam = "Andor Newton"
        self.cool_cam()

    @requires_cam_connected
    def get_cam_params(self,save_path=Path("./cam_params.txt")):
        """
        Collect camera parameters and write them to a human-readable text file.
 
        Args:
            save_path: Destination path for the output file (default: ./cam_params.txt).
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
        Return the full detector dimensions, unaffected by any ROI setting.
 
        Returns:
            Tuple[int, int]: '(width, height)' in pixels – always (1024, 256)
            for this simulated camera.
        """
        return (1024,256)
    
    @requires_cam_connected
    def get_data_dim(self):
        """
        Return the output frame dimensions after applying the current ROI and binning.
 
        Returns:
            Tuple[int, int]: '(width, height)' in binned pixels.
        """
        hstart,hend,vstart,vend,hbin,vbin = self.get_roi()
        width = (hend-hstart)//hbin
        height = (vend-vstart)//vbin
        return (width,height)
    
    @requires_cam_connected
    def calc_frame_timeout(self, extra=5.0, min_timeout=5.0):
        """
        Calculate a safe timeout duration for a single frame acquisition.
 
        The timeout is the exposure time plus 'extra' seconds, floored at
        'min_timeout'.
 
        Args:
            extra:       Additional seconds added on top of the exposure time.
            min_timeout: Minimum timeout value regardless of exposure (seconds).
 
        Returns:
            float: Timeout in seconds.
        """
        exp = float(self.get_exposure())
        return max(min_timeout, exp + extra)

    @requires_cam_connected
    def get_exposure(self):
        """
        Return the currently set exposure time.
 
        Returns:
            float: Exposure time in seconds.
        """
        return self.exposure
    
    # ==== ROI and Binning =====

    @requires_cam_connected
    def get_max_binning(self):
        """
        Return the maximum supported binning factors.
 
        Returns:
            Tuple[int, int]: '(max_hbin, max_vbin)' – always (4, 4) for this model.
        """
        return (4,4)

    @requires_cam_connected
    def get_roi(self):
        """
        Return the currently active region-of-interest and binning parameters.
 
        Returns:
            Tuple[int, int, int, int, int, int]:
            '(hstart, hend, vstart, vend, hbin, vbin)'.
        """
        return (self.hstart, self.hend, self.vstart, self.vend, self.hbin, self.vbin)

    @requires_cam_connected
    def set_roi(self,hstart:int=0, hend:Optional[int]=1024, vstart:int=0, vend:Optional[int]=256, hbin:int=1, vbin:int=1):
        """
        Validate and apply new ROI and binning parameters.
 
        Args:
            hstart: First horizontal pixel (inclusive, 0-based).
            hend:   Last horizontal pixel (exclusive).
            vstart: First vertical pixel (inclusive, 0-based).
            vend:   Last vertical pixel (exclusive).
            hbin:   Horizontal binning factor.
            vbin:   Vertical binning factor.
        """
        hstart,hend,vstart,vend,hbin,vbin = self.validate_roi_settings(hstart, hend, vstart, vend, hbin, vbin)
        self.hstart = hstart
        self.hend = hend
        self.vstart = vstart
        self.vend = vend
        self.hbin = hbin
        self.vbin = vbin
        print(f"ROI set to: x={hstart}->{hend} | y={vstart}->{vend} | hbin: {hbin}, vbin: {vbin}")

    @requires_cam_connected
    def get_roi_limits(self,hbin=1,vbin=1):
        """
        Return the valid ROI parameter ranges for the given binning factors.
 
        Args:
            hbin: Horizontal binning factor (default 1).
            vbin: Vertical binning factor (default 1).
 
        Returns:
            Tuple[tuple, tuple]: '(hlim, vlim)' where each limit tuple is
            '(min, max, step, bin, maxbin)'.
        """
        if hbin is None:
            hbin = 1
        if vbin is None:
            vbin = 1
        
        det_w, det_h = self.detect_cam_size()
        hmaxbin, vmaxbin = 32, 32

        hbin = max(1,min(int(hbin),hmaxbin))
        vbin = max(1,min(int(vbin),vmaxbin))

        hlim = (hbin,det_w,1,hbin,hmaxbin)
        vlim = (vbin,det_h,1,vbin,vmaxbin)
        return (hlim, vlim)


    # ==== SHUTTER SETUP ====

    @requires_cam_connected
    def get_shutter_parameters(self):
        """
        Return the current shutter configuration.
 
        Returns:
            Tuple: '(mode, ttl_mode, open_time, close_time)'.
        """
        return (self.shutter_mode, self.ttl_mode, self.open_time, self.close_time)

    @requires_cam_connected
    def setup_shutter(self, mode:str, ttl_mode:int=0, open_time:Optional[float]=None, close_time:Optional[float]=None):
        """
        Validate and apply new shutter parameters.
 
        Args:
            mode:       Shutter mode – 'auto', 'open', or 'closed'.
            ttl_mode:   TTL logic: '0' = low is open, '1' = high is open.
            open_time:  Minimum shutter opening time in ms.
            close_time: Minimum shutter closing time in ms.
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
        Return the minimum shutter open and close times supported by this camera.
 
        Returns:
            Tuple[int, int]: '(min_open_ms, min_close_ms)' – always (5, 5).
        """
        return (5, 5)

    @requires_cam_connected
    def get_shutter(self):
        """
        Return the current shutter state string.
 
        Returns:
            str: One of 'auto', 'open', or 'closed'.
        """
        return self.shutter_mode
    

    @requires_cam_connected
    def set_default_settings(self):
        """
        Apply safe default camera settings (single acquisition mode).
 
        Intended to be called once after connection to put the camera into a
        known-good state before any user configuration is applied.
        """
        self.setup_single_mode()

        print(f"Camera initialized")
        return

    @requires_cam_connected
    def get_settings(self,include=-10):
        """
        Return a simulated snapshot of all current camera settings.
 
        Mirrors the dictionary structure returned by a real pylablib Andor camera
        so that upstream code can be tested without physical hardware.
 
        Args:
            include: Unused parameter kept for API compatibility.
 
        Returns:
            dict: Fixed settings dictionary representing a realistic camera state.
        """
        settings = {'image_indexing': 'rcb', 'frame_format': 'list', 'frame_info_format': 'namedtuple', 'frame_info_period': 1, 'roi': (0, 1024, 0, 256, 1, 1), 'temperature': -85, 'cooler': True, 'channel': 0, 'oamp': 0, 'hsspeed': 0, 'preamp': 1, 'vsspeed': 1, 'shutter': ('open', 0, 0, 0), 'fan_mode': 'full', 'trigger_mode': 'int', 'acq_parameters/accum': (1, 0), 'acq_parameters/kinetic': (1, 0.0, 1, 0, 0), 'acq_parameters/fast_kinetic': (1, 0.0), 'acq_parameters/cont': 0, 'acq_mode': 'single', 'frame_transfer': None, 'read_parameters/single_track': (0, 1), 'read_parameters/multi_track': (1, 1, 0), 'read_parameters/random_track': [(0, 1)], 'read_parameters/image': (0, 1024, 0, 256, 1, 1), 'read_mode': 'image', 'exposure': 0.05000000074505806, 'frame_period': 0.1457899957895279}
        return settings

    # ==== READ MODE =====

    @requires_cam_connected
    def set_read_mode(self, read_mode:str):
        """
        Validate and apply a new detector read mode.
 
        Args:
            read_mode: One of 'fvb', 'image', 'single_track',
                       'multi_track', or 'random_track'.
 
        Raises:
            ValueError: If 'read_mode' is not a recognised value.
        """
        self.validate_read_mode(read_mode)
        self.read_mode = read_mode
        print(f"Read mode set to: {read_mode}")
        return

    @requires_cam_connected
    def get_read_mode(self):
        """
        Return the currently active read mode string.
 
        Returns:
            str: Active read mode (e.g. 'image', 'fvb').
        """
        return self.read_mode

    @requires_cam_connected
    def setup_single_track_mode(self, mode,center:int=0, width:int=1):
        """
        Configure and activate single-track read mode.
 
        A single horizontal strip of 'width' rows centred at 'center' is read.
 
        Args:
            mode:   Unused – kept for API symmetry with the real camera wrapper.
            center: Row index of the track centre.
            width:  Number of rows to bin into a single track.
        """
        self.validate_single_track_mode(center, width)
        self.set_read_mode("single_track")
        return

    @requires_cam_connected
    def get_single_track_mode_params(self):
        """
        Return the current single-track read mode parameters.
 
        Returns:
            Tuple[int, int]: '(center, width)' – the row centre and track width.
        """
        return (0, 1)

    @requires_cam_connected
    def setup_multi_track_mode(self,mode, number:int=1, height:int=1, offset:int=0):
        """
        Configure and activate multi-track read mode.
 
        Multiple horizontal strips are read simultaneously.
 
        Args:
            mode:   Unused – kept for API symmetry with the real camera wrapper.
            number: Number of tracks to read.
            height: Height (in rows) of each individual track.
            offset: Pixel offset between adjacent track centres.
        """
        self.validate_multi_track_mode(number, height, offset)
        print("Trying to set multi-track mode")
        self.set_read_mode("multi_track")
        return

    @requires_cam_connected
    def get_multi_track_mode_params(self):
        """
        Return the current multi-track read mode parameters.
 
        Returns:
            Tuple[int, int, int]: '(number, height, offset)'.
        """
        return (1, 1, 0)

    @requires_cam_connected
    def setup_random_track_mode(self,mode, tracks=None):
        """
        Configure random-track read mode with an arbitrary set of row spans.
 
        Each entry in 'tracks' defines an independent strip to be read.
        This method does not change the active read mode; call 'set_read_mode'
        separately.
 
        Args:
            mode:   Unused – kept for API symmetry with the real camera wrapper.
            tracks: List of '(start, stop)' tuples where start is inclusive and
                    stop is exclusive (0-based row indices).
        """
        return

    @requires_cam_connected
    def get_random_track_mode_params(self):
        """
        Return the current random-track mode row-span parameters.
 
        Returns:
            Tuple[int, int]: A single '(start, stop)' span representing the
            simulated track configuration.
        """
        return (10,20)

    @requires_cam_connected
    def setup_image_mode(self,mode,hstart:int=0, hend:Optional[int]=1024, vstart:int=0, vend:Optional[int]=256, hbin:int=1, vbin:int=1):
        """
        Configure and activate full-image (2-D) read mode with the given ROI and binning.
 
        Args:
            mode:   Unused – kept for API symmetry with the real camera wrapper.
            hstart: First horizontal pixel (inclusive).
            hend:   Last horizontal pixel (exclusive).
            vstart: First vertical pixel (inclusive).
            vend:   Last vertical pixel (exclusive).
            hbin:   Horizontal binning factor.
            vbin:   Vertical binning factor.
        """
        self.validate_roi_settings(hstart, hend, vstart, vend, hbin, vbin)
        self.set_roi(hstart, hend, vstart, vend, hbin, vbin)
        self.set_read_mode("image")
        return 

    def setup_bit_shifting(self,bit_shift_pixels,bit_shift_vstart,bit_shift_vend):
        """
        Validate and store bit-shift correction parameters.
 
        Pixel shifting is applied during frame processing to correct spectral
        offsets within the designated row region.
 
        Args:
            bit_shift_pixels: Number of pixels to shift (negative = left).
            bit_shift_vstart: First row (absolute detector coordinate) of the
                              correction region.
            bit_shift_vend:   Last row (exclusive) of the correction region.
        """
        bit_shift_pixels,bit_shift_vstart,bit_shift_vend = self.validate_bit_shift(bit_shift_pixels,bit_shift_vstart,bit_shift_vend)
        self.bit_shift_pixels = bit_shift_pixels
        self.bit_shift_vstart = bit_shift_vstart
        self.bit_shift_vend = bit_shift_vend
        return

    def get_bit_shifting(self):
        """
        Return the current bit-shift correction parameters.
 
        Returns:
            Tuple: '(bit_shift_pixels, bit_shift_vstart, bit_shift_vend)'.
        """
        return self.bit_shift_pixels,self.bit_shift_vstart,self.bit_shift_vend

    @requires_cam_connected
    def get_image_mode_parameters(self):
        """
        Return the active image-mode ROI parameters.
 
        Returns:
            Tuple[int, None, int, None, int, int]:
            '(hstart, hend, vstart, vend, hbin, vbin)' where 'None' indicates
            the full detector extent is used.
        """
        return (0,None,0,None,1,1)

    
    # ===== ACQUISITION MODE =====

    @requires_cam_connected
    def acquisition_in_progress(self):
        """
        Check whether the camera is currently acquiring frames.
 
        Returns:
            bool: Always 'False' for the simulated camera.
        """
        return False

    @requires_cam_connected
    def get_acquisition_progress(self):
        """
        Return the current acquisition progress counters.
 
        Returns:
            Tuple[int, int]: '(accumulated_frames, kinetic_cycles)' –
            both zero for the simulated camera.
        """
        return (0,0)

    @requires_cam_connected
    def setup_single_mode(self):
        """
        Configure the camera for single-frame acquisition mode.
 
        One frame is captured per trigger event.
        """
        self.acquisition_mode = "single"
        return

    @requires_cam_connected
    def setup_accum_mode(self,mode,num_acc:int, cycle_time_acc:Optional[float]=0, result_mode="sum"):
        """
        Configure the camera for accumulation acquisition mode.
 
        Multiple frames are accumulated (on-chip or in software) to improve SNR.
 
        Args:
            mode:          Unused – kept for API symmetry.
            num_acc:       Number of frames to accumulate.
            cycle_time_acc: Minimum time between accumulations in seconds.
            result_mode:   How to combine frames – 'sum' or 'avg'.
        """
        self.acquisition_mode = "accum"
        return

    @requires_cam_connected
    def setup_kinetic_mode(self,mode, num_cycle:int, cycle_time:Optional[float]=0, num_acc:Optional[int]=1, cycle_time_acc:Optional[float]=0, num_prescan:Optional[int]=0,result_mode="sum"):
        """
        Configure the camera for kinetic series acquisition mode.
 
        A sequence of accumulation sets is captured with a programmable inter-cycle delay.
 
        Args:
            mode:          Unused – kept for API symmetry.
            num_cycle:     Number of kinetic cycles in the series.
            cycle_time:    Time between the start of successive kinetic cycles (seconds).
            num_acc:       Number of accumulations per kinetic cycle.
            cycle_time_acc: Minimum time between accumulations (seconds).
            num_prescan:   Number of pre-scan (clean) frames before the series.
            result_mode:   Combination method – 'sum' or 'avg'.
        """
        self.acquisition_mode = "kinetic"
        return

    @requires_cam_connected
    def setup_fast_kinetic_mode(self, mode,num_acc:int, cycle_time_acc:Optional[float]=0,result_mode="sum"):
        """
        Configure the camera for fast-kinetic acquisition mode.
 
        Uses on-chip storage to capture frames at the highest possible rate.
 
        Args:
            mode:          Unused – kept for API symmetry.
            num_acc:       Number of frames to capture in the fast-kinetic burst.
            cycle_time_acc: Minimum inter-frame time (seconds).
            result_mode:   Combination method – 'sum' or 'avg'.
        """
        self.acquisition_mode = "fast_kinetic"
        return
    
    @requires_cam_connected
    def setup_cont_mode(self,mode, cycle_time:Optional[float]=0):
        """
        Configure the camera for continuous (video) acquisition mode.
 
        Frames are captured repeatedly until acquisition is stopped.
 
        Args:
            mode:       Unused – kept for API symmetry.
            cycle_time: Minimum time between successive frames (seconds).
        """
        self.acquisition_mode = "cont"
        return

    
    # ===== TRIGGER MODE =====

    @requires_cam_connected
    def set_trigger_mode(self,mode:str):
        """
        Validate and apply a new trigger mode.
 
        Args:
            mode: One of 'int', 'ext', 'ext_start', 'ext_exp',
                  'ext_fvb_em', 'software', or 'ext_charge_shift'.
 
        Raises:
            ValueError: If 'mode' is not a recognised trigger mode.
        """
        self.validate_trigger_mode(mode)
        self.trigger_mode = mode
        return

    # ==== EXPOSURE ====

    @requires_cam_connected
    def set_exposure(self,exposure:float):
        """
        Validate and apply a new exposure time.
 
        Args:
            exposure: Desired exposure time in seconds. Must be non-negative.
 
        Raises:
            ValueError: If 'exposure' is negative.
        """
        self.validate_exposure(exposure)
        self.exposure = exposure
        return

    # ==== AMP MODE ====

    @requires_cam_connected
    def get_all_amp_modes(self):
        """
        Return all available amplifier mode configurations.
 
        Returns:
            List[TAmpModeFull]: Simulated list of supported amp modes.
        """
        return self.all_amp_modes

    @requires_cam_connected
    def set_amp_mode(self,channel:Optional[int],oamp:Optional[int],hsspeed:Optional[int],preamp:Optional[int]):
        """
        Validate and apply a new amplifier mode.
 
        Args:
            channel:  Output channel index.
            oamp:     Output amplifier index.
            hsspeed:  Horizontal shift speed index.
            preamp:   Pre-amplifier gain index.
        """
        self.validate_amp(channel,oamp,hsspeed,preamp)
        self.amp_mode.set_mode(channel,oamp,hsspeed,preamp)
        return

    # ==== VSSPEED ====

    @requires_cam_connected
    def get_all_vsspeeds(self):
        """
        Return the list of all supported vertical shift speeds in µs/pixel.
 
        Returns:
            List[float]: Available vertical shift speeds.
        """
        return self.all_vsspeeds

    @requires_cam_connected
    def set_vsspeed(self,vsspeed_idx:int):
        """
        Select a vertical shift speed by its index in the supported speed list.
 
        Args:
            vsspeed_idx: Zero-based index into 'self.all_vsspeeds'.
        """
        self.vsspeed = self.all_vsspeeds[vsspeed_idx]
        print(f"Vsspeed set to: {self.vsspeed}")
        return

    # ==== EMCCD GAIN ====

    @requires_cam_connected
    def set_EMCCD_gain(self,emccd_gain, emccd_advanced=False):
        """
        Validate and apply a new EMCCD gain value.
 
        Args:
            emccd_gain:     Desired EM gain (0–300 normally, up to higher values
                            when 'emccd_advanced' is True).
            emccd_advanced: Allow gain values above 300 if 'True'.
 
        Raises:
            ValueError: If gain exceeds 300 and 'emccd_advanced' is 'False'.
        """
        self.validate_EMCCD_gain(emccd_gain, emccd_advanced)
        self.emccd_gain = emccd_gain
        print(f"EMCCD gain set to: {self.emccd_gain}")
        return
    
    # ===== COOLING =====

    def get_temp(self):
        """
        Return the current sensor temperature and a status string.
 
        Returns:
            Tuple[str | float, str]: '(temperature, status_string)'.
            Returns '("--", "")' when no camera is connected.
        """
        if not self.cam:
            return "--",""
        
        return self.temp, "Some status"

    @requires_cam_connected
    def cool_cam(self,target_temp:float=-85.0):
        """
        Simulate the sensor cooling sequence down to 'target_temp'.
 
        Temperature is decremented in 5 °C steps with a 100 ms delay between
        steps.  The loop respects 'self.cancel' so that cooling can be
        interrupted externally.
 
        Args:
            target_temp: Target sensor temperature in °C (default –85 °C).
        """
        self.cancel = False
        print(f"Cooling to {target_temp} C")
        
        self.temp = 20.0
        while True:
            if self.cancel:
                print("Cooling canceled")
                break

            self.temp -= 5

            if self.temp <= target_temp:
                print(f"Temperature stabilized, Status: Stabilized")
                break

            time.sleep(0.1)

    @requires_cam_connected
    def warm_cam(self,safe_temp:float=-20):
        """
        Simulate warming the sensor back up to 'safe_temp'.
 
        Sets 'self.cancel = True' to abort any ongoing cooling loop, then
        increments the temperature in 20 °C steps until 'safe_temp' is reached.
 
        Args:
            safe_temp: Target warm-up temperature in °C (default –20 °C).
        """
        self.cancel = True

        print("Warming (cooler OFF)")
        self.temp = -80.0 

        while True:
            print(f"Warming T = {self.temp} C")

            if self.temp >= safe_temp:
                break
            self.temp += 20
            time.sleep(0.1)


    # ===== DISCONNECT =====

    def safe_close(self):
        """
        Safely disconnect the camera by stopping any cooling and closing the connection.
 
        Sets the cancel flag to interrupt active cooling loops, then calls
        'close_cam()'.  Does nothing if no camera is connected.
        """
        if not self.cam:
            return
        
        self.cancel=True
        
        self.close_cam()
        return

    def close_cam(self):
        """
        Close the camera connection and reset the camera handle to 'None'.
 
        Does nothing if the camera is already disconnected.
        """
        if self.cam:
            print("Camera disconnected")
            self.cam = None
    

    # ===== LIVE VIDEO =====

    @requires_cam_connected
    def start_live(self):
        """
        Capture a single live-preview frame, simulating the current exposure time.
 
        Generates a synthetic frame via 'generate_fake_frame()' and sleeps for
        the duration of the configured exposure to mimic real readout timing.
 
        Returns:
            List[np.ndarray]: A one-element list containing the generated frame.
        """
        print("Live mode started")
        
        frame = self.generate_fake_frame()
        exposure = self.get_exposure()
        time.sleep(exposure)

        return frame

    @requires_cam_connected
    def stop_live(self):
        """
        Stop the live-preview acquisition loop.
 
        No-op if no camera is connected.
        """
        if not self.cam:
            return

        print("Live mode stopped")
        return

    @requires_cam_connected
    def get_live_frame(self):
        """
        Return a single live frame without blocking for the exposure duration.
 
        Returns:
            List[np.ndarray] | None: Generated frame list, or 'None' if the
            camera handle is unexpectedly unset.
        """
        if self.cam is None:
            print(f"Could not obtain the frame for the preview. Cam: {self.cam}")
            return None
        
        frame = self.generate_fake_frame()
        return frame

    @requires_cam_connected
    def single_preview(self):
        """
        Return a single 2-D preview frame (not wrapped in a list).
 
        Returns:
            np.ndarray: The first (and only) frame from 'generate_fake_frame()'.
        """
        return self.generate_fake_frame()[0]


    # ==== VALIDATION ====

    def validate_EMCCD_gain(self,emccd_gain:float,advanced:bool):
        """
        Validate the requested EMCCD gain value.
 
        Clamps negative values to zero.  Raises if gain exceeds 300 and
        'advanced' mode is not enabled.
 
        Args:
            emccd_gain: Requested EM gain value.
            advanced:   Whether the advanced (high-gain) mode is active.
 
        Raises:
            ValueError: If 'emccd_gain > 300' and 'advanced' is 'False'.
        """
        if emccd_gain < 0:
            emccd_gain = 0
        if emccd_gain > 300 and not advanced:
            raise ValueError(f"Invalid EMCCD gain {emccd_gain}, to set above 300 use advanced option")
        return

    def validate_exposure(self,exposure:float):
        """
        Ensure the exposure time is non-negative.
 
        Args:
            exposure: Exposure time in seconds.
 
        Raises:
            ValueError: If 'exposure' is negative.
        """
        if exposure < 0:
            raise ValueError(f"Invalid exposure time {exposure}, can not be negative")
        return

    def validate_amp(self,channel:Optional[int],oamp:Optional[int],hsspeed:Optional[int],preamp:Optional[int]):
        """
        Validate amplifier mode parameters.
 
        Currently a no-op stub; extend to add range checking against
        'self.all_amp_modes' as needed.
 
        Args:
            channel: Output channel index.
            oamp:    Output amplifier index.
            hsspeed: Horizontal shift speed index.
            preamp:  Pre-amplifier gain index.
        """
        return

    def validate_read_mode(self, read_mode:str):
        """
        Confirm that 'read_mode' is one of the accepted mode strings.
 
        Args:
            read_mode: Mode string to validate.
 
        Raises:
            ValueError: If the mode is not in the set of valid modes.
        """
        valid_modes = {"fvb", "image", "single_track", "multi_track", "random_track"}
        
        if read_mode not in valid_modes:
            raise ValueError(f"Invalid read mode: {read_mode}. Valid modes are: {valid_modes}")

    def validate_single_track_mode(self, center:int, width:int):
        """
        Validate single-track mode parameters.
 
        Currently a no-op stub; extend to check that the track lies within the
        detector bounds as needed.
 
        Args:
            center: Row index of the track centre.
            width:  Track width in rows.
        """
        return

    def validate_multi_track_mode(self, number:int, height:int, offset:int):
        """
        Validate multi-track mode parameters.
 
        Currently a no-op stub; extend to enforce detector-bound constraints
        as needed.
 
        Args:
            number: Number of tracks.
            height: Height of each track in rows.
            offset: Pixel offset between track centres.
        """
        return

    def validate_shutter_settings(self, mode:str, ttl_mode:int, open_time:Optional[float], close_time:Optional[float]):
        """
        Validate shutter configuration parameters.
 
        Clamps 'open_time' and 'close_time' up to the camera's minimum values
        when they are specified but too small.
 
        Args:
            mode:       Shutter mode string ('auto', 'open', 'closed').
            ttl_mode:   TTL polarity – '0' or '1'.
            open_time:  Requested shutter open time in ms (or 'None' to skip check).
            close_time: Requested shutter close time in ms (or 'None' to skip check).
 
        Raises:
            ValueError: If 'mode' or 'ttl_mode' is invalid.
        """
        valid_modes = ["auto", "open", "closed"]
        if mode not in valid_modes:
            raise ValueError(f"Invalid shutter mode: {mode}. Valid modes are: {valid_modes}")

        if ttl_mode not in [0, 1]:
            raise ValueError("TTL mode must be 0 (low is open) or 1 (high is open)")

        min_open_time, min_close_time = self.get_min_shutter_times()

        if open_time is not None and open_time < min_open_time:
            open_time = min_open_time

        if close_time is not None and close_time < min_close_time:
            close_time = min_close_time

    def validate_acquisition_mode(self, mode:str):
        """
        Validate an acquisition mode string before applying it.
 
        Args:
            mode: Mode string to check.
 
        Returns:
            bool: 'True' if the mode is valid.
 
        Raises:
            ValueError: If 'mode' is not a recognised acquisition mode.
        """
        valid_modes = ["single", "accum", "kinetic", "fast_kinetic", "cont"]
        if mode not in valid_modes:
            raise ValueError(f"Invalid acquisition mode: {mode}. Valid modes are: {valid_modes}.")
            
        return True

    def validate_trigger_mode(self, mode:str):
        """
        Validate a trigger mode string before applying it.
 
        Args:
            mode: Mode string to check.
 
        Returns:
            bool: 'True' if the mode is valid.
 
        Raises:
            ValueError: If 'mode' is not a recognised trigger mode.
        """
        valid_modes = ["int","ext","ext_start","ext_exp","ext_fvb_em","software","ext_charge_shift"]
        if mode not in valid_modes:
            raise ValueError(f"Invalid trigger mode: {mode}. Valid modes are: {valid_modes}.")
        
        return True

    def validate_roi_settings(self, hstart:int, hend:Optional[int], vstart:int, vend:Optional[int], hbin:int, vbin:int):
        """
        Substitute 'None' ROI values with safe defaults and return the sanitised tuple.
 
        Args:
            hstart: Horizontal start pixel ('None' → 0).
            hend:   Horizontal end pixel ('None' → 1024).
            vstart: Vertical start pixel ('None' → 0).
            vend:   Vertical end pixel ('None' → 256).
            hbin:   Horizontal bin ('None' → 1).
            vbin:   Vertical bin ('None' → 1).
 
        Returns:
            Tuple[int, int, int, int, int, int]: Sanitised ROI parameters.
        """

        if hstart is None:
            hstart = 0
        if hend is None:
            hend = 1024
        if vstart is None:
            vstart = 0
        if vend is None:
            vend = 256
        if hbin is None:
            hbin = 1
        if vbin is None:
            vbin = 1
        return hstart,hend,vstart,vend,hbin,vbin

    def validate_bit_shift(self,bit_shift_pixels,bit_shift_vstart,bit_shift_vend):
        """
        Sanitise and validate bit-shift correction parameters against the active ROI.
 
        'None' values for 'bit_shift_vstart' / 'bit_shift_vend' are replaced
        with the ROI vertical extents.  Values outside the ROI are clamped.
 
        Args:
            bit_shift_pixels: Shift amount in pixels ('None' → 0).
            bit_shift_vstart: First row of the shift region (absolute detector coordinate).
            bit_shift_vend:   Last row of the shift region (absolute detector coordinate).
 
        Returns:
            Tuple: Validated '(bit_shift_pixels, bit_shift_vstart, bit_shift_vend)'.
 
        Raises:
            ValueError: If 'bit_shift_vstart > bit_shift_vend' after clamping.
        """
        if bit_shift_pixels is None:
            bit_shift_pixels = 0

        _,_,vstart,vend,_,_ = self.get_roi()
        if bit_shift_vstart is None or bit_shift_vstart<vstart:
            bit_shift_vstart = vstart
        if bit_shift_vend is None or bit_shift_vend>vend:
            bit_shift_vend = vend
        if bit_shift_vstart > bit_shift_vend:
            raise ValueError(f"Bit shift region should be between {vstart} - {vend}")
        return bit_shift_pixels,bit_shift_vstart,bit_shift_vend

    @requires_cam_connected
    def start_acquisition(self):
        """
        Simulate a single save acquisition and return a list of generated frames.
 
        Returns:
            List[np.ndarray]: One-element list containing a fake detector frame.
        """
        return self.generate_fake_frame()


    @requires_cam_connected
    def stop_acquisition(self):
        """
        Stop any ongoing acquisition (no-op for the simulated camera)."""
        print("Acquistion stopped")
        return

    # ===== FILE MANAGEMENT =====

    def save_csv_frame(self,frame,filename):
        """
        Save a raw 2-D detector frame as a CSV file alongside an NPZ output.
 
        The output filename is derived from 'filename' by stripping the '.npz'
        extension and appending '_frame.csv'.
 
        Args:
            frame:    2-D ndarray to save.
            filename: Base filename (typically the corresponding NPZ filename).
        """
        new_filename = filename
        csv_frame_path = self.save_path / f"{new_filename.replace('.npz','')}_frame.csv"
        np.savetxt(csv_frame_path,frame,delimiter=",",fmt="%d")
    
    def set_dlls_path(self,dlls_path):
        """
        Set the filesystem path to the Andor SDK2 DLL for pylablib.
 
        Args:
            dlls_path: Path to the directory containing the Andor SDK2 shared library.
        """
        pll.par["devices/dll/andor_sdk2"] = dlls_path

    # ==== DISPLAY DATA =====


    # ==== MATH =====

    def apply_binning(self, frame: np.ndarray, hbin: int, vbin: int) -> np.ndarray:
        """
        Simulate CCD binning by summing charge inside each 'vbin × hbin' block.
 
        Args:
            frame: 2-D ndarray representing the unbinned detector frame.
            hbin:  Horizontal binning factor.
            vbin:  Vertical binning factor.
 
        Returns:
            np.ndarray: Binned frame clipped to uint16 range.
        """

        if hbin == 1 and vbin == 1:
            return frame.astype(np.uint16)

        h, w = frame.shape
        out_h = h // vbin
        out_w = w // hbin

        trimmed = frame[:out_h * vbin, :out_w * hbin]
        binned = trimmed.reshape(out_h, vbin, out_w, hbin).sum(axis=(1, 3))

        return np.clip(binned, 0, 65535).astype(np.uint16)

    def generate_fake_frame(self):
        """
        Generate a synthetic detector frame that mimics a real Raman spectrum.
 
        Produces a noisy 2-D array with randomly placed Gaussian spectral lines
        (including main peaks and asymmetric tails), column-wise readout noise,
        and a small number of hot pixels.  The frame is sized and binned according
        to the currently active ROI settings.
 
        Returns:
            List[np.ndarray]: One-element list containing the generated uint16 frame.
        """
        hstart, hend, vstart, vend, hbin, vbin = self.get_roi()

        raw_w = hend - hstart
        raw_h = vend - vstart

        frame = np.random.normal(loc=120, scale=18, size=(raw_h, raw_w))

        rng = np.random.default_rng()
        n_lines = rng.integers(18, 32)

        if raw_w > 80:
            cols = np.sort(rng.choice(np.arange(40, raw_w - 40), size=n_lines, replace=False))
        else:
            cols = np.sort(rng.choice(np.arange(0, raw_w), size=min(n_lines, raw_w), replace=False))

        y = np.arange(raw_h)[:, None]

        for c in cols:
            y0 = rng.integers(max(0, raw_h // 3), max(1, 2 * raw_h // 3))

            amp_main = rng.uniform(1800, 5200)
            sigma_y_main = rng.uniform(4.0, 10.0)
            profile_main = amp_main * np.exp(-0.5 * ((y - y0) / sigma_y_main) ** 2)

            amp_tail = rng.uniform(300, 1200)
            sigma_y_tail = rng.uniform(25.0, 60.0)
            y_tail = y0 - rng.uniform(25, 55)
            profile_tail = amp_tail * np.exp(-0.5 * ((y - y_tail) / sigma_y_tail) ** 2)

            vertical_profile = profile_main + profile_tail

            line_half_width = int(rng.integers(0, 2))
            for dx in range(-line_half_width, line_half_width + 1):
                cc = c + dx
                if 0 <= cc < raw_w:
                    strength = 1.0 if dx == 0 else 0.55
                    frame[:, cc] += vertical_profile[:, 0] * strength

        col_noise = rng.normal(0, 8, size=raw_w)
        frame += col_noise[None, :]

        for _ in range(rng.integers(10, 25)):
            ry = rng.integers(0, raw_h)
            rx = rng.integers(0, raw_w)
            frame[ry, rx] += rng.uniform(800, 2500)

        frame = np.clip(frame, 0, 65535)

        frame = self.apply_binning(frame, hbin=hbin, vbin=vbin)

        return [frame]


class TAmpModeFull:
    
    def __init__(self,channel,bitdepth,oamp,oamp_kind,hsspeed,hsspeed_MHz,preamp,preamp_gain):
        """
        Represent a complete amplifier mode configuration for an Andor CCD camera.
 
        Args:
            channel:     Output channel index.
            bitdepth:    ADC bit depth for this channel.
            oamp:        Output amplifier index.
            oamp_kind:   Human-readable amplifier type string (e.g. 'Standard').
            hsspeed:     Horizontal shift speed value.
            hsspeed_MHz: Horizontal shift speed in MHz.
            preamp:      Pre-amplifier gain index.
            preamp_gain: Pre-amplifier gain multiplier.
        """
        self.channel = channel
        self.channel_bitdepth = bitdepth
        self.oamp = oamp
        self.oamp_kind = oamp_kind
        self.hsspeed = hsspeed
        self.hsspeed_MHz = hsspeed_MHz
        self.preamp = preamp
        self.preamp_gain = preamp_gain

    def set_mode(self,channel,oamp,hsspeed,preamp):
        """
        Update the mutable amplifier parameters in-place.
 
        Args:
            channel: New output channel index.
            oamp:    New output amplifier index.
            hsspeed: New horizontal shift speed value.
            preamp:  New pre-amplifier gain index.
        """
        self.channel = channel
        self.oamp = oamp
        self.hsspeed = hsspeed
        self.preamp = preamp

    def __repr__(self):
        """
        Return a detailed string representation of the amplifier mode.
 
        Returns:
            str: Constructor-style string with all parameter values.
        """
        return f"TAmpModeFull(channel={self.channel}, bitdepth={self.channel_bitdepth}, oamp={self.oamp}, oamp_kind={self.oamp_kind}, hsspeed={self.hsspeed}, hsspeed_MHz={self.hsspeed_MHz}, preamp={self.preamp}, preamp_gain={self.preamp_gain})"