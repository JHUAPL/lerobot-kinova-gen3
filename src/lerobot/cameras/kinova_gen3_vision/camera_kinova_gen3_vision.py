import logging
import math
import os
import platform
import time

from kortex_api.autogen.client_stubs.DeviceManagerClientRpc import DeviceManagerClient
from kortex_api.autogen.client_stubs.VisionConfigClientRpc import VisionConfigClient
from kortex_api.autogen.messages import DeviceConfig_pb2, VisionConfig_pb2

from lerobot.errors import DeviceAlreadyConnectedError

from ..opencv.camera_opencv import OpenCVCamera
from .configuration_kinova_gen3_vision import (
    KinovaGen3VisionCameraConfig,
)

# Fix MSMF hardware transform compatibility for Windows before importing cv2
if (
    platform.system() == "Windows"
    and "OPENCV_VIDEOIO_MSMF_ENABLE_HW_TRANSFORMS" not in os.environ
):
    os.environ["OPENCV_VIDEOIO_MSMF_ENABLE_HW_TRANSFORMS"] = "0"
import cv2

MAX_OPENCV_INDEX = 60

# Attempted latency fixes
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (
    "rtsp_transport;tcp"         # or 'tcp' if you need reliability
    "|buffer_size;102400"        # 100 KB demux buffer
#    "|stimeout;5000000"          # 5 s connect timeout
#    "|rw_timeout;5000000"        # 5 s I/O timeout
    #"|probesize;32"
    #"|analyzeduration;0"
    "|fflags;nobuffer"
    "|flags;low_delay"
)

# Logging

logger = logging.getLogger(__name__)


class KinovaGen3VisionCamera(OpenCVCamera):
    def __init__(self, config: KinovaGen3VisionCameraConfig):
        super().__init__(config)
        self.vision_config: VisionConfigClient
        self.device_manager: DeviceManagerClient

    def get_vision_device_id(self):
        vision_device_id = 0

        # Getting all device routing information (from DeviceManagerClient service)
        all_devices_info = self.device_manager.ReadAllDevices()

        vision_handles = [
            hd
            for hd in all_devices_info.device_handle
            if hd.device_type == DeviceConfig_pb2.VISION
        ]
        if len(vision_handles) == 0:
            print("Error: there is no vision device registered in the devices info")
        elif len(vision_handles) > 1:
            print(
                "Error: there are more than one vision device registered in the devices info"
            )
        else:
            handle = vision_handles[0]
            vision_device_id = handle.device_identifier
            print("Vision module found, device Id: {0}".format(vision_device_id))

        return vision_device_id

    def connect(self, vision_config, device_manager, warmup: bool = True):
        if self.is_connected:
            raise DeviceAlreadyConnectedError(f"{self} is already connected.")

        self.vision_config = vision_config
        self.device_manager = device_manager  # this needs to be set to get device id

        # Set resolution
        vision_device_id = self.get_vision_device_id()

        sensor_settings = VisionConfig_pb2.SensorSettings()
        sensor_settings.sensor = VisionConfig_pb2.SENSOR_COLOR
        sensor_settings.bit_rate = VisionConfig_pb2.BITRATE_10_MBPS # options are 10, 15,20,25

        resolution_map = {
            (640, 480): VisionConfig_pb2.RESOLUTION_640x480,
            (320, 240): VisionConfig_pb2.RESOLUTION_320x240,
            (424, 240): VisionConfig_pb2.RESOLUTION_424x240,
            (480, 270): VisionConfig_pb2.RESOLUTION_480x270,
            (1280, 720): VisionConfig_pb2.RESOLUTION_1280x720,
            (1920, 1080): VisionConfig_pb2.RESOLUTION_1920x1080,
        }

        requested_resolution = (self.config.width, self.config.height)

        try:
            sensor_settings.resolution = resolution_map[requested_resolution]
        except KeyError:
            allowed = ", ".join(f"{w}×{h}" for w, h in resolution_map)
            raise ValueError(
                f"Kinova Gen3 vision camera config requires one of these resolutions: "
                f"{allowed!r}; got width={self.config.width!r}, "
                f"height={self.config.height!r}"
            ) from None

        # Set FPS
        fps_map = {
            6: VisionConfig_pb2.FRAMERATE_6_FPS,
            15: VisionConfig_pb2.FRAMERATE_15_FPS,
            30: VisionConfig_pb2.FRAMERATE_30_FPS,
        }

        requested_fps = self.config.fps

        try:
            sensor_settings.frame_rate = fps_map[requested_fps]
        except KeyError:
            allowed_fps = ", ".join(str(f) for f in fps_map)
            raise ValueError(
                f"Kinova Gen3 vision camera config requires one of these FPS values: "
                f"{allowed_fps!r}; got fps={requested_fps!r}"
            ) from None

        self.vision_config.SetSensorSettings(sensor_settings, vision_device_id)

        # TODO: Set focus and/or disable auto-focus

        # Pause continuous focus
        sensor_focus_action = VisionConfig_pb2.SensorFocusAction()
        sensor_focus_action.sensor = VisionConfig_pb2.SENSOR_COLOR
        sensor_focus_action.focus_action = VisionConfig_pb2.FOCUSACTION_PAUSE_CONTINUOUS_FOCUS
        vision_config.DoSensorFocusAction(sensor_focus_action, vision_device_id)

        #time.sleep(1)

        # Set focus
        #sensor_focus_action = VisionConfig_pb2.SensorFocusAction()
        #sensor_focus_action.sensor = VisionConfig_pb2.SENSOR_COLOR
        #sensor_focus_action.focus_action = VisionConfig_pb2.FOCUSACTION_SET_MANUAL_FOCUS
        #sensor_focus_action.manual_focus.value = 350
        #self.vision_config.DoSensorFocusAction(sensor_focus_action, vision_device_id)

        # Turn off focus (requires testing, this might be extraneous)
        #sensor_focus_action = VisionConfig_pb2.SensorFocusAction()
        #sensor_focus_action.sensor = VisionConfig_pb2.SENSOR_COLOR
        #sensor_focus_action.focus_action = VisionConfig_pb2.FOCUSACTION_DISABLE_FOCUS
        #vision_config.DoSensorFocusAction(sensor_focus_action, vision_device_id)
        # Use 1 thread for OpenCV operations to avoid potential conflicts or
        # blocking in multi-threaded applications, especially during data collection.

        time.sleep(2)  # Give time to let configurations send
        cv2.setNumThreads(1)

        #self.videocapture = cv2.VideoCapture(self.index_or_path, self.backend)
        self.videocapture = cv2.VideoCapture(self.index_or_path, cv2.CAP_FFMPEG)
        #print(cv2.getBuildInformation)
        # TODO Get gstreamer working to see if fixes latency issues
        #gst = (
        #    f"rtspsrc location={self.index_or_path} latency=0 drop-on-latency=true protocols=udp ! "
        #    "rtpjitterbuffer mode=0 drop-on-late=true ! "
        #    "rtph264depay ! h264parse config-interval=-1 ! avdec_h264 ! "
        #    "videoconvert ! appsink sync=false max-buffers=1 drop=true"
        #)
        #cap = cv2.VideoCapture(gst, cv2.CAP_GSTREAMER)

        #print(f"Backend chosen was {self.videocapture.getBackendName()}")

        if not self.videocapture.isOpened():
            self.videocapture.release()
            self.videocapture = None
            raise ConnectionError(
                f"Failed to open {self}.Run `lerobot-find-cameras opencv` to find available cameras."
            )

        self._configure_capture_settings()

        if warmup:
            start_time = time.time()
            while time.time() - start_time < self.warmup_s:
                self.read()
                time.sleep(0.1)

        logger.info(f"{self} connected.")

    def _validate_width_and_height(self) -> None:
        """Validates and sets the camera's frame capture width and height."""

        actual_width = int(round(self.videocapture.get(cv2.CAP_PROP_FRAME_WIDTH)))
        if self.capture_width != actual_width:
            raise RuntimeError(
                f"{self} failed to set capture_width={self.capture_width} ({actual_width=})."
            )

        actual_height = int(round(self.videocapture.get(cv2.CAP_PROP_FRAME_HEIGHT)))
        if self.capture_height != actual_height:
            raise RuntimeError(
                f"{self} failed to set capture_height={self.capture_height} ({actual_height=})."
            )

    def _validate_fps(self) -> None:
        """Validates and sets the camera's frames per second (FPS)."""

        actual_fps = self.videocapture.get(cv2.CAP_PROP_FPS)
        # Use math.isclose for robust float comparison
        # Note using huge rel tolerance, since kinova camera doesn't seem to reliably output at 30 FPS but 15 FPS is just too slow
        if not math.isclose(self.fps, actual_fps, rel_tol=5):
            raise RuntimeError(f"{self} failed to set fps={self.fps} ({actual_fps=}).")
