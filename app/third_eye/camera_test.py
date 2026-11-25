"""
Camera checker. Run:   py -3.12 camera_test.py

It tries camera numbers 0-4 with every camera driver, saves a test photo from each one
that works (camera_test_0.jpg, ...), and tells you what to try if none work.
Close the Third Eye app (and Zoom/Teams/Camera) first: only one app can use a camera at a time.
"""
import platform
import time

import cv2

from main import camera_backends


def check(index, name, api):
    start = time.time()
    cap = cv2.VideoCapture(index, api)
    if not cap.isOpened():
        cap.release()
        return "not found", None
    frame = None
    while time.time() - start < 5:
        ok, f = cap.read()
        if ok and f is not None and f.size:
            frame = f
            break
        time.sleep(0.1)
    cap.release()
    if frame is None:
        return "found, but it sent no picture", None
    if frame.mean() < 3:
        return "picture is completely black (privacy shutter / camera key / privacy setting?)", frame
    return f"WORKS ({frame.shape[1]}x{frame.shape[0]}, took {time.time() - start:.1f}s)", frame


def main():
    print(f"OpenCV {cv2.__version__} on {platform.system()} {platform.release()}\n")
    working = []
    for i in range(5):
        for name, api in camera_backends():
            result, frame = check(i, name, api)
            if result == "not found":
                continue
            print(f"Camera {i} with {name:<16}: {result}")
            if result.startswith("WORKS"):
                cv2.imwrite(f"camera_test_{i}.jpg", frame)
                working.append(i)
                break
    print()
    if working:
        cams = ", ".join(str(i) for i in sorted(set(working)))
        print(f"Working camera(s): {cams}. Test photos saved as camera_test_<number>.jpg in this folder.")
        print(f"In the app, pick that camera in the menu, or start it with:  py -3.12 main.py --camera {working[0]}")
        print("Tip: if a photo looks grey/dark and grainy, that's the Windows Hello face-login (infrared)")
        print("     camera. Pick the other number.")
    else:
        print("No camera gave a picture. Try these, then run this test again:")
        print("  1. Close Zoom, Teams, Discord, OBS, the Camera app and any browser tab using the camera.")
        if platform.system() == "Windows":
            print("  2. Settings > Privacy & security > Camera: turn ON 'Camera access',")
            print("     'Let apps access your camera' AND 'Let desktop apps access your camera'.")
            print("  3. Open the Windows Camera app. If it shows no picture either, the problem is the camera itself:")
            print("     check for a privacy shutter or a camera on/off key (often F8 or F10).")
            print("  4. Device Manager > Cameras: if the camera has a warning icon or is missing,")
            print("     right-click > Uninstall device, then restart the laptop.")
        else:
            print("  2. System Settings > Privacy & Security > Camera: allow Terminal (or VS Code).")
        print("  5. USB camera: try another USB port, and avoid USB hubs.")


if __name__ == "__main__":
    main()
