from camera import RamanCameraModel
from spectrometer import SpectrometerModel
from unittest.mock import MagicMock
from test_cam import TestCameraModel
from test_spec import TestSpectrometerModel
import time
from threads import CoolingWorker, WarmUpCloseWorker

class RamanCameraController:

    def __init__(self,view):
        self.view = view
        # self.camera = RamanCameraModel()
        self.camera = TestCameraModel()
        #self.spec = SpectrometerModel()
        self.spec = TestSpectrometerModel()
        # self.camera = MagicMock()    # use temporally for testing


    # ==== Decorators =====

    def handle_errors(func):
        def wrapper(self, *args, **kwargs):
            try:
                return func(self, *args, **kwargs)
            except Exception as e:
                class_name = self.__class__.__name__
                print(f"Error in {class_name}.{func.__name__}: {str(e)}")
                self.view.display_msg(f"Error: {str(e)}")
        return wrapper


    # ==== View methods =====

    # might join those below later
    @handle_errors
    def display_used_params(self):
        roi = self.camera.get_roi()
        roi_dict = {
            'hstart': str(roi[0]),
            'hend': "" if roi[1] is None else str(roi[1]),
            'vstart': str(roi[2]),
            'vend': "" if roi[3] is None else str(roi[3]),
            'hbin': str(roi[4]),
            'vbin': str(roi[5])
        }

        shutter = self.camera.get_shutter_parameters()
        shutter_dict = {
            'mode': str(shutter[0]),
            'tll_mode': str(shutter[1]),
            'open_time': str(shutter[2]),
            'close_time': str(shutter[3])
        }

        read_mode = self.camera.get_read_mode()
        # read_mode_params = self.get_read_mode_params(read_mode)
        self.view.display_used_params(roi=roi_dict, shutter=shutter_dict, read_mode=read_mode)
        return

    def display_msg(self,msg:str):
        self.view.display_msg(msg)
        return

    @handle_errors
    def display_shutter_state(self):
        state = self.camera.get_shutter()
        self.view.display_shutter_state(state)
        return


    # ==== Action methods =====

    @handle_errors
    def connect_cam(self):
        self.camera.connect_cam()
        # self.camera.get_cam_params()     # save cam defaults for later
        self.camera.set_default_settings()
        self.load_amp_modes()
        self.load_vsspeeds()
        self.display_used_params()
        self.display_shutter_state()
        self.cool_cam(target_temp=-85)
        return
    
    def isBusy_cam(self):
        return self.camera.busy

    @handle_errors
    def cool_cam(self,target_temp):
        # self.camera.cool_cam(target_temp)
        self.view.disable_buttons()
        self.cooling_worker = CoolingWorker(self.camera, target_temp)
        self.cooling_worker.finished.connect(self.view.enable_buttons)
        self.cooling_worker.start()
        return

    @handle_errors
    def warm_cam(self):
        self.camera.warm_cam()

    @handle_errors
    def disconnect_cam(self):
        self.camera.close_cam()
        return

    @handle_errors
    def safe_disconnect_cam(self):
        self.view.disable_buttons()
        self.warmup_close_worker = WarmUpCloseWorker(self.camera, target_temp=20.0)
        self.warmup_close_worker.finished.connect(self.view.enable_buttons)
        self.warmup_close_worker.start()
        return

    @handle_errors
    def start_live(self):
        self.camera.start_live()
        self.view.start_live_timer()
        return
    
    @handle_errors
    def stop_live(self):
        self.camera.end_live()
        self.view.stop_live_timer()
        return
    
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
    def start_acquisition(self):
        return self.camera.start_acquisition()
    
    @handle_errors
    def adjust_frame(self,frame):
        return self.camera.adjust_frame(frame)


    # ==== SETTINGS METHODS =====

    @handle_errors
    def apply_cam_settings(self,roi,shutter,read_mode,acquisition_mode,trigger_mode,exposure,amp,vsspeed):
        self.set_roi(**roi)
        self.setup_shutter(**shutter)
        self.set_read_mode(read_mode)
        self.set_acquisition_mode(acquisition_mode)
        self.set_trigger_mode(trigger_mode)
        self.set_exposure(exposure)
        self.set_amp(amp)
        self.set_vsspeed(vsspeed)
        self.display_used_params()
        return


    # ==== Vsspeed ====

    @handle_errors
    def set_vsspeed(self,vsspeed):
        vsspeed = int(vsspeed)
        self.camera.set_vsspeed(vsspeed)
        return


    # ==== AMP methods =====

    @handle_errors
    def set_amp(self,amp):
        channel,oamp,hsspeed,preamp = amp["channel"],amp["oamp"],amp["hsspeed"],amp["preamp"]
        channel = None if channel == "" else int(channel)
        oamp = None if oamp == "" else int(oamp)
        hsspeed = None if hsspeed == "" else int(hsspeed)
        preamp = None if preamp == "" else int(preamp)
        self.camera.set_amp_mode(channel,oamp,hsspeed,preamp)
        return

    # ==== Exposure methods =====

    @handle_errors
    def set_exposure(self,exposure):
        exposure = None if exposure == "" else float(exposure)
        if exposure:
            self.camera.set_exposure(exposure)
        return

    

    @handle_errors
    def set_acquisition_mode(self,mode):
        self.camera.set_acquisition_mode(mode)
        return

    # ==== Trigger mode methods =====    

    @handle_errors
    def set_trigger_mode(self,trigger_mode):
        self.camera.set_trigger_mode(trigger_mode)
        return

    # ==== Read mode methods =====

    @handle_errors
    def get_read_mode_params(self, read_mode):
        
        dispatch = {
            "multi_track": self.camera.get_multi_track_mode_params,
            "single_track": self.camera.get_single_track_mode_params,
            "random_track": self.camera.get_random_track_mode_params,
            "image": self.camera.get_image_mode_params
        }

        handler = dispatch.get(read_mode)
        return handler()

    @handle_errors
    def set_read_mode(self,read_mode):
        mode = read_mode["mode"]
        
        dispatch = {
            "multi_track": self.setup_multi_track_mode,
            "single_track": self.setup_single_track_mode,
            "random_track": self.setup_random_track_mode,
            "image": self.setup_image_mode
        }

        handler = dispatch.get(mode)
        if not handler:
            raise ValueError(f"Invalid read mode: {mode}")

        handler(read_mode)
        # self.camera.set_read_mode(read_mode)
        return

    @handle_errors
    def setup_single_track_mode(self,params):
        del params["mode"]

        if "center" in params:
            params["center"] = int(params["center"])
        if "width" in params:
            params["width"] = int(params["width"])

        self.camera.setup_single_track_mode(**params)
        return

    @handle_errors
    def setup_multi_track_mode(self,params):
        del params["mode"]

        if "number" in params:
            params["number"] = int(params["number"])
        if "height" in params:
            params["height"] = int(params["height"])
        if "offset" in params:
            params["offset"] = int(params["offset"])

        self.camera.setup_multi_track_mode(**params)
        return

    @handle_errors
    def setup_random_track_mode(self,params):
        del params["mode"]
        # this one is not clear yet

        return

    @handle_errors
    def setup_image_mode(self,params):

        return

    # ==== Shutter methods =====

    @handle_errors
    def setup_shutter(self,mode,tll_mode,open_time,close_time):
        mode = str(mode).lower()
        tll_mode = int(tll_mode)
        open_time = None if open_time == "" else float(open_time)       # get back to this! changed "" -> None
        close_time = None if close_time == "" else float(close_time)
        self.camera.setup_shutter(mode,tll_mode,open_time,close_time)
        self.display_shutter_state()
        return

    # ==== ROI methods =====

    @handle_errors
    def get_roi(self):
        return self.camera.get_roi()

    @handle_errors
    def set_roi(self,hstart=0, hend=None, vstart=0, vend=None, hbin=1, vbin=1):
        """
        Set ROI with given parameters
        Start is inclusive, end is exclusive
        """

        hstart = int(hstart)
        hend = None if hend == "" else int(hend)
        vstart = int(vstart)
        vend = None if vend == "" else int(vend)
        hbin = int(hbin)
        vbin = int(vbin)

        self.view.stop_live()  # stop live before changing roi
        self.camera.set_roi(hstart, hend, vstart, vend, hbin, vbin)

        return


    # ==== View communication methods ====

    @handle_errors
    def load_amp_modes(self):
        amp_modes = self.camera.get_all_amp_modes()
        self.view.load_amp_modes(amp_modes)
        return

    @handle_errors
    def load_vsspeeds(self):
        vsspeeds = self.camera.get_all_vsspeeds()
        self.view.load_vsspeeds(vsspeeds)
        return

    # ==== Spectrometer methods (unused) =====

    # def connect_spec(self):
    #     self.spec.connect()
    #     self.spec.get_default_settings()
    #     return
        
    # def disconnect_spec(self):
    #     self.spec.disconnect()

    # def set_wavelength_spec(self,wavelength):
    #     try:
    #         wavelength = float(wavelength)
    #     except:
    #         print("Wavelength must be a number (in meters)")
    #         return
    #     self.spec.set_wavelength(wavelength)
    #     return
    
    # def set_grating_spec(self,grating,force=False):
    #     try:
    #         grating = int(grating)
    #     except:
    #         print("Grating must be an integer (counting from 1)")
    #         return
    #     self.spec.set_grating(grating,force)
    #     return
    
    # def set_slit_width_spec(self,slit,width):
    #     try:
    #         width = float(width)
    #     except:
    #         print("Slit width must be a number (in meters)")
    #         return
    #     self.spec.set_slit_width(slit,width)
    #     return
    
    # def get_default_settings_spec(self):

    #     self.spec.get_default_settings()
    #     return
        
