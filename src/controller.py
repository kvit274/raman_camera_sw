from model import RamanCameraModel
import time

class RamanCameraController:
    def __init__(self,view):
        self.view = view
        self.model = RamanCameraModel()

        # connect signals from view
        self.view.run_clicked.connect(self.run_exp)
        
    def run_exp(self,raw_params):
        try:
            params = self.validate_inputs(raw_params)
            self.prep_cam(params)
            frame, spectrum = self.acquire_data(params)
            self.save_results(params, frame, spectrum)

            self.view.show_info("Experiment completed successfully!")

        except Exception as e:
            self.view.show_error(f"Error: {str(e)}")

        print("Experiment completed.")
        self.model.close_cam()
    
    # validate data formats
    def validate_inputs(self,params):
        """
        params contains:
        temp, exposure_time, read_mode, acq_mode, hbin, vbin, accum_n, roi, save_path, dll_path
        """

        # validate paths here:
        # TOD0

        # numeric conversions:
        params["temp"] = float(params["temp"])
        params["exposure_time"] = float(params["exposure_time"])
        params["hbin"] = int(params["hbin"])
        params["vbin"] = int(params["vbin"])
        params["accum_n"] = int(params["accum_n"]) if params["accum_n"] else None

        # modes:
        # TOD0 change to drop down menus!

        # check roi:
        if params["roi"]:
            params["roi"] = self.parse_roi()
        
        return params
    
    # parse roi
    def parse_roi(self,roi):
        try:
            x,y,w,h = map(int,roi.split(","))
            return (x,y,w,h)
        except:
            raise ValueError("ROI must be in format: x,y,w,h (integers).")
        
    # prepare the camera
    def prep_cam(self,params):
        """Set DLL, Connect camera, cool down, set modes, roi"""

        # update paths if given
        if params["dll_path"]:
            self.model.set_dll_path(params["dll_path"])
        if params["dll_path"]:
            self.model.set_dll_path(params["dll_path"])
        
        # connect camera
        self.model.connect_cam()

        # cool cam
        self.model.cool_cam(params["temp"])

        # set acquisition:
        self.model.set_cam_settings(
            exposure=params["exposure_time"],
            hbin=params["hbin"],
            vbin=params["vbin"],
            read_mode=params["read_mode"],
            acq_mode=params["acq_mode"],
        )

        # set roi if given
        if params["roi"]:
            self.model.set_roi(params["roi"],params["hbin"],params["vbin"])

    # acquisition
    def acquire_data(self,params):
        # run acquisition
        acq_mode = params["acq_mode"]
        if acq_mode == "single":
            frame, spectrum = self.model.acquire_single()
        elif acq_mode == "accumulate":
            frame, spectrum = self.model.acquire_accumulate(params["accum_n"])
        elif acq_mode == "run_till_abort":
            frame, spectrum = self.model.acquire_rta()

    # save data
    def save_results(self,params,frame,spectrum):

        ts = int(time.time())
        self.model.save_data(frame, spectrum, ts)
        self.model.save_meta(
            frame=frame,
            exposure=params["exposure"],
            hbin=params["hbin"],
            vbin=params["vbin"],
            roi=params["roi"],
            temp=params["temp"],
            timestamp=ts
        )

        
