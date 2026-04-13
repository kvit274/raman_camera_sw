from dataclasses import dataclass, field
from copy import deepcopy
from typing import Optional


@dataclass
class CameraConfig:
    """
    Immutable value object that holds a complete snapshot of camera settings.
 
    All mutable fields (dicts) are stored by value so that callers cannot
    accidentally mutate the stored config through external references.
 
    Attributes:
        shutter:          Dict describing shutter parameters (mode, ttl_mode,
                          open_time, close_time).
        read_mode:        Dict describing the active read mode and its parameters
                          (e.g. hstart/hend/vstart/vend for image mode).
        acquisition_mode: Dict describing the acquisition mode and its parameters
                          (e.g. num_acc for accum mode).
        trigger_mode:     Trigger mode string (e.g. 'int', 'ext').
        exposure:         Exposure time as a string representation of a float (seconds).
        amp:              Dict describing amplifier settings (channel, oamp, hsspeed,
                          preamp).
        vsspeed:          Vertical shift speed index, or None if not set.
        emccd_gain:       Dict with keys 'emccd_gain' and 'emccd_advanced'.
    """
    shutter: dict = field(default_factory=dict)
    read_mode: dict = field(default_factory=dict)
    acquisition_mode: dict = field(default_factory=dict)
    trigger_mode: str = ""
    exposure: str = ""
    amp: dict = field(default_factory=dict)
    vsspeed: Optional[int] = None
    emccd_gain: dict = field(default_factory=dict)

    def to_dict(self):
        """
        Serialise the config to a plain dict with deep-copied mutable values.
 
        Returns:
            Dict representation of all config fields, safe to mutate independently.
        """
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
    """
    Mutable store for the active CameraConfig.
 
    Acts as the single source of truth for camera settings within the application.
    All reads and writes go through deep-copy operations to ensure the stored config
    is never accidentally shared by reference.
    """
    def __init__(self):
        """Initialise with a default (empty) CameraConfig."""
        self._config = CameraConfig()

    def set_config(self, config: CameraConfig):
        """
        Replace the stored config with a deep copy of the supplied CameraConfig.
 
        Args:
            config: A CameraConfig instance to store.
        """
        self._config = deepcopy(config)

    def get_config(self) -> CameraConfig:
        """
        Return a deep copy of the currently stored CameraConfig.
 
        Returns:
            CameraConfig instance (safe to mutate without affecting the stored copy).
        """
        return deepcopy(self._config)

    def update_from_dict(self, data: dict):
        """
        Overwrite the stored config by parsing a plain settings dict.
 
        Expected keys match the fields of CameraConfig (shutter, read_mode,
        acquisition_mode, trigger_mode, exposure, amp, vsspeed, emccd_gain).
        Missing keys fall back to empty dicts / empty strings / None.
 
        Args:
            data: Dict produced by CameraConfig.to_dict() or equivalent.
        """
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
        """
        Return the stored config as a plain dict (via CameraConfig.to_dict).
 
        Returns:
            Dict with deep-copied values, safe to mutate independently.
        """
        return self._config.to_dict()