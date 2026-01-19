from camera import RamanCameraModel
from spectrometer import SpectrometerModel
from unittest.mock import MagicMock
from test_cam import TestCameraModel
from test_spec import TestSpectrometerModel
import time

class RamanCameraController:

    def __init__(self,view):
        self.view = view
        #self.camera = RamanCameraModel()
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
                print(f"Error in {func.__name__}: {str(e)}")
                self.view.display_msg(f"Error: {str(e)}")
        return wrapper


    # ==== View methods =====

    # might join those below later
    @handle_errors
    def display_used_params(self):
        roi = self.camera.get_roi()
        shutter = self.camera.get_shutter_parameters()
        self.view.display_used_params(roi=roi, shutter=shutter)
        return

    def display_msg(self,msg):
        self.view.display_msg(msg)
        return

    @handle_errors
    def display_shutter_state(self):
        state = self.camera.get_shutter()
        self.view.display_shutter_state(state)
        return


    # ==== Model methods =====

    @handle_errors
    def connect_cam(self):
        self.camera.connect_cam()
        self.camera.get_cam_params()     # save cam defaults for later
        self.camera.set_default_settings()
        self.display_used_params()
        self.display_shutter_state()
        # self.cool_cam(target_temp=-80)
        return
    
    def isBusy_cam(self):
        return self.camera.busy

    @handle_errors
    def cool_cam(self,target_temp):
        self.camera.cool_cam(target_temp)

    @handle_errors
    def warm_cam(self):
        self.camera.warm_cam()

    @handle_errors
    def disconnect_cam(self):
        self.camera.safe_close()
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
        return self.camera.simple_acq()
    
    @handle_errors
    def adjust_frame(self,frame):
        return self.camera.adjust_frame(frame)


    # ==== SETTINGS METHODS =====

    @handle_errors
    def setup_shutter(self,mode,tll_mode,open_time,close_time):
        mode = str(mode).lower()
        tll_mode = int(tll_mode)
        open_time = float(open_time)
        close_time = float(close_time)
        self.camera.set_shutter(mode,tll_mode,open_time,close_time)
        self.display_used_params()
        self.display_shutter_state()
        return

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
        hend = int(hend)
        vstart = int(vstart)
        vend = int(vend)
        hbin = int(hbin)
        vbin = int(vbin)

        self.view.stop_live()  # stop live before changing roi
        self.camera.set_roi(hstart, hend, vstart, vend, hbin, vbin)

        self.display_used_params()
        return


    # ==== Spectrometer methods (unused) =====

    def connect_spec(self):
        self.spec.connect()
        self.spec.get_default_settings()
        return
        
    def disconnect_spec(self):
        self.spec.disconnect()

    def set_wavelength_spec(self,wavelength):
        try:
            wavelength = float(wavelength)
        except:
            print("Wavelength must be a number (in meters)")
            return
        self.spec.set_wavelength(wavelength)
        return
    
    def set_grating_spec(self,grating,force=False):
        try:
            grating = int(grating)
        except:
            print("Grating must be an integer (counting from 1)")
            return
        self.spec.set_grating(grating,force)
        return
    
    def set_slit_width_spec(self,slit,width):
        try:
            width = float(width)
        except:
            print("Slit width must be a number (in meters)")
            return
        self.spec.set_slit_width(slit,width)
        return
    
    def get_default_settings_spec(self):

        self.spec.get_default_settings()
        return
        
