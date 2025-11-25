from camera import RamanCameraModel
from spectrometer import SpectrometerModel
from unittest.mock import MagicMock
import time

class RamanCameraController:

    def __init__(self,view):
        self.view = view
        self.camera = RamanCameraModel()
        self.spec = SpectrometerModel()
        # self.camera = MagicMock()    # use temporally for testing


    def connect_cam(self):
        self.camera.connect_cam()
        self.camera.get_cam_params()     # save cam defaults for later
        self.camera.set_default_settings()
        # self.cool_cam(target_temp=-80)
        return
    
    def isBusy_cam(self):
        return self.camera.busy

    def cool_cam(self,target_temp):
        self.camera.cool_cam(target_temp)

    def warm_cam(self):
        self.camera.warm_cam()

    def disconnect_cam(self):
        self.camera.safe_close()
        return

    def start_live(self):
        self.camera.start_live()
        return
    
    def stop_live(self):
        self.camera.end_live()
        return
    
    def get_temp(self):
        return self.camera.get_temp()
    
    def get_live_frame(self):
        return self.camera.get_live_frame()
    
    def acquire_single(self):
        return self.camera.simple_acq()
    
    def adjust_frame(self,frame):
        return self.camera.adjust_frame(frame)


    # def test(self,raw_params):
    #     try:
    #         params = self.validate_inputs(raw_params)
    #         for param,val in params.items():
    #             print(f"{param}: {val}\n")
    #     except:
    #         print("Wrong input")
    #     params = self.validate_inputs(raw_params)
    #     self.camera.connect_cam()
    #     time.sleep(5.0)
    #     self.camera.close_cam()
        
    # def run_exp(self,raw_params):
    #     try:
    #         params = self.validate_inputs(raw_params)
    #         self.prep_cam(params)
    #         frame, spectrum = self.acquire_data(params)
    #         self.save_results(params, frame, spectrum)

    #         # self.view.show_info("Experiment completed successfully!") # TOD0

    #     except Exception as e:
    #         print("Could not run experiment")
    #         # self.view.show_error(f"Error: {str(e)}") # TOD0

    #     print("Experiment completed.")
    #     self.camera.close_cam()
    
    # # validate data formats
    # def validate_inputs(self,params):
    #     """
    #     params contains:
    #     temp, exposure_time, read_mode, acq_mode, hbin, vbin, accum_n, roi, save_path, dlls_path
    #     """

    #     # validate paths here:
    #     # TOD0

    #     # numeric conversions:
    #     # TOD0: validate for sanity
    #     params["temp"] = float(params["temp"])
    #     params["exposure_time"] = float(params["exposure_time"])
    #     params["hbin"] = int(params["hbin"])
    #     params["vbin"] = int(params["vbin"])
    #     params["accum_n"] = int(params["accum_n"]) if params["accum_n"] else None

    #     # modes:
    #     # TOD0 change to drop down menus!

    #     # check roi:
    #     # TOD0: validate sanity
    #     if params["roi"]:
    #         params["roi"] = self.parse_roi(params["roi"])
        
    #     return params
    
    # # parse roi
    # def parse_roi(self,roi):
    #     try:
    #         x,y,w,h = map(int,roi.split(","))
    #         return (x,y,w,h)
    #     except:
    #         raise ValueError("ROI must be in format: x,y,w,h (integers).")
        
    # # prepare the camera
    # def prep_cam(self,params):
    #     """Set DLL, Connect camera, cool down, set modes, roi"""

    #     # update paths if given
    #     if params["dlls_path"]:
    #         self.camera.set_dlls_path(params["dlls_path"])
    #     if params["save_path"]:
    #         self.camera.set_save_path(params["save_path"])
        
    #     # connect camera
    #     self.camera.connect_cam()

    #     # cool cam
    #     self.camera.cool_cam(params["temp"])

    #     # set acquisition:
    #     self.camera.set_cam_settings(
    #         exposure=params["exposure_time"],
    #         hbin=params["hbin"],
    #         vbin=params["vbin"],
    #         read_mode=params["read_mode"],
    #         acq_mode=params["acq_mode"],
    #     )

    #     # set roi if given
    #     if params["roi"]:
    #         self.camera.set_roi(params["roi"],params["hbin"],params["vbin"])

    # acquisition
    def acquire_data(self,params):
        # run acquisition
        acq_mode = params["acq_mode"]
        if acq_mode == "single":
            frame, spectrum = self.camera.acquire_single()
        elif acq_mode == "accumulate":
            frame, spectrum = self.camera.acquire_accumulate(params["accum_n"])
        elif acq_mode == "run_till_abort":
            frame, spectrum = self.camera.acquire_rta()
        return frame,spectrum

    # save data
    def save_results(self,params,frame,spectrum):

        ts = int(time.time())
        self.camera.save_data(frame, spectrum, ts)
        self.camera.save_meta(
            frame=frame,
            exposure=params["exposure"],
            hbin=params["hbin"],
            vbin=params["vbin"],
            roi=params["roi"],
            temp=params["temp"],
            timestamp=ts
        )

        
