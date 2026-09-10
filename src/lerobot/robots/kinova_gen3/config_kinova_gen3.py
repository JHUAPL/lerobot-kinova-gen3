from dataclasses import dataclass, field
from pathlib import Path

from lerobot.cameras import CameraConfig
from lerobot.cameras.kinova_gen3_vision.configuration_kinova_gen3_vision import (
    KinovaGen3VisionCameraConfig,
)
from lerobot.cameras.opencv import OpenCVCameraConfig

from ..config import RobotConfig


@RobotConfig.register_subclass("kinova_gen3")
@dataclass
class KinovaGen3Config(RobotConfig):
    ip: str = "192.168.1.10"
    port: int = 10000

    # No-op mode to allow recording with dummy teleop values
    no_op: bool = False

    # Allows to distinguish between different robots of the same type
    id: str | None = "kinova_gen3"
    # Directory to store calibration file
    calibration_dir: Path | None = None

    kinova_user: str = "admin"
    kinova_pwd: str = "admin"
    session_inactivity_timeout: float = 10000  # in ms
    connection_inactivity_timeout: float = 2000  # in ms

    # Maximum allowed waiting time during actions (in seconds)
    action_timeout_duration: float = 20

    # Actuator speed (deg/s)
    speed: float = 20.0

    cameras: dict[str, CameraConfig] = field(
        default_factory=lambda: {
            "wrist": KinovaGen3VisionCameraConfig(
                index_or_path="rtsp://192.168.1.10/color",
                fps=30,
                width=640,
                height=480,
            ),
            "top": OpenCVCameraConfig(
                index_or_path="/dev0/video0",
                fps=30,
                width=640,
                height=480,
            ),
        }
    )
