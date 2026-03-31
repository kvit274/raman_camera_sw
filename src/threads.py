from PyQt5.QtCore import QThread, pyqtSignal

class CoolingWorker(QThread):
    finished = pyqtSignal()

    def __init__(self, camera, target_temp:float=-85.0):
        super().__init__()
        self.camera = camera
        self.target_temp = target_temp

    def run(self):
        self.camera.cool_cam(self.target_temp)
        self.finished.emit()    # unlock buttons

class WarmUpCloseWorker(QThread):
    finished = pyqtSignal()

    def __init__(self, camera, target_temp:float=20.0):
        super().__init__()
        self.camera = camera
        self.target_temp = target_temp

    # think about this
    def run(self):
        self.camera.warm_cam(self.target_temp)
        self.camera.safe_close()
        self.finished.emit()

# TOD0!!
# class AcquisitionStatusWorker(QThread):
#     finished = pyqtSignal()

#     def __init__(self, camera):
#         super().__init__()
#         self.camera = camera

#     def run(self):
#         self.camera.wait_for_frame()
#         self.camera.safe_close()
#         self.finished.emit()

class AcquisitionWorker(QThread):
    finished = pyqtSignal(object)

    def __init__(self, controller, filename=None):
        super().__init__()
        self.controller = controller
        self.filename = filename
        self.stop_requested = False

    def stop(self):
        self.stop_requested = True
        self.controller.stop_acquisition()

    def run(self):

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
            self.controller.stop_acquisition()
            
       
class LiveWorker(QThread):
    finished = pyqtSignal()
    frame_ready = pyqtSignal(object, object)

    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.running = True

    def stop(self):
        self.running = False

    def run(self):
        
        try:
            while self.running:
            
                result = self.controller.start_live()

                if result is None:
                    self.running = False
                    break

                combined_frame,spectrum,frame = result
                
                if frame is not None:
                    self.frame_ready.emit(frame,spectrum)

                self.msleep(30)  # avoid cpu spinning
        except Exception as e:
            self.running = False
        finally:
            self.controller.stop_live()
            self.finished.emit()