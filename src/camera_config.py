from dataclasses import dataclass, field
from copy import deepcopy


@dataclass
class CameraConfig:
    shutter: dict = field(default_factory=dict)
    read_mode: dict = field(default_factory=dict)
    acquisition_mode: dict = field(default_factory=dict)
    trigger_mode: str = ""
    exposure: str = ""
    amp: dict = field(default_factory=dict)
    vsspeed: int | None = None
    emccd_gain: dict = field(default_factory=dict)

    def to_dict(self):
        return {
            "shutter": deepcopy(self.shutter),
            "read_mode": deepcopy(self.read_mode),
            "acquisition_mode": deepcopy(self.acquisition_mode),
            "trigger_mode": self.trigger_mode,
            "exposure": self.exposure,
            "amp": deepcopy(self.amp),
            "vsspeed": self.vsspeed,
            "emccd_gain": deepcopy(self.emccd_gain),
        }


class CameraConfigModel:
    def __init__(self):
        self._config = CameraConfig()

    def set_config(self, config: CameraConfig):
        self._config = deepcopy(config)

    def get_config(self) -> CameraConfig:
        return deepcopy(self._config)

    def update_from_dict(self, data: dict):
        self._config = CameraConfig(
            shutter=deepcopy(data.get("shutter", {})),
            read_mode=deepcopy(data.get("read_mode", {})),
            acquisition_mode=deepcopy(data.get("acquisition_mode", {})),
            trigger_mode=data.get("trigger_mode", ""),
            exposure=data.get("exposure", ""),
            amp=deepcopy(data.get("amp", {})),
            vsspeed=data.get("vsspeed"),
            emccd_gain=deepcopy(data.get("emccd_gain", {})),
        )

    def as_dict(self) -> dict:
        return self._config.to_dict()