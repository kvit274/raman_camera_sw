from camera import RamanCameraModel
from camera_2 import RamanCameraModel2
from spectrometer import SpectrometerModel
from unittest.mock import MagicMock
from test_cam import TestCameraModel
from test_spec import TestSpectrometerModel
import time
from threads import CoolingWorker, WarmUpCloseWorker, AcquisitionWorker, LiveWorker
from PyQt5.QtCore import QObject, pyqtSignal
import traceback
from acquisition_service import AcquisitionService
import numpy as np
from fsm import CameraStateMachine, CameraState
from camera_config import CameraConfig, CameraConfigModel

class RamanCameraController(QObject):
    """
    MVC Controller that mediates between the Qt GUI (MainWindow) and the
    hardware model (RamanCameraModel / AcquisitionService).
 
    Responsible for:
    - Camera lifecycle management (connect → cool → acquire → disconnect).
    - Delegating hardware calls to RamanCameraModel.
    - Delegating all data processing and file I/O to AcquisitionService.
    - Enforcing valid state transitions via CameraStateMachine.
    - Running blocking operations (cooling, acquisition, live) in QThreads.
    - Broadcasting results / errors to the GUI via Qt signals.
 
    Signals:
        error_signal(str):         Emitted on a recoverable error with a human-readable message.
        camera_lost_signal():      Emitted when the physical camera becomes unreachable.
        send_msg(str):             General-purpose message forwarding signal.
        shutter_state_changed(str):Emitted after the shutter state changes.
        amp_modes_loaded(object):  Emitted after amp modes are fetched from hardware.
        vsspeeds_loaded(object):   Emitted after VS-speeds are fetched from hardware.
        message_signal(str):       Emitted to display informational messages in the GUI.
        live_frame_ready(object, object): Emitted per live-mode frame (frame, spectrum).
        live_finished():           Emitted when the live worker exits.
        acquisition_finished(object): Emitted when an async acquisition completes (spectrum).
        ui_state_changed(object):  Emitted whenever the FSM state changes (CameraState).
    """

    error_signal = pyqtSignal(str)
    camera_lost_signal = pyqtSignal()
    send_msg = pyqtSignal(str)
    shutter_state_changed = pyqtSignal(str)
    amp_modes_loaded = pyqtSignal(object)
    vsspeeds_loaded = pyqtSignal(object)
    message_signal = pyqtSignal(str)
    live_frame_ready = pyqtSignal(object,object)
    live_finished = pyqtSignal()
    acquisition_finished = pyqtSignal(object)
    ui_state_changed = pyqtSignal(str)

    def __init__(self):
        """
        Initialise the controller, wiring together the camera model, acquisition
        service, config model, and FSM.  All worker thread references start as None.
        """
        super().__init__()

        self.camera = RamanCameraModel2()
        # self.camera = TestCameraModel()
        self.acquisition_service = AcquisitionService()
        self.spec = TestSpectrometerModel() # delete

        self.config_model = CameraConfigModel()
        self.cooling_worker = None
        self._error_active = False
        self.live_worker = None
        self.acq_worker = None
        self.warmup_close_worker = None
        self.fsm = CameraStateMachine()
        self.fsm.state_changed.connect(lambda s: self.ui_state_changed.emit(s.name))


    # ==== Decorators =====

    def handle_errors(func):
        """
        Method decorator that catches all exceptions and routes them to the
        appropriate error signal or camera-lost signal.
 
        On any exception:
        - If the camera object exists but self.cam is None (i.e. the physical
          camera disappeared), transitions the FSM to DISCONNECTED and emits
          camera_lost_signal.
        - If the camera reports unhealthy via get_device_info(), same as above.
        - Otherwise emits error_signal with the exception message (recoverable).
 
        Uses self._error_active to avoid flooding the UI with repeated signals
        for the same underlying fault.
        """
        def wrapper(self, *args, **kwargs):
            try:
                result = func(self, *args, **kwargs)
                self._error_active = False
                return result

            except Exception as e:
                print("============ EXCEPTION ============")
                traceback.print_exc()
                print("===================================")

                msg = str(e) if str(e) else e.__class__.__name__

                cam_exists = self.camera is not None
                cam_connected = cam_exists and getattr(self.camera, "cam", None) is not None

                if cam_exists and not cam_connected:
                    self.fsm.set_state(CameraState.DISCONNECTED)

                    if not self._error_active:
                        self._error_active = True
                        self.camera_lost_signal.emit()
                    return None

                if cam_connected:
                    try:
                        self.camera.get_device_info()
                    except Exception:
                        self.fsm.set_state(CameraState.DISCONNECTED)

                        if not self._error_active:
                            self._error_active = True
                            self.camera_lost_signal.emit()
                        return None

                if not self._error_active:
                    self._error_active = True
                    self.error_signal.emit(msg)

                return None

        return wrapper
    
    def get_state(self):
        """
        Return the current FSM state.
 
        Returns:
            CameraState enum value.
        """
        return self.fsm.get_state()

    def display_msg(self,msg:str):
        """
        Emit a message string to the GUI via message_signal.
 
        Args:
            msg: Human-readable message to display.
        """
        self.message_signal.emit(msg)
        return

    @handle_errors
    def display_shutter_state(self):
        """
        Query the current shutter state from hardware and broadcast it via
        shutter_state_changed so the GUI can update its indicator.
        """
        state = self.camera.get_shutter()
        self.shutter_state_changed.emit(state)
        return

    @handle_errors
    def display_acquisition_state(self):
        """
        Query whether acquisition is in progress and return (in_progress, progress).
 
        Returns:
            Tuple (bool, progress_tuple) from the hardware.
        """
        in_progress_state = self.camera.acquisition_in_progress()
        progress = self.camera.get_acquisition_progress()
        return in_progress_state,progress
        

    # ==== Action methods =====

    @handle_errors
    def connect_cam(self):
        """
        Connect to the camera, load hardware metadata into the UI, read the
        current settings into the config model, and immediately begin cooling.
 
        State transition: DISCONNECTED → CONNECTED → COOLING.
        """
        try:
            self.fsm.require("connect")
            self.camera.connect_cam()
            self.load_amp_modes()
            self.load_vsspeeds()
            self.config_model.update_from_dict(self.cam_settings_to_user_config())
            self.display_shutter_state()

            self.fsm.set_state(CameraState.CONNECTED)
            self.cool_cam(target_temp=-85)
        except:
            self.display_msg("No camera found")
        return

    def is_camera_alive(self):
        """
        Check whether the camera is still physically accessible.
 
        Returns:
            True if the camera is connected and responds to get_device_info().
        """
        try:
            if not self.camera.cam:
                return False
            self.camera.get_device_info()
            return True
        except:
            return False
    
    def isBusy_cam(self):
        """
        Return whether the camera model reports a busy state.
 
        Returns:
            Boolean busy flag from the camera model.
        """
        return self.camera.busy

    def detect_cam_size(self):
        """
        Return the full detector size unaffected by ROI settings.
 
        Returns:
            Tuple (width, height) in pixels.
        """
        return self.camera.detect_cam_size()

    @handle_errors
    def set_save_frame_path(self,path):
        """
        Update the output directory used by AcquisitionService for all saved files.
 
        Args:
            path: New save directory (str or Path).
        """
        self.acquisition_service.set_save_frame_path(path)
        return

    @handle_errors
    def cool_cam(self,target_temp):
        """
        Start a CoolingWorker thread to cool the sensor to target_temp.
 
        If a cooling worker is already running, it is cancelled and awaited before
        the new one starts.  Transitions the FSM to COOLING.
 
        Args:
            target_temp: Target temperature in °C (e.g. –85).
        """
        self.fsm.require("start_cooling")
        if self.cooling_worker and self.cooling_worker.isRunning():
            self.camera.cancel_cooling = True
            self.cooling_worker.wait()

        self.cooling_worker = CoolingWorker(self.camera, target_temp)
        self.fsm.set_state(CameraState.COOLING)

        self.cooling_worker.finished.connect(self.on_cooling_finished)
        self.cooling_worker.start()
        return
    
    def on_cooling_finished(self):
        """
        Slot called when CoolingWorker finishes.
 
        Verifies the camera is still alive and transitions the FSM to READY, then
        restores the user's camera config.  Transitions to ERROR on failure.
        """
        try:
            if not self.is_camera_alive():
                self.fsm.set_state(CameraState.ERROR)
                return

            self.fsm.set_state(CameraState.READY)
            self.restore_user_config()

        except Exception:
            self.fsm.set_state(CameraState.ERROR)
            self.error_signal.emit("Cooling finished but failed to finalize camera setup.")

    @handle_errors
    def stop_cooling(self):
        """Request that the cooling loop exit early."""
        self.camera.stop_cooling()

    @handle_errors
    def warm_cam(self):
        """
        Disable the TEC cooler without waiting for the sensor to warm up.
 
        Note: For a fully safe warm-up-then-close sequence, use safe_disconnect_cam()
        instead, which runs WarmUpCloseWorker in the background.
        """
        self.camera.warm_cam()

    @handle_errors
    def disconnect_cam(self):
        """
        Stop any running live or acquisition workers, then close the camera
        immediately and transition the FSM to DISCONNECTED.
 
        Warning: Does not wait for the sensor to warm up first.  Use
        safe_disconnect_cam() for a graceful shutdown.
        """
        if self.get_state() == CameraState.LIVE:
            self.stop_live()
        if self.get_state() == CameraState.ACQUIRING:
            self.stop_acquisition()
        self.camera.close_cam()
        self.fsm.set_state(CameraState.DISCONNECTED)
        return

    @handle_errors
    def safe_disconnect_cam(self):
        """
        Start a WarmUpCloseWorker thread that warms the sensor to 20 °C before
        closing the camera connection.  Non-blocking from the caller's perspective.
        """
        self.warmup_close_worker = WarmUpCloseWorker(self.camera, target_temp=20.0)
        self.warmup_close_worker.start()
        return

    @handle_errors
    def start_live(self):
        """
        Perform one live-preview tick: acquire frame(s), optionally apply bit-shift
        correction, combine multi-frame acquisitions, convert to a spectrum, and
        expand the frame for display.
 
        Called repeatedly by LiveWorker.run() in a background thread.
 
        Returns:
            Tuple (combined_frame, spectrum_data, display_frame) or raises on error.
 
        Raises:
            RuntimeError: If no frames are captured.
        """
        self.fsm.require("start_live")
        self.fsm.set_state(CameraState.LIVE)
        user_config = self.get_user_config()
        acq_cfg = user_config.get("acquisition_mode",{})
        acq_mode = acq_cfg.get("mode", "single")
        print("acq mode in start_live:", acq_mode)
        frames = self.camera.start_live(acq_mode)
        if not frames:
            raise RuntimeError("No live frames captured")

        read_mode = self.camera.get_read_mode()
        roi = self.camera.get_roi()

        if self.should_apply_bit_shift():

            bit_shift_pixels,bit_shift_vstart,bit_shift_vend = self.camera.get_bit_shifting()
            processed_frames = self.acquisition_service.bit_shift(
                frames,
                roi=roi,
                shift_pixels=bit_shift_pixels,
                shift_vstart=bit_shift_vstart,
                shift_vend=bit_shift_vend,
            )
        else:
            processed_frames = frames


        num_frames = 1
            
        if acq_mode in ["kinetic", "fast_kinetic","accum"]:
            num_frames = len(processed_frames)

        if acq_mode in {"kinetic", "fast_kinetic"}:
            # accum mode excluded: the SDK accumulates internally and returns
            # one already-combined frame, so combining here would be a no-op.
            result_mode = acq_cfg.get("result_mode","sum")
            combined_frame = self.acquisition_service.combine_frames(processed_frames,acq_mode,num_frames,result_mode)
        else:
            combined_frame = processed_frames[0]

        spectrum_data = self.acquisition_service.convert_to_spectrum(combined_frame, roi)
        display_frame = self.acquisition_service.expand_frame_for_display(combined_frame, roi, read_mode)

        return combined_frame, spectrum_data, display_frame
    
    @handle_errors
    def stop_live(self):
        """
        Stop the live acquisition on the hardware and transition the FSM to READY.
        """
        self.fsm.require("stop_live")
        self.camera.stop_live()
        self.fsm.set_state(CameraState.READY)
        return
    
    @handle_errors
    def start_live_async(self):
        """
        Start a LiveWorker background thread for continuous live preview.
 
        Does nothing if a live worker is already running.  Wires frame_ready and
        finished signals before starting.
        """
        if self.live_worker and self.live_worker.isRunning():
            return

        self.restore_user_config()

        self.live_worker = LiveWorker(self)
        self.live_worker.frame_ready.connect(self.live_frame_ready.emit)
        self.live_worker.finished.connect(self.on_live_worker_finished)
        self.live_worker.start()


    @handle_errors
    def stop_live_async(self):
        """
        Stop the LiveWorker thread and wait for it to finish before returning.
        """
        if self.live_worker and self.live_worker.isRunning():
            self.live_worker.stop()
            self.live_worker.wait()


    def on_live_worker_finished(self):
        """
        Internal slot: clean up the live worker reference and emit live_finished.
        """
        self.live_finished.emit()
        self.live_worker = None

    @handle_errors
    def acquisition_in_progress(self):
        """
        Check whether the camera is currently running an acquisition.
 
        Returns:
            True if acquisition is in progress, False otherwise.
        """
        return self.camera.acquisition_in_progress()

    @handle_errors
    def restore_user_config(self):
        """
        Apply the settings stored in the config model to the camera hardware.
 
        Raises:
            RuntimeError: If no config (or at least no read_mode) has been set yet.
        """
        user_config = self.get_user_config()
        if not user_config or not user_config.get("read_mode"):
            raise RuntimeError("You must set parameters before acquisition")

        self.apply_cam_settings(**user_config)

    @handle_errors
    def cam_settings_to_user_config(self):
        """
        Read the current hardware settings and return them as a config dict
        compatible with the CameraConfigModel.
 
        Returns:
            Dict with keys: shutter, read_mode, acquisition_mode, trigger_mode,
            exposure, amp, vsspeed, emccd_gain.
        """
        settings = self.camera.get_settings()
        roi = settings["read_parameters/image"]
        hstart, hend, vstart, vend, hbin, vbin = roi

        shutter_mode, ttl, open_time, close_time = settings["shutter"]

        return {
            "shutter": {
                "mode": shutter_mode,
                "ttl_mode": str(ttl),
                "open_time": "" if open_time is None else str(open_time),
                "close_time": "" if close_time is None else str(close_time)
            },

            "read_mode": {
                "mode": settings["read_mode"],
                "hstart": hstart,
                "hend": hend,
                "vstart": vstart,
                "vend": vend,
                "hbin": hbin,
                "vbin": vbin,
                "processing_mode": "binning",
                "bit_shift_pixels": 0,
                "bit_shift_vstart": "",
                "bit_shift_vend": ""
            },

            "acquisition_mode": {
                "mode": "single"
            },

            "trigger_mode": settings["trigger_mode"],

            "exposure": str(settings["exposure"]),

            "amp": {
                "channel": settings["channel"],
                "oamp": settings["oamp"],
                "hsspeed": settings["hsspeed"],
                "preamp": settings["preamp"]
            },

            "vsspeed": settings["vsspeed"],

            "emccd_gain": {"emccd_gain": "", "emccd_advanced": False},
        }
    
    def get_user_config(self):
        """
        Return the currently stored camera config as a plain dict.
 
        Returns:
            Dict representation of the active CameraConfig.
        """
        return self.config_model.as_dict()
    
    def get_temp(self):
        """
        Return the current sensor temperature and status string.
 
        Returns:
            Tuple (temperature_float, status_str) forwarded from the camera model.
        """
        return self.camera.get_temp()
    
    @handle_errors
    def get_live_frame(self):
        """
        Capture a single snap for quick preview (5 s timeout).
 
        Returns:
            2-D ndarray or None on error.
        """
        return self.camera.get_live_frame()
    
    @handle_errors
    def acquire_single(self):
        """
        Perform a quick single-frame acquisition via simple_acq and save the frame.
 
        Note: Calls camera.save_frame() which does not exist on the model – this
        method will raise AttributeError at runtime.  Likely a legacy leftover.
 
        Returns:
            2-D ndarray of the acquired frame.
        """
        frame = self.camera.simple_acq()
        self.camera.save_frame(frame)
        return frame

    @handle_errors
    def single_preview(self):
        """
        Acquire one frame with the current settings for immediate display (no save).
 
        Applies bit-shift correction if configured, then converts to a spectrum.
 
        Returns:
            Tuple (frame, spectrum_data) where spectrum_data is (x, y).
        """
        self.fsm.require("preview")

        self.restore_user_config()
        frame = self.camera.single_preview()
        roi = self.camera.get_roi()
        
        user_config = self.get_user_config()
        read_cfg = user_config.get("read_mode", {})

        if self.should_apply_bit_shift():

            bit_shift_pixels,bit_shift_vstart,bit_shift_vend = self.camera.get_bit_shifting()
            frame = self.acquisition_service.bit_shift(
                [frame],
                roi=roi,
                shift_pixels=bit_shift_pixels,
                shift_vstart=bit_shift_vstart,
                shift_vend=bit_shift_vend,
            )[0]

        spectrum_data = self.acquisition_service.convert_to_spectrum(frame,roi)
        return frame, spectrum_data

    @handle_errors
    def start_acquisition(self, filename=None):
        """
        Run a full save acquisition: acquire frames, optionally apply bit-shift,
        combine multi-frame results, save PNG / NPZ / CSV, and return results.
 
        State transition: READY → ACQUIRING → (stopped by stop_acquisition).
 
        Args:
            filename: Base filename (with .npz extension) for all output files.
                      If None, timestamp-based names are generated automatically.
 
        Returns:
            Tuple (combined_frame, spectrum_data, raw_first_frame).
 
        Raises:
            RuntimeError: If no frames are acquired.
        """
        self.fsm.require("start_acquisition")

        self.restore_user_config()
        self.fsm.set_state(CameraState.ACQUIRING)
        user_config = self.get_user_config()
        acq_mode = user_config.get("acquisition_mode",{}).get("mode","single")
        frames = self.camera.start_acquisition()

        if not frames:
            raise RuntimeError("No frames acquired during acquisition")
        
        roi = self.camera.get_roi()
        if self.should_apply_bit_shift():

            before_shift_filename = f'{filename.strip(".npz")}_before_shifting.npz'
            self.acquisition_service.save_image(frames,filename=before_shift_filename)

            bit_shift_pixels,bit_shift_vstart,bit_shift_vend = self.camera.get_bit_shifting()

            processed_frames = self.acquisition_service.bit_shift(
                frames,
                roi=roi,
                shift_pixels=bit_shift_pixels,
                shift_vstart=bit_shift_vstart,
                shift_vend=bit_shift_vend,
            )
        else:
            processed_frames = frames

        num_frames = 1
        if acq_mode in ["kinetic","fast_kinetic"]:
            num_frames = len(processed_frames)

        if acq_mode in {"kinetic", "fast_kinetic"}:
            # accum mode excluded: the SDK returns one hardware-accumulated frame,
            # so there is nothing to combine in software.
            result_mode = user_config.get("acquisition_mode",{}).get("result_mode","sum")
            combined_frame = self.acquisition_service.combine_frames(processed_frames,acq_mode,num_frames,result_mode)
        else:
            combined_frame = processed_frames[0]

        self.acquisition_service.save_image(combined_frame if isinstance(combined_frame, list) else [combined_frame],filename=filename)

        spectrum_data = self.acquisition_service.convert_to_spectrum(combined_frame, roi)
        self.acquisition_service.save_npz(spectrum_data, metadata=user_config,filename=filename)
        self.acquisition_service.save_csv(combined_frame, roi, filename=filename)

        return combined_frame, spectrum_data, frames[0]

    @handle_errors
    def stop_acquisition(self):
        """
        Abort the in-progress acquisition and transition the FSM to READY.
        """
        self.fsm.require("stop_acquisition")
        self.camera.stop_acquisition()
        self.fsm.set_state(CameraState.READY)
        return
    
    @handle_errors
    def start_acquisition_async(self, filename=None):
        """
        Start an AcquisitionWorker background thread for a non-blocking acquisition.
 
        Does nothing if an acquisition worker is already running.
 
        Args:
            filename: Base filename passed through to start_acquisition().
        """
        if self.acq_worker and self.acq_worker.isRunning():
            return

        self.acq_worker = AcquisitionWorker(self, filename=filename)
        self.acq_worker.finished.connect(self.on_acquisition_worker_finished)
        self.acq_worker.start()


    @handle_errors
    def stop_acquisition_async(self):
        """
        Signal the AcquisitionWorker to stop and wait for it to finish.
        """
        if self.acq_worker and self.acq_worker.isRunning():
            self.acq_worker.stop()
            self.acq_worker.wait()


    def on_acquisition_worker_finished(self, spectrum):
        """
        Internal slot: emit acquisition_finished with the spectrum and clear
        the worker reference.
 
        Args:
            spectrum: 1-D ndarray from the acquisition, or None on error.
        """
        self.acquisition_finished.emit(spectrum)
        self.acq_worker = None
    
    @handle_errors
    def adjust_frame(self,frame):
        """
        Normalise a raw frame to uint8 grayscale for display.
 
        Delegates to AcquisitionService.adjust_frame.
 
        Args:
            frame: 2-D ndarray of raw detector counts.
 
        Returns:
            Tuple (frame8, h, w).
        """
        return self.acquisition_service.adjust_frame(frame)


    # ==== SETTINGS METHODS =====

    @handle_errors
    def apply_cam_settings(self,shutter,read_mode,acquisition_mode,trigger_mode,exposure,amp,vsspeed,emccd_gain):
        """
        Apply a complete set of camera settings to the hardware and persist them
        in the config model.
 
        Stops any active live or acquisition sessions first.  Refuses to apply
        settings while continuous acquisition mode is active.
 
        Args:
            shutter:          Dict with keys mode, ttl_mode, open_time, close_time.
            read_mode:        Dict with mode key and mode-specific parameters.
            acquisition_mode: Dict with mode key and mode-specific parameters.
            trigger_mode:     Trigger mode string.
            exposure:         Exposure time as a numeric string (seconds).
            amp:              Dict with channel, oamp, hsspeed, preamp keys.
            vsspeed:          Vertical shift speed index (int).
            emccd_gain:       Dict with emccd_gain and emccd_advanced keys.
 
        Raises:
            RuntimeError: If the acquisition mode is 'cont' (continuous).
        """
        self.fsm.require("apply_settings")
        if acquisition_mode["mode"] == "cont":
            raise RuntimeError("Cannot apply settings while in continuous acquisition mode. Please stop live mode or continuous acquisition before applying new settings.")
        if self.get_state() == CameraState.LIVE:
            self.stop_live()
        if self.get_state() == CameraState.ACQUIRING:
            self.stop_acquisition()
        self.set_read_mode(read_mode)
        self.set_trigger_mode(trigger_mode)
        self.set_amp_mode(amp)
        self.set_vsspeed(vsspeed)
        self.setup_shutter(**shutter)
        self.set_exposure(exposure)
        self.set_EMCCD_gain(**emccd_gain)
        self.set_acquisition_mode(acquisition_mode)
        self.config_model.set_config(
            CameraConfig(
                shutter=shutter,
                read_mode=read_mode,
                acquisition_mode=acquisition_mode,
                trigger_mode=trigger_mode,
                exposure=exposure,
                amp=amp,
                vsspeed=vsspeed,
                emccd_gain=emccd_gain,
            )
        )

        print(f"User config: {self.get_user_config()}")
        return

    # ==== EMCCD gain ====

    def set_EMCCD_gain(self,emccd_gain,emccd_advanced=False):
        """
        Parse and apply the EMCCD gain setting.
 
        An empty string for emccd_gain is treated as 'not set' and skipped.
 
        Args:
            emccd_gain:     Gain value as a number or empty string.
            emccd_advanced: If True, allows gain > 300.
        """
        emccd_gain = None if emccd_gain == "" else float(emccd_gain)
        if emccd_gain:
            self.camera.set_EMCCD_gain(emccd_gain,emccd_advanced=emccd_advanced)
        return

    # ==== Vsspeed ====

    def set_vsspeed(self,vsspeed):
        """
        Parse and apply the vertical shift speed index.
 
        Args:
            vsspeed: Speed index as an integer or string.
        """
        vsspeed = int(vsspeed)
        self.camera.set_vsspeed(vsspeed)
        return


    # ==== AMP methods =====

    def set_amp_mode(self,amp):
        """
        Parse and apply the output amplifier / horizontal shift speed settings.
 
        Empty string values for any parameter are treated as 'leave unchanged' (None).
 
        Args:
            amp: Dict with keys channel, oamp, hsspeed, preamp.
        """
        channel,oamp,hsspeed,preamp = amp["channel"],amp["oamp"],amp["hsspeed"],amp["preamp"]
        channel = None if channel == "" else int(channel)
        oamp = None if oamp == "" else int(oamp)
        hsspeed = None if hsspeed == "" else int(hsspeed)
        preamp = None if preamp == "" else int(preamp)
        self.camera.set_amp_mode(channel,oamp,hsspeed,preamp)
        return

    # ==== Exposure methods =====

    def set_exposure(self,exposure):
        """
        Parse and apply the exposure time.
 
        Empty string is treated as 'not set' and skipped.
 
        Args:
            exposure: Exposure time in seconds as a float or numeric string.
        """
        exposure = None if exposure == "" else float(exposure)
        if exposure:
            self.camera.set_exposure(exposure)
        return


    # ==== Acquisition mode methods ====

    def set_acquisition_mode(self,acquisition_mode):
        """
        Dispatch to the appropriate setup_*_mode helper based on the 'mode' key.
 
        Args:
            acquisition_mode: Dict with at least a 'mode' key ('single', 'accum',
                               'kinetic', 'fast_kinetic', 'cont') plus any
                               mode-specific parameters.
 
        Raises:
            ValueError: If the mode string is not recognised.
        """
        mode = acquisition_mode["mode"]
        print(f"Acquisition mode: {mode}")
        
        dispatch = {
            "single": self.setup_single_mode,
            "accum": self.setup_accum_mode,
            "kinetic": self.setup_kinetic_mode,
            "fast_kinetic": self.setup_fast_kinetic_mode,
            "cont": self.setup_cont_mode
        }

        handler = dispatch.get(mode)
        print(f"acquisition mode handler: {handler}")
        if not handler:
            raise ValueError(f"Invalid read mode: {mode}")

        handler(acquisition_mode)
        return

    def setup_single_mode(self,params):
        """
        Configure single-frame acquisition mode (no mode-specific parameters needed).
 
        Args:
            params: Acquisition mode dict (mode key is used; others ignored).
        """
        print("Got to setup_single_mode in controller")
        self.camera.setup_single_mode()
        return

    def setup_accum_mode(self,params):
        """
        Parse and apply accumulation mode parameters to the camera.
 
        Args:
            params: Dict containing at least 'num_acc' (int) and optionally
                    'cycle_time_acc' (float).
 
        Raises:
            ValueError: If 'num_acc' is missing from params.
        """
        if "num_acc" not in params:
            raise ValueError("num_acc parameter is required for accumulation mode")

        params["num_acc"] = int(params["num_acc"])

        if "cycle_time_acc" in params:
            params["cycle_time_acc"] = float(params["cycle_time_acc"])

        self.camera.setup_accum_mode(**params)
        return

    def setup_kinetic_mode(self,params):
        """
        Parse and apply kinetic series mode parameters to the camera.
 
        Args:
            params: Dict containing at least 'num_cycle' (int) and optionally
                    'cycle_time', 'num_acc', 'cycle_time_acc', 'num_prescan'.
 
        Raises:
            ValueError: If 'num_cycle' is missing from params.
        """
        if "num_cycle" not in params:
            raise ValueError("num_cycle parameter is required for kinetic mode")

        params["num_cycle"] = int(params["num_cycle"])

        if "cycle_time" in params:
            params["cycle_time"] = float(params["cycle_time"])
        if "num_acc" in params:
            params["num_acc"] = int(params["num_acc"])
        if "cycle_time_acc" in params:
            params["cycle_time_acc"] = float(params["cycle_time_acc"])
        if "num_prescan" in params:
            params["num_prescan"] = int(params["num_prescan"])

        self.camera.setup_kinetic_mode(**params)
        return

    def setup_fast_kinetic_mode(self,params):
        """
        Parse and apply fast-kinetic mode parameters to the camera.
 
        Args:
            params: Dict containing at least 'num_acc' (int) and optionally
                    'cycle_time_acc' (float).
 
        Raises:
            ValueError: If 'num_acc' is missing from params.
        """
        if "num_acc" not in params:
            raise ValueError("num_acc parameter is required for fast kinetic mode")

        params["num_acc"] = int(params["num_acc"])

        if "cycle_time_acc" in params:
            params["cycle_time_acc"] = float(params["cycle_time_acc"])

        self.camera.setup_fast_kinetic_mode(**params)
        return

    def setup_cont_mode(self,params):
        """
        Parse and apply continuous acquisition mode parameters to the camera.
 
        Args:
            params: Dict optionally containing 'cycle_time' (float or empty string).
        """
        if "cycle_time" in params:
            params["cycle_time"] = float(params["cycle_time"]) if params["cycle_time"] != "" else None

        self.camera.setup_cont_mode(**params)
        return

    # ==== Trigger mode methods =====    

    def set_trigger_mode(self,trigger_mode):
        """
        Apply the specified trigger mode to the camera.
 
        Args:
            trigger_mode: Trigger mode string (e.g. 'int', 'ext').
        """
        self.camera.set_trigger_mode(trigger_mode)
        return

    # ==== Read mode methods =====

    def get_read_mode_params(self, read_mode):
        """
        Query the current parameters for the specified read mode from the hardware.
 
        Args:
            read_mode: One of 'multi_track', 'single_track', 'random_track', 'image'.
 
        Returns:
            Mode-specific parameter tuple from the camera.
        """
        dispatch = {
            "multi_track": self.camera.get_multi_track_mode_params,
            "single_track": self.camera.get_single_track_mode_params,
            "random_track": self.camera.get_random_track_mode_params,
            "image": self.camera.get_image_mode_params
        }

        handler = dispatch.get(read_mode)
        return handler()

    def set_read_mode(self,read_mode):
        """
        Dispatch to the appropriate setup helper based on the 'mode' key.
 
        Args:
            read_mode: Dict with at least a 'mode' key ('fvb', 'image',
                       'single_track', 'multi_track', 'random_track') plus any
                       mode-specific parameters.
 
        Raises:
            ValueError: If the mode string is not recognised.
        """
        mode = read_mode["mode"]
        print(f"Trying to set read mode in controller to: {mode}")
        
        dispatch = {
            "fvb": self.set_fvb_read_mode,
            "multi_track": self.setup_multi_track_mode,
            "single_track": self.setup_single_track_mode,
            "random_track": self.setup_random_track_mode,
            "image": self.setup_image_mode
        }

        handler = dispatch.get(mode)
        print(f"Handler: {handler}")
        if not handler:
            raise ValueError(f"Invalid read mode: {mode}")

        handler(read_mode)

        return

    def set_fvb_read_mode(self,read_mode):
        """
        Apply Full-Vertical-Binning (FVB) read mode to the camera.
 
        Args:
            read_mode: Dict with key 'mode' == 'fvb'.
        """
        mode = read_mode["mode"]
        self.camera.set_read_mode(mode)

    def setup_single_track_mode(self,params):
        """
        Parse and apply single-track read mode parameters.
 
        Args:
            params: Dict optionally containing 'center' (int) and 'width' (int).
        """
        if "center" in params:
            params["center"] = int(params["center"])
        if "width" in params:
            params["width"] = int(params["width"])

        self.camera.setup_single_track_mode(**params)
        return

    def setup_multi_track_mode(self,params):
        """
        Parse and apply multi-track read mode parameters.
 
        Args:
            params: Dict optionally containing 'number' (int), 'height' (int),
                    and 'offset' (int).
        """
        if "number" in params:
            params["number"] = int(params["number"])
        if "height" in params:
            params["height"] = int(params["height"])
        if "offset" in params:
            params["offset"] = int(params["offset"])

        self.camera.setup_multi_track_mode(**params)
        return

    def setup_random_track_mode(self,params):
        """
        Apply random-track read mode parameters.
 
        Args:
            params: Dict passed directly to RamanCameraModel.setup_random_track_mode.
        """
        self.camera.setup_random_track_mode(**params)
        return

    def setup_image_mode(self, params):
        """
        Parse and apply image read mode with ROI and optional bit-shift configuration.
 
        Converts empty string values to None before passing to the camera model.
        If processing_mode is 'bit_shift', also configures the bit-shift parameters.
 
        Args:
            params: Dict containing 'mode', optional ROI keys (hstart, hend, vstart,
                    vend, hbin, vbin), 'processing_mode', and optional bit-shift keys
                    (bit_shift_pixels, bit_shift_vstart, bit_shift_vend).
        """
        print(f"Entered setup_image_mode in controller")

        hstart = int(params["hstart"]) if params.get("hstart") not in ("", None) else None
        hend = int(params["hend"]) if params.get("hend") not in ("", None) else None
        vstart = int(params["vstart"]) if params.get("vstart") not in ("", None) else None
        vend = int(params["vend"]) if params.get("vend") not in ("", None) else None
        hbin = int(params["hbin"]) if params.get("hbin") not in ("", None) else None
        vbin = int(params["vbin"]) if params.get("vbin") not in ("", None) else None

        self.camera.setup_image_mode(
            hstart=hstart,
            hend=hend,
            vstart=vstart,
            vend=vend,
            hbin=hbin,
            vbin=vbin,
            mode=params["mode"],
        )

        if params.get("processing_mode","binning") == "bit_shift":
            bit_shift_pixels = int(params["bit_shift_pixels"]) if params.get("bit_shift_pixels") not in ("", None) else None
            bit_shift_vstart = int(params["bit_shift_vstart"]) if params.get("bit_shift_vstart") not in ("", None) else None
            bit_shift_vend = int(params["bit_shift_vend"]) if params.get("bit_shift_vend") not in ("", None) else None
            self.camera.setup_bit_shifting(bit_shift_pixels,bit_shift_vstart,bit_shift_vend)
        else:
            self.camera.setup_bit_shifting(0,None,None)
        return

    # ==== Shutter methods =====

    def setup_shutter(self,mode,ttl_mode,open_time,close_time):
        """
        Parse, validate, and apply shutter settings, then refresh the GUI indicator.
 
        Empty string values for open_time / close_time are converted to None.
 
        Args:
            mode:       Shutter mode string ('auto', 'open', 'closed').
            ttl_mode:   TTL polarity as int or string.
            open_time:  Opening time in ms as float string, or empty string.
            close_time: Closing time in ms as float string, or empty string.
        """
        mode = str(mode).lower()
        ttl_mode = int(ttl_mode)
        open_time = None if open_time == "" else float(open_time)    
        close_time = None if close_time == "" else float(close_time)
        self.camera.setup_shutter(mode,ttl_mode,open_time,close_time)
        self.display_shutter_state()
        return

    # ==== ROI methods =====

    @handle_errors
    def get_roi(self):
        """
        Return the current ROI from the hardware.
 
        Returns:
            Tuple (hstart, hend, vstart, vend, hbin, vbin).
        """
        return self.camera.get_roi()

    def get_roi_limits(self, hbin, vbin):
        """
        Return the hardware ROI limits for the given binning factors.
 
        Returns:
            List of two 5-tuples [h_limits, v_limits] where each tuple is
            (min, max, position_step, size_step, max_bin).
        """
        hbin = None if hbin == "" else int(hbin)
        vbin = None if vbin == "" else int(vbin)
        return self.camera.get_roi_limits(hbin,vbin)

    def set_roi(self,hstart=0, hend=None, vstart=0, vend=None, hbin=1, vbin=1):
        """
        Parse string values and apply a new ROI to the camera.
 
        Start is inclusive, end is exclusive.  Empty strings are converted to None.
 
        Args:
            hstart: Horizontal start pixel (int or numeric string).
            hend:   Horizontal end pixel (int, numeric string, or None).
            vstart: Vertical start pixel (int or numeric string).
            vend:   Vertical end pixel (int, numeric string, or None).
            hbin:   Horizontal binning factor.
            vbin:   Vertical binning factor.
        """
        hstart = None if hstart == "" else int(hstart)
        hend = None if hend == "" else int(hend)
        vstart = None if vstart == "" else int(vstart)
        vend = None if vend == "" else int(vend)
        hbin = None if hbin == "" else int(hbin)
        vbin = None if vbin == "" else int(vbin)

        self.camera.set_roi(hstart, hend, vstart, vend, hbin, vbin)

        return
    
    def should_apply_bit_shift(self):
        """
        Determine whether bit-shift post-processing should be applied to acquired frames.
 
        Bit-shift correction is only applicable when:
        - The read mode is 'image'.
        - The processing mode is 'bit_shift'.
        - Both hbin and vbin are 1 (no hardware binning).
 
        Returns:
            True if all conditions are met, False otherwise.
        """
        read_cfg = self.get_user_config().get("read_mode", {})
        if read_cfg.get("mode") != "image":
            return False

        if read_cfg.get("processing_mode", "binning") != "bit_shift":
            return False

        hbin = int(read_cfg.get("hbin", 1) or 1)
        vbin = int(read_cfg.get("vbin", 1) or 1)
        print(f"bitshifting applied")
        return hbin == 1 and vbin == 1


    # ==== View communication methods ====

    @handle_errors
    def load_amp_modes(self):
        """
        Fetch all supported amplifier modes from the hardware and emit
        amp_modes_loaded so the GUI can populate its dropdown.
        """
        amp_modes = self.camera.get_all_amp_modes()
        self.amp_modes_loaded.emit(amp_modes)
        return

    @handle_errors
    def load_vsspeeds(self):
        """
        Fetch all supported vertical shift speeds from the hardware and emit
        vsspeeds_loaded so the GUI can populate its dropdown.
        """
        vsspeeds = self.camera.get_all_vsspeeds()
        self.vsspeeds_loaded.emit(vsspeeds)
        return

    # File mnagement methods
    @handle_errors
    def get_save_path(self):
        """
        Return the root save directory currently used by AcquisitionService.
 
        Returns:
            Path object for the current save directory.
        """
        return self.acquisition_service.get_save_path()