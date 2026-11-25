"""
Recording light.

On the laptop it is a red "REC" dot drawn on the camera window.
On a Raspberry Pi (Option B) it also drives a real LED on GPIO 17, if gpiozero is installed.
The light is controlled in ONE place, so it can never disagree with whether we are recording.
"""
import time

try:  # only exists on a Raspberry Pi
    from gpiozero import LED  # type: ignore
    _led = LED(17)
except Exception:
    _led = None


class RecordingIndicator:
    def __init__(self):
        self.recording = False
        self.mode = "OFF"          # "REC", "ASK", "PAUSED", "OFF"

    def set(self, mode: str):
        self.mode = mode
        self.recording = mode in ("REC", "ASK")
        if _led is not None:
            _led.on() if self.recording else _led.off()

    def draw(self, frame):
        """Draw the indicator onto an OpenCV frame (BGR numpy array)."""
        import cv2
        colors = {"REC": (0, 0, 255), "ASK": (255, 160, 0), "PAUSED": (128, 128, 128), "OFF": (80, 80, 80)}
        labels = {"REC": "REC", "ASK": "LISTENING TO YOU", "PAUSED": "PAUSED (privacy)", "OFF": "OFF"}
        color = colors.get(self.mode, (80, 80, 80))
        # blink the dot once per second while recording, like a real camera light
        show_dot = not self.recording or int(time.time() * 2) % 2 == 0 or self.mode == "ASK"
        if show_dot:
            cv2.circle(frame, (30, 30), 12, color, -1)
        cv2.putText(frame, labels.get(self.mode, ""), (50, 38),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2, cv2.LINE_AA)
        return frame
