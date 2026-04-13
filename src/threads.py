from PyQt5.QtCore import QThread, pyqtSignal

class CoolingWorker(QThread):
    """
    Background thread that drives the camera cooling sequence.
 
    Runs RamanCameraModel.cool_cam() in a separate thread so the UI remains
    responsive while the sensor cools down.  Emits finished when done.
    """
    finished = pyqtSignal()

    def __init__(self, camera, target_temp:float=-85.0):
        """
        Args:
            camera:      RamanCameraModel instance.
            target_temp: Desired sensor temperature in °C (default –85 °C).
        """
        super().__init__()
        self.camera = camera
        self.target_temp = target_temp

    def run(self):
        """Execute the cooling sequence and emit finished on completion."""
        self.camera.cool_cam(self.target_temp)
        self.finished.emit()

class WarmUpCloseWorker(QThread):
    """
    Background thread that warms the sensor and then safely closes the camera.
 
    Used during graceful shutdown to ensure the detector is not closed while
    it is still at cryogenic temperature.  Emits finished when done.
    """
    finished = pyqtSignal()

    def __init__(self, camera, target_temp:float=20.0):
        """
        Args:
            camera:      RamanCameraModel instance.
            target_temp: Temperature in °C to warm up to before closing (default 20 °C).
        """
        super().__init__()
        self.camera = camera
        self.target_temp = target_temp

    def run(self):
        """Warm the camera to target_temp, then close the connection, and emit finished."""
        self.camera.warm_cam(self.target_temp)
        self.camera.safe_close()
        self.finished.emit()

class AcquisitionWorker(QThread):
    """
    Background thread that performs a single save acquisition.
 
    Calls RamanCameraController.start_acquisition() off the main thread and
    emits finished(spectrum) with the resulting spectrum array (or None on
    error or cancellation).
    """
    finished = pyqtSignal(object)

    def __init__(self, controller, filename=None):
        """
        Args:
            controller: RamanCameraController instance.
            filename:   Optional output filename to pass to start_acquisition.
        """
        super().__init__()
        self.controller = controller
        self.filename = filename
        self.stop_requested = False

    def stop(self):
        """
        Request cancellation of the running acquisition.
 
        Sets the stop flag and calls controller.stop_acquisition() so the
        camera exits its acquisition loop as soon as possible.
        """
        self.stop_requested = True
        self.controller.stop_acquisition()

    def run(self):
        """
        Run the acquisition.  Emits finished(spectrum) on success or
        finished(None) if cancelled or an exception occurs.
        """

        if self.stop_requested:
            self.finished.emit(None)
            return
        
        try:
            result = self.controller.start_acquisition(filename=self.filename)

            if self.stop_requested or result is None:
                self.finished.emit(None)
                return

            _,spectrum,_ = result
            self.finished.emit(spectrum)

        except Exception:
            self.finished.emit(None)
        finally:
            try:
                self.controller.stop_acquisition()
            except Exception:
                pass
            
       
class LiveWorker(QThread):
    """
    Background thread that continuously captures and emits live preview frames.
 
    Loops until stop() is called, invoking controller.start_live() on each
    iteration and forwarding results via frame_ready.  Emits finished when the
    loop exits and calls controller.stop_live() for cleanup.
    """
    finished = pyqtSignal()
    frame_ready = pyqtSignal(object, object)

    def __init__(self, controller):
        """
        Args:
            controller: RamanCameraController instance.
        """
        super().__init__()
        self.controller = controller
        self.running = True

    def stop(self):
        """Signal the loop to exit on its next iteration."""
        self.running = False

    def run(self):
        """
        Continuously fetch frames from the controller and emit frame_ready(frame, spectrum).
 
        Sleeps 30 ms between frames to avoid spinning the CPU.  On exit, calls
        controller.stop_live() and emits finished.
        """
        
        try:
            while self.running:
            
                result = self.controller.start_live()

                if result is None:
                    self.running = False
                    break

                combined_frame,spectrum,frame = result
                
                if frame is not None:
                    self.frame_ready.emit(frame,spectrum)

                self.msleep(30)
        except Exception as e:
            self.running = False
        finally:
            self.controller.stop_live()
            self.finished.emit()