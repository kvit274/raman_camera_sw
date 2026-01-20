from PyQt5.QtCore import QThread, pyqtSignal

class CoolingWorker(QThread):
    finished = pyqtSignal()

    def __init__(self, camera, target_temp:float=-70.0):
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