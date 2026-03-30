from camera import RamanCameraModel
from spectrometer import SpectrometerModel
from unittest.mock import MagicMock
from test_cam import TestCameraModel
from test_spec import TestSpectrometerModel
import time
from threads import CoolingWorker, WarmUpCloseWorker
from PyQt5.QtCore import QObject, pyqtSignal
import traceback
from acquisition_service import AcquisitionService
import numpy as np

class RamanCameraController(QObject):

    error_signal = pyqtSignal(str)
    camera_lost_signal = pyqtSignal()
    send_msg = pyqtSignal(str)

    shutter_state_changed = pyqtSignal(str)
    amp_modes_loaded = pyqtSignal(object)
    vsspeeds_loaded = pyqtSignal(object)
    message_signal = pyqtSignal(str)
    ui_busy_changed = pyqtSignal(bool)

    def __init__(self):
        super().__init__()

        # self.view = view
        self.camera = RamanCameraModel()
        # self.camera = TestCameraModel()
        self.acquisition_service = AcquisitionService()
        self.spec = TestSpectrometerModel() # delete

        self.user_config = {}     # should be moved to model?
        self.cooling_worker = None
        self._error_active = False


    # ==== Decorators =====

    def handle_errors(func):
        def wrapper(self, *args, **kwargs):
            try:
                result = func(self, *args, **kwargs)

                self._error_active = False  # reset error state on successful execution
                return result

            except Exception as e:
                print("============ EXCEPTION ============")
                traceback.print_exc()
                print("===================================")

                if not self._error_active:
                    self._error_active = True

                    # if isinstance(e, (ValueError, RuntimeError)):
                    #      self.camera_lost_signal.emit(str(e))
                    # else:
                    if self.camera is None or self.camera.cam is None:
                        self.camera_lost_signal.emit()
                    else:
                        self.error_signal.emit(str(e))

                return None

        return wrapper

    def display_msg(self,msg:str):
        self.message_signal.emit(msg)
        return

    @handle_errors
    def display_shutter_state(self):
        state = self.camera.get_shutter()
        self.shutter_state_changed.emit(state)
        return

    @handle_errors
    def display_acquisition_state(self):
        in_progress_state = self.camera.acquisition_in_progress()
        progress = self.camera.get_acquisition_progress()
        # self.view.display_acquisition_state(in_progress_state,progress)
        return in_progress_state,progress
        

    # ==== Action methods =====

    @handle_errors
    def connect_cam(self):
        self.camera.connect_cam()
        self.load_amp_modes()
        self.load_vsspeeds()

        self.user_config = self.cam_settings_to_user_config()

        self.display_shutter_state()
        self.cool_cam(target_temp=-85)
        return

    def is_camera_alive(self):
        try:
            if not self.camera.cam:
                return False
            self.camera.get_device_info()
            return True
        except:
            return False
    
    def isBusy_cam(self):
        return self.camera.busy

    def detect_cam_size(self):
        return self.camera.detect_cam_size()

    @handle_errors
    def set_save_frame_path(self,path):
        self.acquisition_service.set_save_frame_path(path)
        return

    @handle_errors
    def cool_cam(self,target_temp):
        
        if self.cooling_worker and self.cooling_worker.isRunning():
            self.camera.cancel_cooling = True
            self.cooling_worker.wait()

        self.ui_busy_changed.emit(True)
        self.cooling_worker = CoolingWorker(self.camera, target_temp)
        self.cooling_worker.finished.connect(lambda: self.ui_busy_changed.emit(False))
        self.cooling_worker.start()
        return

    @handle_errors
    def stop_cooling(self):
        self.camera.stop_cooling()

    @handle_errors
    def warm_cam(self):
        self.camera.warm_cam()

    @handle_errors
    def disconnect_cam(self):
        self.camera.close_cam()
        return

    @handle_errors
    def safe_disconnect_cam(self):
        self.ui_busy_changed.emit(True)
        self.warmup_close_worker = WarmUpCloseWorker(self.camera, target_temp=20.0)
        self.warmup_close_worker.finished.connect(self.ui_busy_changed.emit(False))
        self.warmup_close_worker.start()
        return

    @handle_errors
    def start_live(self):
        frames = self.camera.start_live()
        if not frames:
            raise RuntineError("No live frames captured")

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

        acq_cfg = self.user_config.get("acquisition_mode", {}) if self.user_config else {}
        acq_mode = acq_cfg.get("mode", "single")

        num_frames = 1
        acq_mode = "single"
            
        if acq_mode in ["kinetic", "fast_kinetic"]:
            num_frames = len(processed_frames)
        if acq_mode == "accum":
            num_frames = int(acq_cfg.get("num_acc", 1))

        if acq_mode in {"accum", "kinetic", "fast_kinetic"}:
            result_mode = acq_cfg.get("result_mode","sum")
            combined_frame = self.acquisition_service.combine_frames(processed_frames,acq_mode,num_frames,result_mode)
        else:
            combined_frame = processed_frames[0]

        spectrum_data = self.acquisition_service.convert_to_spectrum(combined_frame, roi)
        display_frame = self.acquisition_service.expand_frame_for_display(combined_frame, roi, read_mode)

        return combined_frame, spectrum_data, display_frame
    
    @handle_errors
    def stop_live(self):
        self.camera.stop_live()
        return

    @handle_errors
    def acquisition_in_progress(self):
        return self.camera.acquisition_in_progress()

    @handle_errors
    def restore_user_config(self):
        if not self.user_config:
            raise RuntimeError("You must set parameters before acquisition")
            return

        self.apply_cam_settings(**self.user_config)

    @handle_errors
    def cam_settings_to_user_config(self):
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
                "mode": settings["acq_mode"]
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
    
    def get_temp(self):
        return self.camera.get_temp()
    
    @handle_errors
    def get_live_frame(self):
        return self.camera.get_live_frame()
    
    @handle_errors
    def acquire_single(self):
        frame = self.camera.simple_acq()
        self.camera.save_frame(frame)
        return frame

    @handle_errors
    def single_preview(self):
        self.restore_user_config()
        frame = self.camera.single_preview()
        roi = self.camera.get_roi()
        read_cfg = self.user_config.get("read_mode", {})

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
        self.restore_user_config()
        frames = self.camera.start_acquisition()
        self.acquisition_service.save_csv_frame(frames[0],filename)        # temp DELETE THIS testing only

        acq_mode = self.user_config.get("acquisition_mode",{}).get("mode","single")
        roi = self.camera.get_roi()

        before_shift_filename = f'{filename.strip(".npz")}_before_shifting.npz'
        self.acquisition_service.save_image(frames,filename=before_shift_filename)  # save raw image

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
            processed_frames = frames[0]

        num_frames = 1
        if acq_mode in ["kinetic","fast_kinetic"]:
            num_frames = len(processed_frames)
        if acq_mode == "accum":
            num_frames = int(self.user_config.get("acquisition_mode",{}).get("num_acc",1))
        

        if acq_mode in {"accum", "kinetic", "fast_kinetic"}:
            result_mode = self.user_config.get("acquisition_mode",{}).get("result_mode","sum")
            combined_frame = self.acquisition_service.combine_frames(processed_frames,acq_mode,num_frames,result_mode)
        else:
            print(f"frame not combined")
            combined_frame = processed_frames[0]

        self.acquisition_service.save_image(combined_frame if isinstance(combined_frame, list) else [combined_frame],filename=filename)

        spectrum_data = self.acquisition_service.convert_to_spectrum(combined_frame, roi)
        self.acquisition_service.save_npz(spectrum_data, metadata=self.user_config,filename=filename)
        self.acquisition_service.save_csv(combined_frame, roi, filename=filename)

        return combined_frame, spectrum_data, frames[0]

    @handle_errors
    def stop_acquisition(self):
        self.camera.stop_acquisition()
        return
    
    @handle_errors
    def adjust_frame(self,frame):
        return self.acquisition_service.adjust_frame(frame)


    # ==== SETTINGS METHODS =====

    @handle_errors
    def apply_cam_settings(self,shutter,read_mode,acquisition_mode,trigger_mode,exposure,amp,vsspeed,emccd_gain):
        # create cameraconfig as a dataclass instead of user_config
        if acquisition_mode["mode"] == "cont":
            raise RuntimeError("Cannot apply settings while in continuous acquisition mode. Please stop live mode or continuous acquisition before applying new settings.")
        self.stop_live()
        self.camera.stop_acquisition()
        self.set_acquisition_mode(acquisition_mode)
        self.set_read_mode(read_mode)
        self.set_exposure(exposure)
        self.set_trigger_mode(trigger_mode)
        self.setup_shutter(**shutter)
        self.set_amp_mode(amp)
        self.set_vsspeed(vsspeed)
        self.set_EMCCD_gain(**emccd_gain)

        self.user_config = {
            "shutter": shutter,
            "read_mode": read_mode,
            "acquisition_mode": acquisition_mode,
            "trigger_mode": trigger_mode,
            "exposure": exposure,
            "amp": amp,
            "vsspeed": vsspeed,
            "emccd_gain": emccd_gain
        }

        print(f"User config: {self.user_config}")
        return

    @handle_errors
    def restore_settings(self):
        if self.camera.cam.acquisition_in_progress():    # temperary
            self.camera.stop_acquisition()

        settings = self.camera.restore_acquisition_settings()

        acquisition_mode = settings["acq_mode"]
        acquisition_mode_params = {"mode":acquisition_mode}
        if acquisition_mode == "accum":
            num_acc,cycle_time = settings["acq_parameters/accum"]
            acquisition_mode_params["num_acc"] = num_acc
            acquisition_mode_params["cycle_time"] = cycle_time
        elif acquisition_mode == "kinetic":
            num_cycle, cycle_time, num_acc, cycle_time_acc, num_prescan = settings["acq_parameters/kinetic"]
            acquisition_mode_params["num_cycle"] = num_cycle
            acquisition_mode_params["cycle_time"] = cycle_time
            acquisition_mode_params["num_acc"] = num_acc
            acquisition_mode_params["cycle_time_acc"] = cycle_time_acc
            acquisition_mode_params["num_prescan"] = num_prescan
        elif acquisition_mode == "fast_kinetic":
            num_acc,cycle_time_acc = settings["acq_parameters/accum"]
            acquisition_mode_params["num_acc"] = num_acc
            acquisition_mode_params["cycle_time_acc"] = cycle_time_acc
        elif acquisition_mode == "cont":
            cycle_time = settings["acq_parameters/cont"]
            acquisition_mode_params["cycle_time"] = cycle_time
        
        self.set_acquisition_mode(acquisition_mode_params)

        read_mode = settings["read_mode"]
        read_mode_params = {"mode": read_mode}
        if read_mode == "multi_track":
            num, height, offset = settings["read_parameters/multi_track"]
            read_mode_params["number"] = num
            read_mode_params["height"] = height
            read_mode_params["offset"] = offset
        elif read_mode == "single_track":
            center, width = settings["read_parameters/single_track"]
            read_mode_params["center"] = center
            read_mode_params["width"] = width
        elif read_mode == "random_track":
            tracks = settings["read_parameters/random_track"]
            read_mode_params["tracks"] = tracks
        elif read_mode == "image":
            hstart,hend,vstart,vend,hbin,vbin = settings["read_parameters/image"]
            read_mode_params["hstart"] = hstart
            read_mode_params["hend"] = hend
            read_mode_params["vstart"] = vstart
            read_mode_params["vend"] = vend
            read_mode_params["hbin"] = hbin
            read_mode_params["vbin"] = vbin
        self.set_read_mode(read_mode_params)

        self.set_exposure(settings["exposure"])
        self.set_trigger_mode(settings["trigger_mode"])
        self.setup_shutter(*settings["shutter"])

        amp_mode = {"channel":settings["channel"],"oamp":settings["oamp"],"hsspeed":settings["hsspeed"],"preamp":settings["preamp"]}
        self.set_amp_mode(amp_mode)
        self.set_vsspeed(settings["vsspeed"])

        return

    # ==== EMCCD gain ====

    # @handle_errors
    def set_EMCCD_gain(self,emccd_gain,emccd_advanced=False):
        emccd_gain = None if emccd_gain == "" else float(emccd_gain)
        if emccd_gain:
            self.camera.set_EMCCD_gain(emccd_gain,emccd_advanced=emccd_advanced)
        return

    # ==== Vsspeed ====

    # @handle_errors
    def set_vsspeed(self,vsspeed):
        vsspeed = int(vsspeed)
        self.camera.set_vsspeed(vsspeed)
        return


    # ==== AMP methods =====

    # @handle_errors
    def set_amp_mode(self,amp):
        channel,oamp,hsspeed,preamp = amp["channel"],amp["oamp"],amp["hsspeed"],amp["preamp"]
        channel = None if channel == "" else int(channel)
        oamp = None if oamp == "" else int(oamp)
        hsspeed = None if hsspeed == "" else int(hsspeed)
        preamp = None if preamp == "" else int(preamp)
        self.camera.set_amp_mode(channel,oamp,hsspeed,preamp)
        return

    # ==== Exposure methods =====

    # @handle_errors
    def set_exposure(self,exposure):
        exposure = None if exposure == "" else float(exposure)
        if exposure:
            self.camera.set_exposure(exposure)
        return


    # ==== Acquisition mode methods ====

    # @handle_errors
    def set_acquisition_mode(self,acquisition_mode):
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
        # self.camera.set_read_mode(read_mode)
        return

    # @handle_errors
    def setup_single_mode(self,params):
        print("Got to setup_single_mode in controller")
        self.camera.setup_single_mode()
        return

    # @handle_errors
    def setup_accum_mode(self,params):
        if "num_acc" not in params:
            raise ValueError("num_acc parameter is required for accumulation mode")

        params["num_acc"] = int(params["num_acc"])

        if "cycle_time_acc" in params:
            params["cycle_time_acc"] = float(params["cycle_time_acc"])

        self.camera.setup_accum_mode(**params)
        return

    # @handle_errors
    def setup_kinetic_mode(self,params):
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

    # @handle_errors
    def setup_fast_kinetic_mode(self,params):
        if "num_acc" not in params:
            raise ValueError("num_acc parameter is required for fast kinetic mode")

        params["num_acc"] = int(params["num_acc"])

        if "cycle_time_acc" in params:
            params["cycle_time_acc"] = float(params["cycle_time_acc"])

        self.camera.setup_fast_kinetic_mode(**params)
        return

    # @handle_errors
    def setup_cont_mode(self,params):
        if "cycle_time" in params:
            params["cycle_time"] = float(params["cycle_time"]) if params["cycle_time"] != "" else None

        self.camera.setup_cont_mode(**params)
        return

    # ==== Trigger mode methods =====    

    # @handle_errors
    def set_trigger_mode(self,trigger_mode):
        self.camera.set_trigger_mode(trigger_mode)
        return

    # ==== Read mode methods =====

    # @handle_errors
    def get_read_mode_params(self, read_mode):
        
        dispatch = {
            "multi_track": self.camera.get_multi_track_mode_params,
            "single_track": self.camera.get_single_track_mode_params,
            "random_track": self.camera.get_random_track_mode_params,
            "image": self.camera.get_image_mode_params
        }

        handler = dispatch.get(read_mode)
        return handler()

    # @handle_errors
    def set_read_mode(self,read_mode):
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

    # @handle_errors
    def set_fvb_read_mode(self,read_mode):
        mode = read_mode["mode"]
        self.camera.set_read_mode(mode)

    # @handle_errors
    def setup_single_track_mode(self,params):

        if "center" in params:
            params["center"] = int(params["center"])
        if "width" in params:
            params["width"] = int(params["width"])

        self.camera.setup_single_track_mode(**params)
        return

    # @handle_errors
    def setup_multi_track_mode(self,params):
        # del params["mode"]

        if "number" in params:
            params["number"] = int(params["number"])
        if "height" in params:
            params["height"] = int(params["height"])
        if "offset" in params:
            params["offset"] = int(params["offset"])

        self.camera.setup_multi_track_mode(**params)
        return

    # @handle_errors
    def setup_random_track_mode(self,params):
        self.camera.setup_random_track_mode(**params)
        return

    # @handle_errors
    def setup_image_mode(self, params):
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

        if params.get("processsing_mode","binning") == "bit_shift":
            bit_shift_pixels = int(params["bit_shift_pixels"]) if params.get("bit_shift_pixels") not in ("", None) else None
            bit_shift_vstart = int(params["bit_shift_vstart"]) if params.get("bit_shift_vstart") not in ("", None) else None
            bit_shift_vend = int(params["bit_shift_vend"]) if params.get("bit_shift_vend") not in ("", None) else None
            self.camera.setup_bit_shifting(bit_shift_pixels,bit_shift_vstart,bit_shift_vend)
        else:
            self.camera.setup_bit_shifting(0,None,None)
        return

    # ==== Shutter methods =====

    # @handle_errors
    def setup_shutter(self,mode,ttl_mode,open_time,close_time):
        mode = str(mode).lower()
        ttl_mode = int(ttl_mode)
        open_time = None if open_time == "" else float(open_time)       # get back to this! changed "" -> None
        close_time = None if close_time == "" else float(close_time)
        self.camera.setup_shutter(mode,ttl_mode,open_time,close_time)
        self.display_shutter_state()
        return

    # ==== ROI methods =====

    @handle_errors
    def get_roi(self):
        return self.camera.get_roi()

    def get_roi_limits(hbin,vbin):
        hbin = None if hbin == "" else int(hbin)
        vbin = None if vbin == "" else int(vbin)
        return self.camera.get_roi_limits(hbin,vbin)

    # @handle_errors
    def set_roi(self,hstart=0, hend=None, vstart=0, vend=None, hbin=1, vbin=1):
        """
        Set ROI with given parameters
        Start is inclusive, end is exclusive
        """

        hstart = None if hstart == "" else int(hstart)
        hend = None if hend == "" else int(hend)
        vstart = None if vstart == "" else int(vstart)
        vend = None if vend == "" else int(vend)
        hbin = None if hbin == "" else int(hbin)
        vbin = None if vbin == "" else int(vbin)

        # self.view.stop_live()  # stop live before changing roi
        self.camera.set_roi(hstart, hend, vstart, vend, hbin, vbin)

        return
    
    def should_apply_bit_shift(self):
        read_cfg = self.user_config.get("read_mode", {})
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
        amp_modes = self.camera.get_all_amp_modes()
        self.amp_modes_loaded.emit(amp_modes)
        return

    @handle_errors
    def load_vsspeeds(self):
        vsspeeds = self.camera.get_all_vsspeeds()
        self.vsspeeds_loaded.emit(vsspeeds)
        return

    # File mnagement methods
    @handle_errors
    def get_save_path(self):
        return self.acquisition_service.get_save_path()