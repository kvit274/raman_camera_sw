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
            frame,spectrum = self.controller.start_acquisition()
            self.finished.emit(frame,spectrum)
        except:
            # self.camera_lost.emit()
            pass