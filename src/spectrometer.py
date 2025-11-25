from pylablib.devices import Andor
import time
from pathlib import Path
from pprint import pformat

class SpectrometerModel:
    def __init__(self):
        self.spec = None


    def connect(self):

        available = Andor.list_shamrock_spectrographs()
        while not available:
            print("No spectrometers found")
            time.sleep(1)
        print(f"Found {available} spectrometer")

        try:
            self.spec = Andor.ShamrockSpectrograph()
            device = self.spec.get_device_info()
            print(f"Spectrometer {device} is connected")
        except Exception as e:
            print(f"Failed to connect spectrometer {e}")
        
    def disconnect(self):
        if self.spec is None:
            return
        try:
            self.spec.close()
            print("Spectrometer disconnected")
            self.spec = None
        except Exception:
            print("Failed to disconnect spectrometer")

    def set_wavelength(self,wavelength):
        """
        Set the wavelength in meters
        """
        if not self.spec:
            return
        
        self.spec.set_wavelength(wavelength)
        return
    
    def set_grating(self,grating,force=False):
        """
        Set grating (counting from 1)
        Call blocks until the grating is exchanged (up to 10-20 sec)
        force=True forces to set the grating if it is the same as the current one
        """
        if not self.spec:
            return
        
        self.spec.set_grating(grating,force)
        return
    
    def set_slit_width(self,slit,width):
        """
        Set slit width in m
        slit can be either be index (starting from 1)
        OR "input_side", "input_direct", "output_side", "output_direct"
        """
        if not self.spec:
            return
        
        self.spec.set_slit_width(slit,width)
        return
    
    def get_default_settings(self,save_path=Path("./spec_params.txt")):

        if not self.spec:
            return
        
        info = {}

        info["wavelength limits"] = self.spec.get_wavelength_limits

        readable_text="=== Andor Shamrock Spectrometer Parameters ===\n"
        readable_text+=pformat(info, indent=2, width=120)

        with open(save_path, "w") as f:
            f.write(readable_text)