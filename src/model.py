import time
import json
import numpy as np
import pylablib as pll
from pylablib.devices import Andor
from pathlib import Path


# save data
SAVE_DIR = Path("./data")
SAVE_DIR.mkdir(parents=True, exist_ok=True)

# camera settings
TARGET_TEMP = -70
EXPOSURE_S = 0.050 # not sure
HBIN, VBIN = 1,1 # not sure about these
ROI = None # (x,y,w,h) or None for full | Region of interest

# specify dll file:

# pll.par["devices/only_windows_dlls"] = False # enable loading DLLs on Linux etc
pll.par["devices/dll/andor_sdk2"] = "C:/"


# cool camera
def cool_camera(cam,TARGET_TEMP):
    cam.set_cooling(True, temperature=TARGET_TEMP)
    print(f"Cooling {cam.get_model()} to {TARGET_TEMP}C°")
    while True:
        t = cam.get_temperature()
        if t == 70:
            print(f"Successfully cooled down to {TARGET_TEMP}C°")
            break


# start acquisition for 1 frame:
def single_acquire(cam):
    try:
        cam.start_acquisition()
        cam.get_attribute_value("CameraAcquiring") # check if the camera is acquiring
        frame = cam.wait_for_frame()
        spectrum = frame.sum(axis=0).astype(np.int32)   # turn raw 2D into 1D spectrum by summing the column pixels (more score -> brighter -> higher score)
        print(f"Frame shape: {frame.shape}, dtype: {frame.dtype}")
        return frame, spectrum
    except Exception:
        print(f"Could not acquire data for single acquisition")

# accumulate acquisition:
def accum_acquire(cam,n=10):
    try:
        cam.set_number_accumulations(n)
        cam.start_acquisition()
        frame = cam.wait_for_frame()
        spectrum = frame.sum(axis=0).astype(np.int32)
        return frame, spectrum
    except Exception:
        print(f"Could not acquire data for accumulative acquisition")

# acquire until stopped:
def till_abort_acquire(cam):
    cam.start_acquisition()
    try:
        while True:
            frame = cam.wait_for_frame(timeout=5.0)
            spectrum = frame.sum(axis=0).astype(np.int32)
    except KeyboardInterrupt:
        print(f"Acquisition was interrupted")
    finally:
        cam.abort_acquisition()
        return frame, spectrum
    
# acquire kinetic
def kinetic_acquire(cam):
    # to do
    return

# Save data
def save_data(frame,spectrum,exp_time):
    try:
        np.savetxt(SAVE_DIR / f"{exp_time}_spectrum.csv", spectrum, delimiter=",",fmt="%d") # save spectrum
        np.savetxt(SAVE_DIR / f"{exp_time}_frame.csv", frame, delimiter=",",fmt="%d")    # save image
        print(f"Data was successfully saved")
    except Exception:
        print(f"Could not save the data")

# Save metaData:
def save_meta_data(cam,frame,exp_time):
    meta = {
    "camera_model": cam.get_model(),
    "serial": cam.get_serial_number(),
    "exposure_s": EXPOSURE_S,
    "binning": {"h": HBIN, "v": VBIN},
    "roi": ROI,
    "cooling_setpoint_C": TARGET_TEMP,
    "frame_shape": frame.shape,
    "timestamp": exp_time,
    }
    (SAVE_DIR / f"meta_{exp_time}.json").write_text(json.dumps(meta, indent=2))

# visualize the spectrum:
def plot_spec(spectrum,exp_time):
    try:
        import matplotlib as plt
        plt.figure()
        plt.plot(spectrum)
        plt.title("Spectrum")
        plt.savefig(SAVE_DIR / f"{exp_time}_plot.png", dpi=200) # dpi is dots per inch -> more dots - better quality
    except Exception:
        print(f"Could not plot the spectrum")


def main():
    # connect camera
    from pylablib.devices import Andor
    cam = Andor.AndorSDK2Camera()
    print(f"Connected to: {cam.get_model()}")

    cool_camera(cam,TARGET_TEMP)
    ACQ_MODE = "single"


    # set up acquisition
    cam.set_acquisition(
        exposure = EXPOSURE_S,
        hbin=HBIN,
        vbin=VBIN,
        read_mode="image",  # gives a 2D frame | ask about other parameters here
        acq_mode = ACQ_MODE
        # acq_mode="single"   # 'single' | 'accumulate' | 'kinetic' | 'run_till_abort'
        # acq_mode = "run_till_abort" # run until stopped
        # acq_mode="accumulate" # might use for accumulate feature
    )

    if ROI:
        x,y,w,h = ROI
        cam.set_roi(x,y,w,h,hbin=HBIN,vbin=VBIN)

    if ACQ_MODE == "single":
        frame,spectrum = single_acquire(cam)
    elif ACQ_MODE == "accumulate":
        frame,spectrum = accum_acquire(cam)
    elif ACQ_MODE == "run_till_abort":
        frame,spectrum = till_abort_acquire(cam)
    elif ACQ_MODE == "kinetic":
        frame,spectrum = kinetic_acquire(cam)
    
    exp_time = int(time.time())
    save_data(frame,spectrum,exp_time)
    save_meta_data(cam,frame,exp_time)
    plot_spec(spectrum,exp_time)


    # close cam
    cam.close()

if __name__ == "__main__":
    main()