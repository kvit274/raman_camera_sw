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
    finished = pyqtSignal(object,object)

    def __init__(self, controller):
        super().__init__()
        self.controller = controller

    def run(self):
        try:
            combined_frame,spectrum,frame = self.controller.start_acquisition()
            self.finished.emit(frame,spectrum)
        except:
            # self.camera_lost.emit()
            pass

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
        
        while self.running:
            try:
                combined_frame,spectrum,frame = self.controller.start_live()
            except Exception:
                break
            
            if frame is not None:
                self.frame_ready.emit(frame,spectrum)

        self.finished.emit()