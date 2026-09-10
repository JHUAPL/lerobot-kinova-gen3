# Kinova Gen3 cameras

The Kinova Gen3 integration supports the robot's integrated vision module and ordinary OpenCV cameras.

[Return to the Kinova Gen3 guide](README.md).

## Integrated Kinova wrist camera

The `kinova_gen3_vision` camera reads the vision module's RTSP color stream. Network transport, decoding, buffering, and the vision module itself can introduce noticeable latency. The amount of latency depends on the robot, network, camera settings, decoder, and host, and this integration does not provide a quantitative latency bound.

The integrated stream can be useful for:

- Observation and monitoring.
- Dataset collection where modest delay is acceptable.
- Workflows trained and evaluated with the same effective delay.

It may be unsuitable for responsive video-based teleoperation, fast contact-rich tasks, closed-loop policies that depend on fresh images, or safety decisions.

Configure the integrated camera explicitly:

```text
--robot.cameras='{
  "wrist": {
    "type": "kinova_gen3_vision",
    "index_or_path": "rtsp://<KINOVA_IP>/color",
    "width": 640,
    "height": 480,
    "fps": 30
  }
}'
```

## External mounted camera

For latency-sensitive work, mount a USB or other low-latency camera on the wrist or elsewhere in the workspace and configure it as an OpenCV camera. The VLA demonstration in this repository used an additional wrist-mounted webcam instead of the integrated Kinova stream.

Discover cameras on the recording host with:

```bash
lerobot-find-cameras opencv
```

Use the camera index reported on that host because indices and device paths are not portable between machines.

```text
--robot.cameras='{
  "front": {
    "type": "opencv",
    "index_or_path": <CAMERA_INDEX>,
    "width": 640,
    "height": 480,
    "fps": 30
  }
}'
```

Keep the physical mount, resolution, frame rate, orientation, and field of view consistent between dataset collection and policy evaluation.
