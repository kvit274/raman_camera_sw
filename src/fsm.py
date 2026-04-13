from enum import Enum, auto
from PyQt5.QtCore import QObject, pyqtSignal


class CameraState(Enum):
    """
    Enumeration of all valid camera lifecycle states.
 
    DISCONNECTED  – No camera is connected.
    CONNECTED     – Camera is connected but not yet cooled to operating temperature.
    COOLING       – The camera is actively cooling down.
    READY         – Camera is cooled and settings are applied; ready for acquisition.
    LIVE          – Continuous live-preview frames are being captured.
    ACQUIRING     – A save acquisition is in progress.
    ERROR         – An unrecoverable error has occurred.
    """
    DISCONNECTED = auto()
    CONNECTED = auto()
    COOLING = auto()
    READY = auto()
    LIVE = auto()
    ACQUIRING = auto()
    ERROR = auto()


class CameraStateMachine(QObject):
    """
    Finite-state machine that enforces valid camera state transitions.
 
    Emits state_changed whenever the active state changes, allowing the UI
    to react by enabling or disabling the appropriate controls.
    """
    state_changed = pyqtSignal(object)

    def __init__(self):
        """
        Initialise the FSM in the DISCONNECTED state and define the allowed
        actions for each state.
        """
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
            CameraState.LIVE: {"stop_live", "disconnect","start_live"},
            CameraState.ACQUIRING: {"stop_acquisition", "disconnect"},
            CameraState.ERROR: {"disconnect", "reset"},
        }

    @property
    def state(self):
        """Return the current CameraState (read-only property)."""
        return self._state

    def can(self, action: str) -> bool:
        """
        Check whether an action is permitted in the current state.
 
        Args:
            action: Action name string (e.g. 'connect', 'start_live').
 
        Returns:
            True if the action is allowed, False otherwise.
        """
        return action in self._allowed_actions.get(self._state, set())

    def require(self, action: str):
        """
        Assert that an action is permitted, raising if it is not.
 
        Args:
            action: Action name string to validate.
 
        Raises:
            RuntimeError: If the action is not allowed in the current state.
        """
        if not self.can(action):
            raise RuntimeError(
                f"Action '{action}' is not allowed in state {self._state.name}"
            )

    def set_state(self, new_state: CameraState):
        """
        Transition to a new state and emit state_changed if the state differs.
 
        Args:
            new_state: Target CameraState to transition into.
        """
        if self._state != new_state:
            self._state = new_state
            self.state_changed.emit(new_state)

    def get_state(self):
        """
        Return the current CameraState.
 
        Returns:
            The active CameraState enum value.
        """
        return self._state