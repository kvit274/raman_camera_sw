import os
import sys
import time
import numpy as np
from pyAndorSDK2 import atmcd
from pyAndorSDK2 import atmcd_codes
from pathlib import Path
from pprint import pformat
from typing import Optional, List, Tuple
from types import SimpleNamespace
from datetime import datetime
from functools import wraps


# ══════════════════════════════════════════════════════════════════════════════
#  SDK2 RETURN CODES
# ══════════════════════════════════════════════════════════════════════════════

DRV_SUCCESS                    = 20002
DRV_ACQUIRING                  = 20072
DRV_IDLE                       = 20073
DRV_TEMPERATURE_OFF            = 20034
DRV_TEMPERATURE_NOT_REACHED    = 20035
DRV_TEMPERATURE_DRIFT          = 20036
DRV_TEMPERATURE_NOT_STABILIZED = 20037
DRV_TEMPERATURE_STABILIZED     = 20038


# ══════════════════════════════════════════════════════════════════════════════
#  ENUM ↔ STRING LOOK-UPS
# ══════════════════════════════════════════════════════════════════════════════

# Read mode
_READ_MODE   = {"fvb": 0, "multi_track": 1, "random_track": 2, "single_track": 3, "image": 4}
_READ_MODE_R = {v: k for k, v in _READ_MODE.items()}

# Acquisition mode
_ACQ_MODE    = {"single": 1, "accum": 2, "kinetic": 3, "fast_kinetic": 4, "cont": 5}
_ACQ_MODE_R  = {v: k for k, v in _ACQ_MODE.items()}

# Trigger mode
_TRIG_MODE   = {
    "int": 0, "ext": 1, "ext_start": 6, "ext_exp": 7,
    "ext_fvb_em": 9, "software": 10, "ext_charge_shift": 12,
}

# Shutter mode
_SHUTTER   = {"auto": 0, "open": 1, "closed": 2}
_SHUTTER_R = {v: k for k, v in _SHUTTER.items()}

# Fan mode
_FAN   = {"full": 0, "low": 1, "off": 2}
_FAN_R = {v: k for k, v in _FAN.items()}

# Temperature status  (the SDK2 error code IS the status for GetTemperatureF)
_TEMP_STATUS = {
    DRV_TEMPERATURE_OFF:            "off",
    DRV_TEMPERATURE_NOT_REACHED:    "not_reached",
    DRV_TEMPERATURE_DRIFT:          "drift",
    DRV_TEMPERATURE_NOT_STABILIZED: "not_stabilized",
    DRV_TEMPERATURE_STABILIZED:     "stabilized",
}


# ══════════════════════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _check(error_code: int, context: str = "") -> None:
    """Raise RuntimeError if *error_code* is not DRV_SUCCESS."""
    if error_code != DRV_SUCCESS:
        msg = f"Andor SDK2 error {error_code}"
        if context:
            msg += f" [{context}]"
        raise RuntimeError(msg)


# ══════════════════════════════════════════════════════════════════════════════
#  CAMERA MODEL
# ══════════════════════════════════════════════════════════════════════════════

class RamanCameraModel2:
    """
    Hardware abstraction layer for an Andor SDK2 camera used in Raman
    spectroscopy.

    All SDK calls go directly through the pyAndorSDK2 *atmcd* module; no
    pylablib dependency is required.

    Because the Andor SDK2 exposes setters for most parameters but very few
    getters, every applied setting is mirrored in an internal state dictionary
    (self._state) so callers can query them at any time without round-tripping
    the hardware.

    All public methods that require an active camera connection are guarded by
    the @requires_cam_connected decorator, which raises RuntimeError if the
    camera has not been initialised.
    """

    # ── construction ──────────────────────────────────────────────────────────

    def __init__(self):
        """
        Initialise the model with no camera connected and default output
        directories.

        Creates ./data, ./data/csv, and ./data/images if they do not exist.
        Also initialises bit-shift correction parameters to their off state.
        """
        self.cam = None           # set to True once the SDK is initialised
        self.sdk = None           # atmcd instance, created in connect_cam()
        self.cancel_cooling = False
        self.acquisition_settings = None

        # default save paths
        self.save_path_csv   = Path("./data/csv");    self.save_path_csv.mkdir(parents=True, exist_ok=True)
        self.save_path_image = Path("./data/images"); self.save_path_image.mkdir(parents=True, exist_ok=True)
        self.save_path       = Path("./data");        self.save_path.mkdir(parents=True, exist_ok=True)

        # bit-shift correction
        self.bit_shift_pixels = 0
        self.bit_shift_vstart = None
        self.bit_shift_vend   = None

        # ── SDK2 state mirror ─────────────────────────────────────────────────
        # The SDK2 has no general "get_settings" call, so every value we apply
        # is stored here and returned by the corresponding getter.
        self._detector_size       = (0, 0)           # (width, height) in pixels
        self._read_mode           = "fvb"
        self._roi                 = (0, 0, 0, 0, 1, 1)  # pylablib convention
        self._single_track        = (0, 1)           # (center_0based, width)
        self._multi_track         = (1, 1, 0)        # (number, height, offset)
        self._random_tracks       = []               # list of (start, stop) 0-based
        self._acq_mode            = "single"
        self._accum_params        = (1, 0.0)         # (num_acc, cycle_time_s)
        self._kinetic_params      = (1, 0.0, 1, 0.0, 0)  # (num_cycle, cycle_time, num_acc, cycle_time_acc, num_prescan)
        self._fast_kinetic_params = (1, 0.0)         # (num_frames, cycle_time_s)
        self._cont_cycle_time     = 0.0
        self._trigger_mode        = "int"
        self._exposure            = 0.1              # seconds
        self._channel             = 0
        self._oamp                = 0
        self._hsspeed             = 0
        self._preamp              = 0
        self._vsspeed             = 0
        self._emccd_gain          = 0
        self._temperature_setpoint = -85.0
        self._shutter_mode        = "auto"
        self._shutter_ttl         = 0
        self._shutter_open_ms     = 0.0
        self._shutter_close_ms    = 0.0
        self._fan_mode            = "full"


    # ══════════════════════════════════════════════════════════════════════════
    #  DECORATOR
    # ══════════════════════════════════════════════════════════════════════════

    def requires_cam_connected(func):
        """
        Decorator that guards a method against being called when no camera is
        open.

        Raises:
            RuntimeError: If self.cam is None (camera not connected).
        """
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            if not self.cam:
                raise RuntimeError("Camera not connected")
            return func(self, *args, **kwargs)
        return wrapper


    # ══════════════════════════════════════════════════════════════════════════
    #  INTERNAL HELPERS
    # ══════════════════════════════════════════════════════════════════════════

    def _pll_to_sdk(self, hstart: int, hend: int,
                    vstart: int, vend: int) -> Tuple[int, int, int, int]:
        """
        Convert pylablib 0-based half-open ROI to SDK2 1-based inclusive.

        pylablib: hstart=0, hend=1024  →  pixels 0..1023
        SDK2:     hstart=1, hend=1024  →  pixels 1..1024  (same physical pixels)
        """
        return hstart + 1, hend, vstart + 1, vend

    def _image_pixels(self) -> int:
        """Return the number of pixels in one acquired frame, derived from
        the current data dimensions (width x height)."""
        w, h = self._get_data_dimensions()
        return w * h

    def _get_data_dimensions(self) -> Tuple[int, int]:
        """
        Compute output frame dimensions (width, height) for the current read
        mode, ROI, and binning.
        """
        w, _ = self._detector_size
        hstart, hend, vstart, vend, hbin, vbin = self._roi
        mode = self._read_mode

        col_width = (hend - hstart) // hbin if (hend > hstart and hbin > 0) else w

        if mode in ("fvb", "single_track"):
            return (col_width, 1)
        elif mode == "multi_track":
            number = self._multi_track[0]
            return (col_width, number)
        elif mode == "random_track":
            ntracks = max(len(self._random_tracks), 1)
            return (col_width, ntracks)
        else:  # image
            _, h = self._detector_size
            row_height = (vend - vstart) // vbin if (vend > vstart and vbin > 0) else h
            return (col_width, row_height)

    def _acquire_single_frame(self, timeout: float) -> np.ndarray:
        """
        Start a single-frame acquisition, poll until complete, and return a
        2-D ndarray (height x width, numpy convention).

        Args:
            timeout: Maximum wait time in seconds.
        """
        _check(self.sdk.StartAcquisition(), "StartAcquisition")
        print("Acquisition started, waiting...")

        deadline = time.time() + max(timeout, 5.0)
        while True:
            error, status = self.sdk.GetStatus()
            if status == DRV_IDLE:
                break
            if time.time() > deadline:
                self.sdk.AbortAcquisition()
                raise RuntimeError(f"Acquisition timed out after {timeout:.1f}s")
            time.sleep(0.05)

        print("Acquisition complete, retrieving data...")
        n = self._image_pixels()
        # GetImages16 returns (ret, arr, validfirst, validlast) — 4 values.
        # GetAcquiredData is not a properly declared pyAndorSDK2 wrapper; calling
        # it passes `n` as a raw C pointer, causing a segfault in the DLL.
        error, arr, _, _ = self.sdk.GetImages16(1, 1, n)
        _check(error, "GetImages16")

        data = np.array(arr, dtype=np.int32)
        w, h = self._get_data_dimensions()
        return data.reshape(h, w)

    def _acquire_n_frames(self, nframes: int, timeout: float) -> List[np.ndarray]:
        """
        Start a multi-frame (kinetic / fast-kinetic) acquisition, poll until
        complete, and return a list of 2-D ndarrays.

        Args:
            nframes: Number of frames expected.
            timeout: Total wait timeout in seconds.
        """
        _check(self.sdk.StartAcquisition(), "StartAcquisition")
        print(f"Acquisition started, waiting for {nframes} frame(s)...")

        # Scale deadline by nframes — calc_frame_timeout() returns the per-frame
        # kinetic cycle time, so the full series takes nframes × that long.
        total_timeout = max(timeout * nframes, 10.0)
        deadline = time.time() + total_timeout
        while True:
            error, status = self.sdk.GetStatus()
            if status == DRV_IDLE:
                break
            if time.time() > deadline:
                self.sdk.AbortAcquisition()
                raise RuntimeError(
                    f"Acquisition timed out after {total_timeout:.1f}s "
                    f"({nframes} frame(s) × {timeout:.1f}s per frame)"
                )
            time.sleep(0.05)

        print("Acquisition complete, retrieving data...")
        n     = self._image_pixels()
        total = n * nframes
        # GetImages16 returns (ret, arr, validfirst, validlast) — 4 values.
        error, arr, _, _ = self.sdk.GetImages16(1, nframes, total)
        _check(error, "GetImages16")

        w, h = self._get_data_dimensions()
        data = np.array(arr, dtype=np.int32)
        return [data[i * n:(i + 1) * n].reshape(h, w) for i in range(nframes)]

    def _stop_acq_safe(self) -> None:
        """
        Abort any in-progress acquisition without raising on error.

        FreeInternalMemory is intentionally omitted — it is not a declared
        pyAndorSDK2 wrapper and calling it through __getattr__ with no argtypes
        causes the same segfault as GetAcquiredData did.
        """
        try:
            self.sdk.AbortAcquisition()
        except Exception:
            pass


    # ══════════════════════════════════════════════════════════════════════════
    #  CONNECTION
    # ══════════════════════════════════════════════════════════════════════════

    def connect_cam(self) -> None:
        """
        Initialise the Andor SDK2 and open the first available camera.

        Does nothing if a camera is already connected.  On success sets
        self.cam = True and caches the full detector size internally.

        Raises:
            ConnectionError: If no cameras are found or initialisation fails.
        """
        if self.cam:
            print("Camera already connected")
            return

        self.sdk = atmcd()

        error, num_cameras = self.sdk.GetAvailableCameras()
        _check(error, "GetAvailableCameras")
        print(f"Found {num_cameras} camera(s)")

        if num_cameras == 0:
            raise ConnectionError("No Andor cameras found")

        # Select the first camera
        error, handle = self.sdk.GetCameraHandle(0)
        _check(error, "GetCameraHandle")
        _check(self.sdk.SetCurrentCamera(handle), "SetCurrentCamera")

        # Initialise the SDK (empty string → use INI in the driver directory)
        _check(self.sdk.Initialize(""), "Initialize")
        self.cam = True     # mark as connected

        # Cache full detector size and default to full-frame ROI
        error, xpix, ypix = self.sdk.GetDetector()
        _check(error, "GetDetector")
        self._detector_size = (xpix, ypix)
        self._roi = (0, xpix, 0, ypix, 1, 1)

        info = self.get_device_info()
        cam_name = f"{info.controller_model} | {info.head_model} | SN {info.serial_number}"
        print(f"Connected to: {cam_name}")


    # ══════════════════════════════════════════════════════════════════════════
    #  DEVICE INFO & DIAGNOSTICS
    # ══════════════════════════════════════════════════════════════════════════

    @requires_cam_connected
    def get_device_info(self) -> SimpleNamespace:
        """
        Return camera identity as a SimpleNamespace with fields:
        controller_model, head_model, serial_number.
        """
        error, serial     = self.sdk.GetCameraSerialNumber()
        _check(error, "GetCameraSerialNumber")
        error, head_model = self.sdk.GetHeadModel()
        _check(error, "GetHeadModel")
        error, ctrl_model = self.sdk.GetControllerCardModel()
        _check(error, "GetControllerCardModel")
        return SimpleNamespace(
            serial_number    = serial,
            head_model       = head_model,
            controller_model = ctrl_model,
        )

    @requires_cam_connected
    def get_cam_params(self, save_path: Path = Path("./cam_params.txt")) -> None:
        """
        Collect all available camera parameters and write them to a
        human-readable text file at *save_path*.

        Captures device info, status, capabilities, pixel size, temperature
        settings, amplifier modes, shift speeds, shutter, trigger, acquisition,
        ROI, and more.

        Args:
            save_path: Destination file path (default ./cam_params.txt).
        """
        info = {}
        info["device_info"]               = vars(self.get_device_info())
        info["status"]                    = self.get_status()
        info["capabilities"]              = self._get_capabilities_dict()
        info["pixel_size_um"]             = self.get_pixel_size()
        info["temperature_setpoint"]      = self._temperature_setpoint
        info["temperature_range"]         = self.get_temperature_range()
        info["current_amp_mode"]          = {
            "channel": self._channel, "oamp": self._oamp,
            "hsspeed": self._hsspeed, "preamp": self._preamp,
        }
        info["available_amp_modes"]       = self.get_all_amp_modes()
        info["preamp_index"]              = self._preamp
        info["preamp_gain"]               = self._get_preamp_gain(self._preamp)
        info["max_vertical_shift_speed"]  = self.get_max_vsspeed()
        info["all_vertical_shift_speeds"] = self.get_all_vsspeeds()
        info["output_amp_index"]          = self._oamp
        info["horizontal_shift_speed"]    = self._hsspeed
        info["hsspeed_frequency_MHz"]     = self._get_hsspeed_freq()
        info["shutter_mode"]              = self._shutter_mode
        info["trigger_mode"]              = self._trigger_mode
        info["acquisition_mode"]          = self._acq_mode
        info["accumulation_params"]       = self._accum_params
        info["exposure_time_s"]           = self.get_exposure()
        info["readout_mode"]              = self._read_mode
        info["detector_size"]             = self._detector_size
        info["roi"]                       = self._roi
        info["roi_limits"]                = self.get_roi_limits()
        info["buffer_size_bytes"]         = self._get_image_size_bytes()

        readable_text  = "=== Andor Newton Camera Parameters ===\n"
        readable_text += pformat(info, indent=2, width=120)

        with open(save_path, "w") as f:
            f.write(readable_text)

    # ── helpers used only by get_cam_params ───────────────────────────────────

    def _get_capabilities_dict(self) -> dict:
        error, caps = self.sdk.GetCapabilities()
        _check(error, "GetCapabilities")
        return {
            "AcqModes":          caps.ulAcqModes,
            "ReadModes":         caps.ulReadModes,
            "TriggerModes":      caps.ulTriggerModes,
            "CameraType":        caps.ulCameraType,
            "PixelMode":         caps.ulPixelMode,
            "SetFunctions":      caps.ulSetFunctions,
            "GetFunctions":      caps.ulGetFunctions,
            "Features":          caps.ulFeatures,
            "PCISpeed":          caps.ulPCICard,
            "EMGainCapability":  caps.ulEMGainCapability,
        }

    def _get_preamp_gain(self, index: int) -> float:
        error, gain = self.sdk.GetPreAmpGain(index)
        _check(error, "GetPreAmpGain")
        return gain

    def _get_hsspeed_freq(self) -> float:
        error, speed = self.sdk.GetHSSpeed(self._channel, self._oamp, self._hsspeed)
        _check(error, "GetHSSpeed")
        return speed

    def _get_image_size_bytes(self) -> int:
        w, h = self._get_data_dimensions()
        return w * h * 4  # 4 bytes per int32 pixel


    # ══════════════════════════════════════════════════════════════════════════
    #  BASIC STATUS
    # ══════════════════════════════════════════════════════════════════════════

    @requires_cam_connected
    def get_status(self) -> str:
        """
        Return the camera's current status as a human-readable string.

        Returns:
            'idle', 'acquiring', or the raw integer code as a string.
        """
        error, status = self.sdk.GetStatus()
        _check(error, "GetStatus")
        return {DRV_IDLE: "idle", DRV_ACQUIRING: "acquiring"}.get(status, str(status))

    @requires_cam_connected
    def get_pixel_size(self) -> Tuple[float, float]:
        """
        Return the physical pixel size.

        Returns:
            Tuple (x_um, y_um) in micrometres.
        """
        error, xsize, ysize = self.sdk.GetPixelSize()
        _check(error, "GetPixelSize")
        return (xsize, ysize)

    @requires_cam_connected
    def detect_cam_size(self) -> Tuple[int, int]:
        """
        Return the full detector size in pixels, unaffected by the current ROI.

        Returns:
            Tuple (width, height).
        """
        return self._detector_size

    @requires_cam_connected
    def get_data_dim(self) -> Tuple[int, int]:
        """
        Return the effective data dimensions (width, height) after applying
        the current ROI, read mode, and binning.

        Returns:
            Tuple (width, height) in pixels.
        """
        return self._get_data_dimensions()


    # ══════════════════════════════════════════════════════════════════════════
    #  SETTINGS SNAPSHOT
    # ══════════════════════════════════════════════════════════════════════════

    @requires_cam_connected
    def get_settings(self, include: int = -10) -> dict:
        """
        Return a dict of all currently tracked camera settings.

        The *include* parameter is accepted for API compatibility with callers
        that used the pylablib equivalent; it is not used.

        Returns:
            Dict of setting name → value pairs.
        """
        return {
            "read_mode":             self._read_mode,
            "acquisition_mode":      self._acq_mode,
            "trigger_mode":          self._trigger_mode,
            "exposure":              self._exposure,
            "roi":                   self._roi,
            "read_parameters/image": self._roi,
            "shutter":               (self._shutter_mode, self._shutter_ttl,
                                      self._shutter_open_ms, self._shutter_close_ms),
            "single_track":          self._single_track,
            "multi_track":           self._multi_track,
            "random_tracks":         self._random_tracks,
            "accum_params":          self._accum_params,
            "kinetic_params":        self._kinetic_params,
            "fast_kinetic_params":   self._fast_kinetic_params,
            "cont_cycle_time":       self._cont_cycle_time,
            "channel":               self._channel,
            "oamp":                  self._oamp,
            "hsspeed":               self._hsspeed,
            "preamp":                self._preamp,
            "vsspeed":               self._vsspeed,
            "emccd_gain":            self._emccd_gain,
            "temperature_setpoint":  self._temperature_setpoint,
            "shutter_mode":          self._shutter_mode,
            "shutter_ttl":           self._shutter_ttl,
            "shutter_open_ms":       self._shutter_open_ms,
            "shutter_close_ms":      self._shutter_close_ms,
            "fan_mode":              self._fan_mode,
        }

    @requires_cam_connected
    def save_acquisition_settings(self) -> None:
        """
        Snapshot the current camera settings into self.acquisition_settings so
        they can be restored later via restore_acquisition_settings().
        """
        self.acquisition_settings = self.get_settings()

    @requires_cam_connected
    def restore_acquisition_settings(self) -> Optional[dict]:
        """
        Return the last settings snapshot saved by save_acquisition_settings().

        Returns:
            Previously saved settings dict, or None if never saved.
        """
        return self.acquisition_settings

    @requires_cam_connected
    def set_default_settings(self) -> None:
        """
        Apply a minimal safe set of default camera parameters (single
        acquisition mode).
        """
        self.setup_single_mode()
        print("Camera initialized")


    # ══════════════════════════════════════════════════════════════════════════
    #  FRAME TIMING
    # ══════════════════════════════════════════════════════════════════════════

    @requires_cam_connected
    def calc_frame_timeout(self, extra: float = 5.0) -> float:
        """
        Calculate a safe frame capture timeout based on the current frame
        timings.

        Args:
            extra: Additional safety margin in seconds added to the frame period.

        Returns:
            Float timeout in seconds (minimum 5.0 s).
        """
        exp, frame_period = self._get_frame_timings()
        return max(frame_period + extra, 5.0)

    def _get_frame_timings(self) -> Tuple[float, float]:
        """
        Return (exposure_s, frame_period_s) from GetAcquisitionTimings.
        frame_period is the kinetic cycle time, which is the upper bound for
        the time between successive frames.
        """
        error, exposure, accumulate, kinetic = self.sdk.GetAcquisitionTimings()
        _check(error, "GetAcquisitionTimings")
        return exposure, kinetic

    @requires_cam_connected
    def get_exposure(self) -> float:
        """
        Return the current exposure time set on the camera.

        Returns:
            Exposure time in seconds (float).
        """
        error, exposure, _, _ = self.sdk.GetAcquisitionTimings()
        _check(error, "GetAcquisitionTimings")
        return exposure


    # ══════════════════════════════════════════════════════════════════════════
    #  ROI MANAGEMENT
    # ══════════════════════════════════════════════════════════════════════════

    @requires_cam_connected
    def get_roi_limits(self, hbin: int = 1, vbin: int = 1) -> List[Tuple]:
        """
        Return the hardware ROI limits for the given binning factors.

        Returns:
            List of two 5-tuples [h_limits, v_limits] where each tuple is
            (min, max, position_step, size_step, max_bin).
            Coordinates are 0-based (pylablib convention).
        """
        w, h = self._detector_size
        # Andor Newton: 1-pixel steps on both axes; max binning = full axis.
        h_limits = (0, w, 1, 1, w)
        v_limits = (0, h, 1, 1, h)
        return [h_limits, v_limits]

    @requires_cam_connected
    def get_roi(self) -> Tuple[int, int, int, int, int, int]:
        """
        Return the current ROI as a 6-tuple.

        Returns:
            Tuple (hstart, hend, vstart, vend, hbin, vbin).
            Coordinates are 0-based, hend/vend are exclusive (pylablib convention).
        """
        return self._roi

    @requires_cam_connected
    def set_roi(self, hstart: int, hend: Optional[int], vstart: int,
                vend: Optional[int], hbin: int, vbin: int) -> None:
        """
        Validate and apply a new ROI to the camera via SetImage.

        Args:
            hstart: Horizontal start pixel (0-based, inclusive).
            hend:   Horizontal end pixel (0-based, exclusive).  None = detector width.
            vstart: Vertical start pixel (0-based, inclusive).
            vend:   Vertical end pixel (0-based, exclusive).  None = detector height.
            hbin:   Horizontal binning factor.
            vbin:   Vertical binning factor.
        """
        hstart, hend, vstart, vend, hbin, vbin = self.validate_roi(
            hstart, hend, vstart, vend, hbin, vbin
        )
        sdk_hs, sdk_he, sdk_vs, sdk_ve = self._pll_to_sdk(hstart, hend, vstart, vend)
        _check(self.sdk.SetImage(hbin, vbin, sdk_hs, sdk_he, sdk_vs, sdk_ve), "SetImage")
        self._roi = (hstart, hend, vstart, vend, hbin, vbin)


    # ══════════════════════════════════════════════════════════════════════════
    #  READ MODE
    # ══════════════════════════════════════════════════════════════════════════

    @requires_cam_connected
    def set_read_mode(self, read_mode: Optional[str] = "fvb") -> None:
        """
        Set the detector readout mode.

        Args:
            read_mode: One of 'fvb', 'image', 'single_track', 'multi_track',
                       'random_track'.
        """
        self.validate_read_mode(read_mode)
        _check(self.sdk.SetReadMode(_READ_MODE[read_mode]), "SetReadMode")
        self._read_mode = read_mode
        print(f"Read mode set to: {read_mode}")

    @requires_cam_connected
    def get_read_mode(self) -> str:
        """
        Return the current detector readout mode string.

        Returns:
            String such as 'fvb', 'image', 'single_track', etc.
        """
        return self._read_mode

    @requires_cam_connected
    def setup_single_track_mode(self, center: int = 0, width: int = 1,
                                 mode: Optional[str] = "single") -> None:
        """
        Configure single-track readout to bin a horizontal strip of rows.

        Args:
            center: Centre row of the track (0-based).
            width:  Number of rows to include in the track.
            mode:   Informational label, not sent to hardware.
        """
        self.validate_single_track_mode(center, width)
        _check(self.sdk.SetReadMode(_READ_MODE["single_track"]), "SetReadMode")
        # SDK2 SetSingleTrack uses 1-based centre row
        _check(self.sdk.SetSingleTrack(center + 1, width), "SetSingleTrack")
        self._read_mode    = "single_track"
        self._single_track = (center, width)

    @requires_cam_connected
    def get_single_track_mode_params(self) -> Tuple[int, int]:
        """
        Return the current single-track mode parameters.

        Returns:
            Tuple (center, width).
        """
        return self._single_track

    @requires_cam_connected
    def setup_multi_track_mode(self, number: int = 1, height: int = 1,
                                offset: int = 0,
                                mode: Optional[str] = "multi_track") -> None:
        """
        Configure multi-track readout with evenly spaced horizontal strips.

        Args:
            number: Number of tracks.
            height: Height of each track in rows.
            offset: Gap between adjacent tracks in rows.
            mode:   Informational label, not sent to hardware.
        """
        self.validate_multi_track_mode(number, height, offset)
        _check(self.sdk.SetReadMode(_READ_MODE["multi_track"]), "SetReadMode")
        # SetMultiTrack also returns (bottom, gap) — we discard those
        error, _, _ = self.sdk.SetMultiTrack(number, height, offset)
        _check(error, "SetMultiTrack")
        self._read_mode   = "multi_track"
        self._multi_track = (number, height, offset)

    @requires_cam_connected
    def get_multi_track_mode_params(self) -> Tuple[int, int, int]:
        """
        Return the current multi-track mode parameters.

        Returns:
            Tuple (number, height, offset).
        """
        return self._multi_track

    @requires_cam_connected
    def setup_random_track_mode(self, tracks=None,
                                 mode: Optional[str] = "random_track") -> None:
        """
        Configure random-track readout with arbitrary row spans.

        Args:
            tracks: List of (start_row, stop_row) tuples (0-based, inclusive).
            mode:   Informational label, not sent to hardware.
        """
        if tracks is None:
            tracks = []
        _check(self.sdk.SetReadMode(_READ_MODE["random_track"]), "SetReadMode")
        # SDK2 expects 1-based (bottom, top) pairs in a flat array
        flat = []
        for (s, e) in tracks:
            flat.extend([s + 1, e])
        error, _, _ = self.sdk.SetRandomTracks(len(tracks), flat)
        _check(error, "SetRandomTracks")
        self._read_mode     = "random_track"
        self._random_tracks = list(tracks)

    @requires_cam_connected
    def get_random_track_mode_params(self) -> list:
        """
        Return the current random-track mode parameters.

        Returns:
            List of (start, stop) tuples (0-based).
        """
        return self._random_tracks

    @requires_cam_connected
    def setup_image_mode(self, hstart: int = 0, hend: Optional[int] = None,
                          vstart: int = 0, vend: Optional[int] = None,
                          hbin: int = 1, vbin: int = 1,
                          mode: Optional[str] = "image") -> None:
        """
        Configure the camera for full-image readout with optional ROI and
        binning.

        Args:
            hstart: Horizontal start pixel (0-based, inclusive).
            hend:   Horizontal end pixel (0-based, exclusive).  None = detector width.
            vstart: Vertical start pixel (0-based, inclusive).
            vend:   Vertical end pixel (0-based, exclusive).  None = detector height.
            hbin:   Horizontal binning factor.
            vbin:   Vertical binning factor.
            mode:   Informational label.
        """
        hstart, hend, vstart, vend, hbin, vbin = self.validate_roi(
            hstart, hend, vstart, vend, hbin, vbin
        )
        _check(self.sdk.SetReadMode(_READ_MODE["image"]), "SetReadMode")
        sdk_hs, sdk_he, sdk_vs, sdk_ve = self._pll_to_sdk(hstart, hend, vstart, vend)
        _check(self.sdk.SetImage(hbin, vbin, sdk_hs, sdk_he, sdk_vs, sdk_ve), "SetImage")
        self._read_mode = "image"
        self._roi       = (hstart, hend, vstart, vend, hbin, vbin)
        print(f"Setting up image mode... ROI: {self._roi}")

    def setup_bit_shifting(self, bit_shift_pixels, bit_shift_vstart,
                            bit_shift_vend) -> None:
        """
        Validate and store bit-shift correction parameters used during frame
        processing.

        Args:
            bit_shift_pixels: Number of pixels to shift (0 = disabled).
            bit_shift_vstart: Absolute detector row where the shift region starts.
            bit_shift_vend:   Absolute detector row where the shift region ends.
        """
        bit_shift_pixels, bit_shift_vstart, bit_shift_vend = self.validate_bit_shift(
            bit_shift_pixels, bit_shift_vstart, bit_shift_vend
        )
        self.bit_shift_pixels = bit_shift_pixels
        self.bit_shift_vstart = bit_shift_vstart
        self.bit_shift_vend   = bit_shift_vend

    def get_bit_shifting(self) -> Tuple:
        """
        Return the currently stored bit-shift correction parameters.

        Returns:
            Tuple (bit_shift_pixels, bit_shift_vstart, bit_shift_vend).
        """
        return self.bit_shift_pixels, self.bit_shift_vstart, self.bit_shift_vend

    @requires_cam_connected
    def get_image_mode_params(self) -> Tuple:
        """
        Return the current image-mode ROI and binning parameters.

        Returns:
            Tuple (hstart, hend, vstart, vend, hbin, vbin).
        """
        return self._roi


    # ══════════════════════════════════════════════════════════════════════════
    #  SHUTTER SETUP
    # ══════════════════════════════════════════════════════════════════════════

    @requires_cam_connected
    def get_shutter_parameters(self) -> Tuple:
        """
        Return the current shutter configuration.

        Returns:
            Tuple (mode, ttl_mode, open_time_ms, close_time_ms).
        """
        return (self._shutter_mode, self._shutter_ttl,
                self._shutter_open_ms, self._shutter_close_ms)

    @requires_cam_connected
    def setup_shutter(self, mode: str, ttl_mode: int = 0,
                      open_time: Optional[float] = None,
                      close_time: Optional[float] = None) -> None:
        """
        Configure the mechanical shutter.

        Args:
            mode:       'auto', 'open', or 'closed'.
            ttl_mode:   0 = low TTL opens the shutter; 1 = high TTL opens it.
            open_time:  Shutter opening time in ms (None → use stored value).
            close_time: Shutter closing time in ms (None → use stored value).

        Raises:
            ValueError: If mode is invalid, ttl_mode is not 0 or 1, or timing
                        values are below the hardware minimum.
        """
        self.validate_shutter_settings(mode, ttl_mode, open_time, close_time)
        open_ms  = int(open_time  if open_time  is not None else self._shutter_open_ms)
        close_ms = int(close_time if close_time is not None else self._shutter_close_ms)
        # SDK2: SetShutter(typ, mode, closingtime, openingtime)
        #   typ:  0 = low TTL opens, 1 = high TTL opens
        #   mode: 0 = auto, 1 = open, 2 = close
        _check(self.sdk.SetShutter(ttl_mode, _SHUTTER[mode], close_ms, open_ms), "SetShutter")
        self._shutter_mode     = mode
        self._shutter_ttl      = ttl_mode
        self._shutter_open_ms  = float(open_ms)
        self._shutter_close_ms = float(close_ms)

    @requires_cam_connected
    def get_min_shutter_times(self) -> Tuple[float, float]:
        """
        Return the hardware minimum opening and closing times for the shutter.

        Returns:
            Tuple (min_open_ms, min_close_ms).
            Falls back to (0.0, 0.0) if the SDK does not expose this query.
        """
        try:
            error, min_close, min_open = self.sdk.GetShutterMinTimes()
            if error == DRV_SUCCESS:
                return (float(min_open), float(min_close))
        except AttributeError:
            pass
        return (0.0, 0.0)

    @requires_cam_connected
    def get_shutter(self) -> str:
        """
        Return the current shutter state string.

        Returns:
            One of 'auto', 'open', 'closed'.
        """
        return self._shutter_mode


    # ══════════════════════════════════════════════════════════════════════════
    #  ACQUISITION MODE
    # ══════════════════════════════════════════════════════════════════════════

    @requires_cam_connected
    def setup_single_mode(self) -> None:
        """Set the camera to single-frame acquisition mode."""
        _check(self.sdk.SetAcquisitionMode(_ACQ_MODE["single"]), "SetAcquisitionMode")
        self._acq_mode = "single"
        print(f"Acquisition mode set to single. Tracked: {self._acq_mode}")

    @requires_cam_connected
    def setup_accum_mode(self, num_acc: int, cycle_time_acc: Optional[float] = 0,
                          mode: Optional[str] = "accum",
                          result_mode: str = "sum") -> None:
        """
        Configure accumulation acquisition mode.

        Args:
            num_acc:        Number of sub-exposures to accumulate.
            cycle_time_acc: Minimum cycle time between accumulations in seconds.
            mode:           Informational label.
            result_mode:    Handled by AcquisitionService, not the camera layer.
        """
        _check(self.sdk.SetAcquisitionMode(_ACQ_MODE["accum"]),     "SetAcquisitionMode")
        _check(self.sdk.SetNumberAccumulations(num_acc),             "SetNumberAccumulations")
        _check(self.sdk.SetAccumulationCycleTime(float(cycle_time_acc)), "SetAccumulationCycleTime")
        self._acq_mode     = "accum"
        self._accum_params = (num_acc, float(cycle_time_acc))

    @requires_cam_connected
    def setup_kinetic_mode(self, num_cycle: int, cycle_time: Optional[float] = 0,
                            num_acc: Optional[int] = 1,
                            cycle_time_acc: Optional[float] = 0,
                            num_prescan: Optional[int] = 0,
                            mode: Optional[str] = "kinetic",
                            result_mode: str = "sum") -> None:
        """
        Configure kinetic series acquisition mode.

        Args:
            num_cycle:      Number of kinetic cycles (frames).
            cycle_time:     Minimum cycle time in seconds.
            num_acc:        Accumulations per cycle.
            cycle_time_acc: Minimum accumulation cycle time in seconds.
            num_prescan:    Number of pre-scan cycles.
            mode:           Informational label.
            result_mode:    Handled by AcquisitionService, not the camera layer.
        """
        _check(self.sdk.SetAcquisitionMode(_ACQ_MODE["kinetic"]),    "SetAcquisitionMode")
        _check(self.sdk.SetNumberKinetics(num_cycle),                "SetNumberKinetics")
        _check(self.sdk.SetKineticCycleTime(float(cycle_time)),      "SetKineticCycleTime")
        _check(self.sdk.SetNumberAccumulations(num_acc),             "SetNumberAccumulations")
        _check(self.sdk.SetAccumulationCycleTime(float(cycle_time_acc)), "SetAccumulationCycleTime")
        self._acq_mode       = "kinetic"
        self._kinetic_params = (num_cycle, float(cycle_time), num_acc,
                                float(cycle_time_acc), num_prescan)

    @requires_cam_connected
    def setup_fast_kinetic_mode(self, num_acc: int,
                                  cycle_time_acc: Optional[float] = 0,
                                  mode: Optional[str] = "fast_kinetic",
                                  result_mode: str = "sum") -> None:
        """
        Configure fast-kinetic acquisition mode.

        Args:
            num_acc:        Number of fast-kinetic frames.
            cycle_time_acc: Minimum cycle time in seconds.
            mode:           Informational label.
            result_mode:    Handled by AcquisitionService, not the camera layer.
        """
        _check(self.sdk.SetAcquisitionMode(_ACQ_MODE["fast_kinetic"]), "SetAcquisitionMode")
        # SetFastKineticsEx(exposedRows, seriesLength, time, mode, hbin, vbin, offset)
        hstart, hend, vstart, vend, hbin, vbin = self._roi
        exposed_rows = vend - vstart
        error = self.sdk.SetFastKineticsEx(
            exposed_rows,           # rows to expose per frame
            num_acc,                # number of frames in the series
            self._exposure,         # exposure time in seconds
            _READ_MODE["image"],    # read mode (Image = 4)
            hbin, vbin,
            vstart + 1,             # 1-based start row
        )
        _check(error, "SetFastKineticsEx")
        self._acq_mode            = "fast_kinetic"
        self._fast_kinetic_params = (num_acc, float(cycle_time_acc))

    @requires_cam_connected
    def setup_cont_mode(self, cycle_time: Optional[float] = 0,
                         mode: Optional[str] = "cont") -> None:
        """
        Configure continuous (run-till-abort) acquisition mode.

        Args:
            cycle_time: Minimum cycle time in seconds (0 = fastest possible).
            mode:       Informational label.
        """
        _check(self.sdk.SetAcquisitionMode(_ACQ_MODE["cont"]),  "SetAcquisitionMode")
        _check(self.sdk.SetKineticCycleTime(float(cycle_time)), "SetKineticCycleTime")
        self._acq_mode        = "cont"
        self._cont_cycle_time = float(cycle_time)

    # ── mode / param getters ──────────────────────────────────────────────────

    def get_acquisition_mode(self) -> str:
        """Return the current acquisition mode string."""
        return self._acq_mode

    def get_accum_mode_parameters(self) -> Tuple:
        """Return (num_acc, cycle_time_s) for accumulation mode."""
        return self._accum_params

    def get_kinetic_mode_parameters(self) -> Tuple:
        """Return (num_cycle, cycle_time, num_acc, cycle_time_acc, num_prescan)."""
        return self._kinetic_params

    def get_fast_kinetic_mode_parameters(self) -> Tuple:
        """Return (num_frames, cycle_time_s) for fast-kinetic mode."""
        return self._fast_kinetic_params

    def get_acquisition_parameters(self) -> dict:
        """Return a dict summarising all current acquisition parameters."""
        return {
            "acquisition_mode":  self._acq_mode,
            "read_mode":         self._read_mode,
            "exposure":          self._exposure,
            "roi":               self._roi,
            "accum_params":      self._accum_params,
            "kinetic_params":    self._kinetic_params,
            "fast_kinetic":      self._fast_kinetic_params,
        }


    # ══════════════════════════════════════════════════════════════════════════
    #  TRIGGER MODE
    # ══════════════════════════════════════════════════════════════════════════

    @requires_cam_connected
    def set_trigger_mode(self, mode: str) -> None:
        """
        Set the acquisition trigger source.

        Args:
            mode: One of 'int', 'ext', 'ext_start', 'ext_exp', 'ext_fvb_em',
                  'software', 'ext_charge_shift'.

        Raises:
            ValueError: If mode is not one of the supported values.
        """
        self.validate_trigger_mode(mode)
        _check(self.sdk.SetTriggerMode(_TRIG_MODE[mode]), "SetTriggerMode")
        self._trigger_mode = mode


    # ══════════════════════════════════════════════════════════════════════════
    #  EXPOSURE
    # ══════════════════════════════════════════════════════════════════════════

    @requires_cam_connected
    def set_exposure(self, exposure: float) -> None:
        """
        Set the sensor exposure time.

        Args:
            exposure: Exposure time in seconds (must be ≥ 0).

        Raises:
            ValueError: If exposure is negative.
        """
        self.validate_exposure(exposure)
        _check(self.sdk.SetExposureTime(exposure), "SetExposureTime")
        self._exposure = exposure


    # ══════════════════════════════════════════════════════════════════════════
    #  AMPLIFIER / HORIZONTAL SHIFT SPEED
    # ══════════════════════════════════════════════════════════════════════════

    @requires_cam_connected
    def get_all_amp_modes(self) -> List[dict]:
        """
        Return all (channel, oamp, hsspeed, preamp) combinations supported by
        the camera as a list of dicts that include the speed in MHz and the
        pre-amplifier gain factor.
        """
        error, num_channels = self.sdk.GetNumberADChannels()
        _check(error, "GetNumberADChannels")
        error, num_preamp = self.sdk.GetNumberPreAmpGains()
        _check(error, "GetNumberPreAmpGains")

        modes = []
        for ch in range(num_channels):
            for oamp in range(2):   # 0 = EMCCD, 1 = conventional
                error, n_speeds = self.sdk.GetNumberHSSpeeds(ch, oamp)
                if error != DRV_SUCCESS:
                    continue
                for hs in range(n_speeds):
                    error, speed_mhz = self.sdk.GetHSSpeed(ch, oamp, hs)
                    if error != DRV_SUCCESS:
                        continue
                    for pa in range(num_preamp):
                        error, gain = self.sdk.GetPreAmpGain(pa)
                        gain = gain if error == DRV_SUCCESS else 0.0
                        modes.append(SimpleNamespace(
                            channel     = ch,
                            oamp        = oamp,
                            hsspeed     = hs,
                            preamp      = pa,
                            hsspeed_MHz = speed_mhz,
                            preamp_gain = gain,
                        ))
        return modes

    @requires_cam_connected
    def set_amp_mode(self, channel: Optional[int], oamp: Optional[int],
                     hsspeed: Optional[int], preamp: Optional[int]) -> None:
        """
        Configure the output amplifier and horizontal shift speed.

        Any argument that is None is left unchanged.

        Args:
            channel:  ADC channel index.
            oamp:     Output amplifier index (0 = EMCCD, 1 = conventional).
            hsspeed:  Horizontal shift speed index.
            preamp:   Pre-amplifier gain index.
        """
        self.validate_amp(channel, oamp, hsspeed, preamp)
        if channel  is not None:
            _check(self.sdk.SetADChannel(channel),           "SetADChannel")
            self._channel = channel
        if oamp     is not None:
            _check(self.sdk.SetOutputAmplifier(oamp),        "SetOutputAmplifier")
            self._oamp = oamp
        if hsspeed  is not None:
            _check(self.sdk.SetHSSpeed(self._oamp, hsspeed), "SetHSSpeed")
            self._hsspeed = hsspeed
        if preamp   is not None:
            _check(self.sdk.SetPreAmpGain(preamp),           "SetPreAmpGain")
            self._preamp = preamp


    # ══════════════════════════════════════════════════════════════════════════
    #  VERTICAL SHIFT SPEED
    # ══════════════════════════════════════════════════════════════════════════

    @requires_cam_connected
    def get_all_vsspeeds(self) -> List[float]:
        """
        Return all available vertical shift speeds in µs/pixel.

        Returns:
            List of float speed values.
        """
        error, n = self.sdk.GetNumberVSSpeeds()
        _check(error, "GetNumberVSSpeeds")
        speeds = []
        for i in range(n):
            error, speed = self.sdk.GetVSSpeed(i)
            if error == DRV_SUCCESS:
                speeds.append(speed)
        return speeds

    @requires_cam_connected
    def get_max_vsspeed(self) -> Tuple[int, float]:
        """
        Return the fastest recommended vertical shift speed.

        Returns:
            Tuple (index, speed_us_per_pixel).
        """
        error, index, speed = self.sdk.GetFastestRecommendedVSSpeed()
        _check(error, "GetFastestRecommendedVSSpeed")
        return (index, speed)

    @requires_cam_connected
    def set_vsspeed(self, vsspeed_idx: int) -> None:
        """
        Set the vertical clock shift speed by index.

        Args:
            vsspeed_idx: Index into the list returned by get_all_vsspeeds().
        """
        _check(self.sdk.SetVSSpeed(vsspeed_idx), "SetVSSpeed")
        self._vsspeed = vsspeed_idx


    # ══════════════════════════════════════════════════════════════════════════
    #  EMCCD GAIN
    # ══════════════════════════════════════════════════════════════════════════

    @requires_cam_connected
    def set_EMCCD_gain(self, emccd_gain: int, emccd_advanced: bool = False) -> None:
        """
        Set the EMCCD multiplication gain register.

        Args:
            emccd_gain:     Gain value (0–300 in normal mode; up to 1000 in
                            advanced mode).
            emccd_advanced: If True, allows gain values above 300.  Use with
                            caution — very high gains risk sensor damage.

        Raises:
            ValueError: If gain is negative, or > 300 without advanced mode.
        """
        self.validate_EMCCD_gain(emccd_gain, emccd_advanced)
        if emccd_advanced:
            _check(self.sdk.SetEMAdvanced(1), "SetEMAdvanced")
        _check(self.sdk.SetEMCCDGain(int(emccd_gain)), "SetEMCCDGain")
        self._emccd_gain = emccd_gain


    # ══════════════════════════════════════════════════════════════════════════
    #  TEMPERATURE CONTROL
    # ══════════════════════════════════════════════════════════════════════════

    @requires_cam_connected
    def get_temperature_range(self) -> Tuple[int, int]:
        """
        Return the hardware temperature range.

        Returns:
            Tuple (min_temp_C, max_temp_C).
        """
        error, min_temp, max_temp = self.sdk.GetTemperatureRange()
        _check(error, "GetTemperatureRange")
        return (min_temp, max_temp)

    @requires_cam_connected
    def cool_cam(self, target_temp: float = -85.0) -> None:
        """
        Enable the TEC cooler and block until the sensor reaches within 20 °C
        of target_temp, or until cancel_cooling is set to True.

        Args:
            target_temp: Desired sensor temperature in °C (default –85 °C).
        """
        self.cancel_cooling = False
        _check(self.sdk.SetTemperature(int(target_temp)), "SetTemperature")
        self._temperature_setpoint = target_temp
        _check(self.sdk.CoolerON(), "CoolerON")
        self.set_fan_mode("full")
        print(f"Fan mode set to: {self._fan_mode}")

        while not self.cancel_cooling:
            try:
                temp, status = self.get_temp()
                print(f"Cooling: {temp} °C, Status: {status}")
            except Exception:
                break
            if isinstance(temp, float) and temp <= target_temp + 20:
                print(f"Temperature approaching target. Status: {status}")
                break
            time.sleep(1)

    @requires_cam_connected
    def stop_cooling(self) -> None:
        """
        Request an early exit from the cool_cam() loop by setting
        cancel_cooling = True.
        """
        self.cancel_cooling = True

    @requires_cam_connected
    def warm_cam(self, safe_temp: float = -20) -> None:
        """
        Turn off the cooler and fan to begin warming the sensor.

        Note: Returns immediately; the sensor continues to warm passively.

        Args:
            safe_temp: Intended safe threshold (unused — cooler is simply
                       disabled without waiting).
        """
        self.set_fan_mode("off")
        self.cancel_cooling = True
        _check(self.sdk.CoolerOFF(), "CoolerOFF")
        print("Warming (cooler OFF)")

    def get_temp(self) -> Tuple:
        """
        Return the current sensor temperature and status string.

        Returns:
            Tuple (temperature_float, status_str).
            Returns ('--', '') if no camera is connected.
        """
        if not self.cam:
            return "--", ""
        error, temp = self.sdk.GetTemperatureF()
        status_str  = _TEMP_STATUS.get(error, str(error))
        return round(temp, 3), status_str

    @requires_cam_connected
    def set_fan_mode(self, mode: str) -> None:
        """
        Set the camera fan speed.

        Args:
            mode: 'full', 'low', or 'off'.
        """
        _check(self.sdk.SetFanMode(_FAN[mode]), "SetFanMode")
        self._fan_mode = mode


    # ══════════════════════════════════════════════════════════════════════════
    #  DISCONNECT
    # ══════════════════════════════════════════════════════════════════════════

    def safe_close(self) -> None:
        """
        Safely disconnect the camera: cancel any in-progress cooling or
        acquisition, then call close_cam() to release the SDK handle.
        """
        if not self.cam:
            return
        self.cancel_cooling = True
        try:
            if self.acquisition_in_progress():
                self.stop_acquisition()
        except Exception:
            pass
        self.close_cam()

    def close_cam(self) -> None:
        """
        Turn off the fan and shut down the Andor SDK2, releasing the camera
        handle.  Sets self.cam to None after closing.
        """
        if self.cam:
            try:
                _check(self.sdk.SetFanMode(_FAN["off"]), "SetFanMode(off)")
                self._fan_mode = "off"
            except Exception:
                pass
            _check(self.sdk.ShutDown(), "ShutDown")
            self.cam = None
            print("Camera disconnected safely")


    # ══════════════════════════════════════════════════════════════════════════
    #  LIVE VIDEO
    # ══════════════════════════════════════════════════════════════════════════

    @requires_cam_connected
    def start_live(self, acquisition_mode: str = "single") -> List[np.ndarray]:
        """
        Capture one 'tick' of live preview by acquiring the configured number
        of frames.

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
        self._stop_acq_safe()
        frames = None

        try:
            if acquisition_mode == "single":
                _check(self.sdk.SetAcquisitionMode(_ACQ_MODE["single"]), "SetAcquisitionMode")
                frames = [self._acquire_single_frame(timeout)]

            elif acquisition_mode == "accum":
                num_acc, cycle = self._accum_params
                accum_timeout = max(self._exposure * num_acc + cycle * num_acc + 5.0, 10.0)
                _check(self.sdk.SetAcquisitionMode(_ACQ_MODE["accum"]), "SetAcquisitionMode")
                frames = [self._acquire_single_frame(accum_timeout)]

            elif acquisition_mode == "kinetic":
                _check(self.sdk.SetAcquisitionMode(_ACQ_MODE["kinetic"]), "SetAcquisitionMode")
                num_frames = self._kinetic_params[0]
                frames = self._acquire_n_frames(num_frames, timeout)

            elif acquisition_mode == "fast_kinetic":
                _check(self.sdk.SetAcquisitionMode(_ACQ_MODE["fast_kinetic"]), "SetAcquisitionMode")
                num_frames = self._fast_kinetic_params[0]
                frames = self._acquire_n_frames(num_frames, timeout)

            elif acquisition_mode == "cont":
                raise RuntimeError("Continuous mode cannot be used for live preview")

        finally:
            self._stop_acq_safe()

        if frames is None:
            raise RuntimeError("No frames were obtained")
        return frames

    @requires_cam_connected
    def stop_live(self) -> None:
        """Stop any in-progress acquisition and clear the hardware frame buffer."""
        self._stop_acq_safe()
        print("Live mode stopped")

    @requires_cam_connected
    def get_live_frame(self) -> Optional[np.ndarray]:
        """
        Capture a single snap for live preview purposes (5 s timeout).

        Returns:
            2-D ndarray or None if the camera is unavailable.
        """
        if not self.cam:
            print(f"Could not obtain frame for preview. Cam: {self.cam}")
            return None
        return self._acquire_single_frame(5.0)


    # ══════════════════════════════════════════════════════════════════════════
    #  ACQUISITION
    # ══════════════════════════════════════════════════════════════════════════

    @requires_cam_connected
    def acquisition_in_progress(self) -> bool:
        """
        Check whether the camera is currently running an acquisition.

        Returns:
            True if an acquisition is active, False otherwise.
        """
        error, status = self.sdk.GetStatus()
        return status == DRV_ACQUIRING

    @requires_cam_connected
    def get_acquisition_progress(self) -> Tuple[int, int]:
        """
        Return acquisition progress counters from the hardware.

        Returns:
            Tuple (accumulations_done, series_done).
        """
        error, acc, series = self.sdk.GetAcquisitionProgress()
        _check(error, "GetAcquisitionProgress")
        return (acc, series)

    @requires_cam_connected
    def single_preview(self) -> np.ndarray:
        """
        Perform a single snap to preview the current settings without saving.

        Returns:
            2-D ndarray of the acquired frame.

        Raises:
            RuntimeError: If no frame was returned by the hardware.
        """
        timeout = self.calc_frame_timeout()
        self._stop_acq_safe()
        try:
            frame = self._acquire_single_frame(timeout)
        finally:
            self._stop_acq_safe()

        if frame is None or not frame.any():
            raise RuntimeError("Could not obtain frame for single preview")
        return frame

    @requires_cam_connected
    def start_acquisition(self) -> List[np.ndarray]:
        """
        Execute a full acquisition (single, accum, kinetic, or fast_kinetic)
        using the mode currently configured on the hardware.

        Returns:
            List of ndarrays – one per acquired frame.

        Raises:
            RuntimeError: If continuous mode is attempted or no frames are
                          returned.
        """
        timeout = self.calc_frame_timeout()
        print(f"Acquisition parameters: {self.get_acquisition_parameters()}")
        print(f"Acquisition mode: {self._acq_mode}")
        print(f"Status before start: {self.get_status()}")

        self._stop_acq_safe()
        acquisition_mode = self._acq_mode
        frames = None

        try:
            if acquisition_mode == "single":
                _check(self.sdk.SetAcquisitionMode(_ACQ_MODE["single"]), "SetAcquisitionMode")
                frames = [self._acquire_single_frame(timeout)]

            elif acquisition_mode == "accum":
                num_acc, cycle = self._accum_params
                accum_timeout = max(self._exposure * num_acc + cycle * num_acc + 5.0, 10.0)
                _check(self.sdk.SetAcquisitionMode(_ACQ_MODE["accum"]), "SetAcquisitionMode")
                frames = [self._acquire_single_frame(accum_timeout)]

            elif acquisition_mode == "kinetic":
                _check(self.sdk.SetAcquisitionMode(_ACQ_MODE["kinetic"]), "SetAcquisitionMode")
                num_frames = self._kinetic_params[0]
                frames = self._acquire_n_frames(num_frames, timeout)

            elif acquisition_mode == "fast_kinetic":
                _check(self.sdk.SetAcquisitionMode(_ACQ_MODE["fast_kinetic"]), "SetAcquisitionMode")
                num_frames = self._fast_kinetic_params[0]
                frames = self._acquire_n_frames(num_frames, timeout)

            elif acquisition_mode == "cont":
                raise RuntimeError("Continuous mode cannot be used for save acquisition")

        finally:
            self._stop_acq_safe()

        if frames is None:
            raise RuntimeError("No frames were obtained")
        return frames

    @requires_cam_connected
    def stop_acquisition(self) -> None:
        """Abort any in-progress acquisition and clear the hardware buffer."""
        self._stop_acq_safe()

    @requires_cam_connected
    def simple_acq(self, num_frames: int = 0):
        """
        Convenience wrapper for quick acquisitions without mode configuration.

        Args:
            num_frames: 0 = single snap; any positive value = grab that many
                        frames.

        Returns:
            Single ndarray (num_frames == 0) or list of ndarrays.
        """
        timeout = self.calc_frame_timeout()
        if num_frames == 0:
            frame = self._acquire_single_frame(timeout)
            print("Single frame acquired")
            return frame
        else:
            frames = self._acquire_n_frames(num_frames, timeout)
            print("Multiple frames acquired")
            return frames


    # ══════════════════════════════════════════════════════════════════════════
    #  VALIDATION
    # ══════════════════════════════════════════════════════════════════════════

    def validate_EMCCD_gain(self, emccd_gain: float, advanced: bool) -> None:
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
            raise ValueError(
                f"Invalid EMCCD gain {emccd_gain}: to set above 300 use advanced=True"
            )

    def validate_exposure(self, exposure: float) -> None:
        """
        Validate the requested exposure time.

        Args:
            exposure: Exposure time in seconds.

        Raises:
            ValueError: If exposure is negative.
        """
        if exposure < 0:
            raise ValueError(f"Invalid exposure time {exposure}: cannot be negative")

    def validate_amp(self, channel: Optional[int], oamp: Optional[int],
                     hsspeed: Optional[int], preamp: Optional[int]) -> None:
        """Placeholder for amplifier parameter validation."""
        pass

    def validate_single_track_mode(self, center: int, width: int) -> None:
        """Placeholder for single-track parameter validation."""
        pass

    def validate_multi_track_mode(self, number: int, height: int, offset: int) -> None:
        """Placeholder for multi-track parameter validation."""
        pass

    def validate_read_mode(self, read_mode: str) -> None:
        """
        Validate the read mode string against the set of supported modes.

        Args:
            read_mode: Mode string to validate.

        Raises:
            ValueError: If read_mode is not in the supported set.
        """
        valid = set(_READ_MODE.keys())
        if read_mode not in valid:
            raise ValueError(f"Invalid read mode: {read_mode}. Valid modes are: {valid}")

    def validate_shutter_settings(self, mode: str, ttl_mode: int,
                                   open_time: Optional[float],
                                   close_time: Optional[float]) -> bool:
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
        if mode not in _SHUTTER:
            raise ValueError(f"Invalid shutter mode: {mode}. Valid: {list(_SHUTTER)}")
        if ttl_mode not in [0, 1]:
            raise ValueError("TTL mode must be 0 (low is open) or 1 (high is open).")
        min_open, min_close = self.get_min_shutter_times()
        if open_time  is not None and open_time  < min_open:  open_time  = min_open
        if close_time is not None and close_time < min_close: close_time = min_close
        return True

    def validate_acquisition_mode(self, mode: str) -> bool:
        """
        Validate the acquisition mode string.

        Args:
            mode: Acquisition mode string to check.

        Returns:
            True on success.

        Raises:
            ValueError: If mode is not in the supported set.
        """
        valid = list(_ACQ_MODE.keys())
        if mode not in valid:
            raise ValueError(f"Invalid acquisition mode: {mode}. Valid: {valid}")
        return True

    def validate_trigger_mode(self, mode: str) -> bool:
        """
        Validate the trigger mode string.

        Args:
            mode: Trigger mode string to check.

        Returns:
            True on success.

        Raises:
            ValueError: If mode is not in the supported set.
        """
        valid = list(_TRIG_MODE.keys())
        if mode not in valid:
            raise ValueError(f"Invalid trigger mode: {mode}. Valid: {valid}")
        return True

    def validate_roi(self, hstart: int, hend: Optional[int],
                     vstart: int, vend: Optional[int],
                     hbin: int, vbin: int) -> Tuple:
        """
        Validate and clamp ROI parameters against hardware limits for the
        given binning.

        None values and out-of-range values are silently replaced with valid
        defaults.

        Args:
            hstart: Horizontal start pixel (0-based, inclusive).
            hend:   Horizontal end pixel (0-based, exclusive).  None = max.
            vstart: Vertical start pixel (0-based, inclusive).
            vend:   Vertical end pixel (0-based, exclusive).  None = max.
            hbin:   Horizontal binning factor.
            vbin:   Vertical binning factor.

        Returns:
            Validated / clamped tuple (hstart, hend, vstart, vend, hbin, vbin).

        Raises:
            ValueError: If end ≤ start, or the ROI size is not divisible by
                        the binning factor.
        """
        if hbin is None or hbin < 1: hbin = 1
        if vbin is None or vbin < 1: vbin = 1

        h_limits, v_limits = self.get_roi_limits(hbin=hbin, vbin=vbin)
        hmin, hmax, hpstep, hsstep, hmaxbin = h_limits
        vmin, vmax, vpstep, vsstep, vmaxbin = v_limits
        print(f"Horizontal limits: hmin={hmin}, hmax={hmax}, hpstep={hpstep}, hsstep={hsstep}, hmaxbin={hmaxbin}")
        print(f"Vertical limits:   vmin={vmin}, vmax={vmax}, vpstep={vpstep}, vsstep={vsstep}, vmaxbin={vmaxbin}")

        if hstart is None or hstart < 0:  hstart = 0
        if vstart is None or vstart < 0:  vstart = 0
        if hend   is None or hend > hmax: hend   = hmax
        if vend   is None or vend > vmax: vend   = vmax

        if hend <= hstart or vend <= vstart:
            raise ValueError("ROI end positions must be greater than start positions.")

        if (hend - hstart) % hbin != 0 or (vend - vstart) % vbin != 0:
            raise ValueError(
                f"ROI width and height must be divisible by their binning factors "
                f"(hsize={hend - hstart} % hbin={hbin} = {(hend - hstart) % hbin})."
            )
        return hstart, hend, vstart, vend, hbin, vbin

    def validate_bit_shift(self, bit_shift_pixels, bit_shift_vstart,
                            bit_shift_vend) -> Tuple:
        """
        Validate and clamp bit-shift parameters against the current ROI
        boundaries.

        Args:
            bit_shift_pixels: Pixel shift amount.
            bit_shift_vstart: Start row of the shift region (clamped to ROI
                              vstart).
            bit_shift_vend:   End row of the shift region (clamped to ROI
                              vend).

        Returns:
            Validated tuple (bit_shift_pixels, bit_shift_vstart, bit_shift_vend).

        Raises:
            ValueError: If the resulting vstart > vend.
        """
        _, _, vstart, vend, _, _ = self.get_roi()
        if bit_shift_vstart is None or bit_shift_vstart < vstart:
            bit_shift_vstart = vstart
        if bit_shift_vend   is None or bit_shift_vend   > vend:
            bit_shift_vend   = vend
        if bit_shift_vstart > bit_shift_vend:
            raise ValueError(
                f"Bit shift region must be between {vstart} – {vend}"
            )
        return bit_shift_pixels, bit_shift_vstart, bit_shift_vend


    # ══════════════════════════════════════════════════════════════════════════
    #  FILE MANAGEMENT
    # ══════════════════════════════════════════════════════════════════════════

    def set_dlls_path(self, dlls_path: str) -> None:
        """
        Prepend *dlls_path* to the OS DLL/shared-library search path so that
        the Andor atmcd DLL is found by pyAndorSDK2.

        On Windows this calls os.add_dll_directory (Python ≥ 3.8) and also
        updates PATH for compatibility.  On Linux/macOS it prepends to
        LD_LIBRARY_PATH / DYLD_LIBRARY_PATH respectively.

        Note: This must be called *before* pyAndorSDK2 is first imported in
        the process to have any effect.
        """
        dlls_path = str(dlls_path)
        if sys.platform.startswith("win"):
            try:
                os.add_dll_directory(dlls_path)   # Python ≥ 3.8
            except AttributeError:
                pass
            os.environ["PATH"] = dlls_path + os.pathsep + os.environ.get("PATH", "")
        elif sys.platform.startswith("linux"):
            current = os.environ.get("LD_LIBRARY_PATH", "")
            os.environ["LD_LIBRARY_PATH"] = dlls_path + os.pathsep + current
        elif sys.platform == "darwin":
            current = os.environ.get("DYLD_LIBRARY_PATH", "")
            os.environ["DYLD_LIBRARY_PATH"] = dlls_path + os.pathsep + current