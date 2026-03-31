from enum import Enum, auto
from PyQt5.QtCore import QObject, pyqtSignal


class CameraState(Enum):
    DISCONNECTED = auto()
    CONNECTED = auto()
    COOLING = auto()
    READY = auto()
    LIVE = auto()
    ACQUIRING = auto()
    ERROR = auto()


class CameraStateMachine(QObject):
    state_changed = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self._state = CameraState.DISCONNECTED

        self._allowed_actions = {
            CameraState.DISCONNECTED: {"connect"},
            CameraState.CONNECTED: {"start_cooling", "disconnect"},
            CameraState.COOLING: {"cooling_done", "cooling_failed", "disconnect"},
            CameraState.READY: {
                "start_live",
                "stop_live",
                "preview",
                "start_acquisition",
                "stop_acquisition",
                "apply_settings",
                "disconnect",
                "start_cooling",
            },
            CameraState.LIVE: {"stop_live", "disconnect"},
            CameraState.ACQUIRING: {"stop_acquisition", "disconnect"},
            CameraState.ERROR: {"disconnect", "reset"},
        }

    @property
    def state(self):
        return self._state

    def can(self, action: str) -> bool:
        return action in self._allowed_actions.get(self._state, set())

    def require(self, action: str):
        if not self.can(action):
            raise RuntimeError(
                f"Action '{action}' is not allowed in state {self._state.name}"
            )

    def set_state(self, new_state: CameraState):
        if self._state != new_state:
            self._state = new_state
            self.state_changed.emit(new_state)

    def get_state(self):
        return self._state