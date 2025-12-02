from pylablib.devices import Andor
import time
from pathlib import Path
from pprint import pformat


class TestSpectrometerModel:
    def __init__(self):
        self.spec = None


    def connect(self):

        available = ["Test Spectrometer"]
        while not available:
            print("No spectrometers found")
            time.sleep(1)
        print(f"Found {available} spectrometer")

        self.spec = available[0]
        print(f"Spectrometer {available[0]} is connected")
        
    def disconnect(self):
        if self.spec is None:
            return

        self.spec = None
        print("Spectrometer disconnected")
        return

    def set_wavelength(self,wavelength):
        """
        Set the wavelength in meters
        """
        if not self.spec:
            return
        
        print(f"Set wavelength to {wavelength} m")
        return
    
    def set_grating(self,grating,force=False):
        """
        Set grating (counting from 1)
        Call blocks until the grating is exchanged (up to 10-20 sec)
        force=True forces to set the grating if it is the same as the current one
        """
        if not self.spec:
            return
        
        print(f"Set grating to {grating}, force={force}")
        return
    
    def set_slit_width(self,slit,width):
        """
        Set slit width in m
        slit can be either be index (starting from 1)
        OR "input_side", "input_direct", "output_side", "output_direct"
        """
        if not self.spec:
            return
        
        print(f"Set slit {slit} width to {width} m")
        return
    
    def get_default_settings(self,save_path=Path("./spec_params.txt")):

        if not self.spec:
            return
        
        info = {}

        info["wavelength limits"] = (200e-9, 1200e-9)

        readable_text="=== Andor Shamrock Spectrometer Parameters ===\n"
        readable_text+=pformat(info, indent=2, width=120)

        with open(save_path, "w") as f:
            f.write(readable_text)