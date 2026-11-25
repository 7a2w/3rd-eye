"""Build sample lecture data for testing Third Eye on a machine with no mic or camera.

Needs: pip install piper-tts pillow numpy opencv-python-headless, ffmpeg on PATH, and in $TE_VOICES
(default /tmp/te/voices): en_US-lessac-medium.onnx(.json) from `python -m piper.download_voices en_US-lessac-medium`
and PatrickHand-Regular.ttf (Google Fonts) for the whiteboard. Falls back to Liberation Sans without it.

Outputs in $TE_SAMPLES (default /tmp/te/samples):
  lecture.wav / lecture.mp3   spoken lecture (Piper TTS + light room noise)
  lecture_slides.mp4          projector-screen video with slide changes, with the lecture audio muxed in
  lecture_silent.mp4          same video without audio
  whiteboard_1.jpg, whiteboard_2.jpg   photos of a whiteboard
  question_1.wav, question_2.wav       spoken questions
  timings.json                section start times
"""
import json
import os
import subprocess
import wave
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from piper import PiperVoice

OUT = Path(os.environ.get("TE_SAMPLES", "/tmp/te/samples"))
OUT.mkdir(parents=True, exist_ok=True)
VOICES = Path(os.environ.get("TE_VOICES", "/tmp/te/voices"))
VOICE = PiperVoice.load(str(VOICES / "en_US-lessac-medium.onnx"))
SR = VOICE.config.sample_rate
FPS = 15
W, H = 1280, 720

SECTIONS = [
    {
        "slide": ("BIOL 1010  |  Lecture 14", ["Cellular Respiration, Part 2", "", "Glycolysis, the Krebs cycle,", "and the electron transport chain"], True),
        "say": "Okay, let's get started. Last time we looked at why cells need ATP. Today we are going to follow one "
               "molecule of glucose all the way through cellular respiration, and see where the energy actually comes from.",
    },
    {
        "slide": ("Glycolysis", ["Happens in the cytoplasm", "No oxygen needed", "1 glucose (6C) -> 2 pyruvate (3C)",
                                 "Uses 2 ATP, makes 4 ATP", "Net gain: 2 ATP and 2 NADH"], False),
        "say": "The first stage is glycolysis. Glycolysis happens in the cytoplasm, and it does not need any oxygen. "
               "One glucose molecule, which has six carbons, gets split into two molecules of pyruvate, which have three "
               "carbons each. The cell spends two ATP to get it started and makes four, so the net gain is two ATP, plus two NADH.",
    },
    {
        "slide": ("Krebs cycle (citric acid cycle)", ["Takes place in the mitochondrial matrix", "Pyruvate -> acetyl CoA + CO2",
                                                      "Per glucose: 2 ATP, 6 NADH, 2 FADH2", "Most of the carbon leaves as CO2"], False),
        "say": "Next, the pyruvate moves into the mitochondria. In the mitochondrial matrix, each pyruvate is turned into "
               "acetyl CoA, and that releases carbon dioxide. Acetyl CoA then enters the Krebs cycle, which is also called "
               "the citric acid cycle. For every glucose, the cycle makes two ATP, six NADH and two FADH2. This is where most "
               "of the carbon from glucose leaves, as the carbon dioxide you breathe out.",
    },
    {
        "slide": ("Electron transport chain", ["Inner mitochondrial membrane", "NADH and FADH2 give up electrons",
                                               "Proton gradient drives ATP synthase", "O2 is the final electron acceptor",
                                               "About 32 ATP per glucose"], False),
        "say": "The last stage is the electron transport chain, on the inner mitochondrial membrane. NADH and FADH2 hand "
               "their electrons to the chain, and as the electrons move down the chain, protons get pumped across the membrane. "
               "That builds up a proton gradient, and the protons flow back through ATP synthase, which makes most of the ATP. "
               "Oxygen is the final electron acceptor. It picks up the electrons and combines with hydrogen to make water. "
               "Altogether you get about thirty two ATP per glucose. This part will be on the exam, so make sure you can "
               "explain why we need oxygen.",
    },
    {
        "slide": ("No oxygen? Fermentation", ["Glycolysis keeps going", "NADH is recycled back to NAD+",
                                              "Muscle cells: lactic acid", "Yeast: ethanol and CO2", "Only 2 ATP per glucose"], False),
        "say": "So what happens when there is not enough oxygen, like in your leg muscles during a sprint? The electron "
               "transport chain backs up, so the cell switches to fermentation. Fermentation recycles NADH back into NAD plus, "
               "so glycolysis can keep going. In muscle cells the product is lactic acid. In yeast it is ethanol and carbon "
               "dioxide. Either way, you only get two ATP per glucose.",
    },
    {
        "slide": ("Before next class", ["Read chapter 9 (pages 160-178)", "Problem set 4 due Friday, 11:59 pm",
                                        "Yeast fermentation lab report due next Wednesday", "Midterm in two weeks: chapters 6 to 9"], False),
        "say": "Before you go, a few reminders. Please read chapter nine before next class. Problem set four is due this "
               "Friday at midnight on the course site. The lab report for the yeast fermentation lab is due next Wednesday. "
               "And the midterm is two weeks from today. It covers chapters six to nine. Okay, that is it for today. "
               "See you on Thursday.",
    },
]

QUESTIONS = ["What is the final electron acceptor?", "Where does glycolysis happen?"]


def tts(text: str) -> np.ndarray:
    chunks = [c.audio_float_array for c in VOICE.synthesize(text)]
    return np.concatenate(chunks).astype(np.float32)


def write_wav(path: Path, audio: np.ndarray, sr: int):
    pcm = (np.clip(audio, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())


def font(size, bold=False):
    name = "LiberationSans-Bold.ttf" if bold else "LiberationSans-Regular.ttf"
    return ImageFont.truetype(f"/usr/share/fonts/truetype/liberation/{name}", size)


def render_slide(title, lines, is_title):
    img = Image.new("RGB", (1024, 576), (250, 250, 247))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 1024, 18], fill=(122, 23, 36))
    if is_title:
        d.text((70, 120), title, font=font(30), fill=(90, 90, 90))
        y = 190
        for i, ln in enumerate(lines):
            d.text((70, y), ln, font=font(56 if i == 0 else 34, bold=(i == 0)), fill=(25, 25, 25))
            y += 80 if i == 0 else 48
    else:
        d.text((60, 52), title, font=font(52, bold=True), fill=(25, 25, 25))
        d.line([60, 128, 964, 128], fill=(122, 23, 36), width=3)
        y = 160
        for ln in lines:
            d.ellipse([66, y + 16, 78, y + 28], fill=(122, 23, 36))
            d.text((98, y), ln, font=font(36), fill=(30, 30, 30))
            y += 66
    d.text((900, 540), "BIOL 1010", font=font(18), fill=(140, 140, 140))
    return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)


def room_background():
    y = np.linspace(0, 1, H)[:, None]
    x = np.linspace(-1, 1, W)[None, :]
    base = 46 - 18 * y - 10 * x ** 2
    bg = np.dstack([base * 0.95, base, base * 1.05]).clip(0, 255).astype(np.uint8)
    cv2.rectangle(bg, (0, 610), (W, H), (34, 30, 28), -1)
    return bg


def on_screen(slide, bg):
    src = np.float32([[0, 0], [1024, 0], [1024, 576], [0, 576]])
    dst = np.float32([[168, 70], [1122, 92], [1104, 628], [184, 646]])
    M = cv2.getPerspectiveTransform(src, dst)
    warped = cv2.warpPerspective(slide, M, (W, H))
    mask = cv2.warpPerspective(np.full((576, 1024), 255, np.uint8), M, (W, H))
    frame = bg.copy()
    frame[mask > 0] = warped[mask > 0]
    # projector hot spot + camera softness
    yy, xx = np.mgrid[0:H, 0:W]
    spot = 1.0 - 0.18 * (((xx - 640) / 640) ** 2 + ((yy - 340) / 360) ** 2)
    frame = (frame.astype(np.float32) * spot[..., None]).clip(0, 255).astype(np.uint8)
    return cv2.GaussianBlur(frame, (3, 3), 0.8)


def whiteboard(lines, path, angle):
    fpath = VOICES / "PatrickHand-Regular.ttf"
    try:
        f = ImageFont.truetype(str(fpath), 70)
    except OSError:
        f = font(60)
    img = Image.new("RGB", (1600, 1000), (236, 238, 235))
    d = ImageDraw.Draw(img)
    colors = [(30, 60, 160), (20, 20, 20), (160, 30, 30), (20, 110, 50)]
    y = 110
    for i, ln in enumerate(lines):
        d.text((120, y), ln, font=f, fill=colors[i % len(colors)])
        y += 130
    arr = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR).astype(np.float32)
    yy, xx = np.mgrid[0:1000, 0:1600]
    shade = 1.0 - 0.22 * ((xx / 1600) ** 1.5) - 0.08 * (yy / 1000)
    arr = (arr * shade[..., None])
    arr += np.random.default_rng(1).normal(0, 3, arr.shape)
    arr = arr.clip(0, 255).astype(np.uint8)
    M = cv2.getRotationMatrix2D((800, 500), angle, 1.0)
    arr = cv2.warpAffine(arr, M, (1600, 1000), borderValue=(60, 60, 60))
    cv2.imwrite(str(path), cv2.resize(arr, (1200, 750)), [cv2.IMWRITE_JPEG_QUALITY, 88])


def main():
    rng = np.random.default_rng(7)
    pieces, timings, t = [], [], 0.0
    lead = np.zeros(int(SR * 1.5), np.float32)
    pieces.append(lead)
    t += len(lead) / SR
    for sec in SECTIONS:
        speech = tts(sec["say"])
        timings.append({"start": round(t, 2), "title": sec["slide"][0]})
        gap = np.zeros(int(SR * 2.0), np.float32)
        pieces += [speech, gap]
        t += (len(speech) + len(gap)) / SR
    audio = np.concatenate(pieces)
    audio = audio * 0.8 + rng.normal(0, 0.0025, len(audio)).astype(np.float32)   # room noise
    write_wav(OUT / "lecture.wav", audio, SR)
    duration = len(audio) / SR
    (OUT / "timings.json").write_text(json.dumps({"duration": duration, "sections": timings}, indent=2))

    bg = room_background()
    frames_dir = OUT / "frames"
    frames_dir.mkdir(exist_ok=True)
    slides = [on_screen(render_slide(*s["slide"]), bg) for s in SECTIONS]
    n = int(duration * FPS)
    writer = cv2.VideoWriter(str(OUT / "raw.avi"), cv2.VideoWriter_fourcc(*"MJPG"), FPS, (W, H))
    starts = [s["start"] - 0.6 for s in timings]   # slide goes up just before the professor talks about it
    for i in range(n):
        ts = i / FPS
        k = max(j for j in range(len(starts)) if starts[j] <= ts or j == 0)
        frame = slides[k].astype(np.int16) + rng.normal(0, 2.0, (H, W, 1)).astype(np.int16)
        writer.write(frame.clip(0, 255).astype(np.uint8))
    writer.release()
    for i, s in enumerate(slides):
        cv2.imwrite(str(OUT / f"slide_ref_{i + 1}.png"), s)

    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(OUT / "raw.avi"), "-i", str(OUT / "lecture.wav"),
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "26", "-preset", "veryfast",
                    "-c:a", "aac", "-b:a", "96k", "-shortest", "-movflags", "+faststart", str(OUT / "lecture_slides.mp4")], check=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(OUT / "raw.avi"), "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-crf", "26", "-preset", "veryfast", "-an", str(OUT / "lecture_silent.mp4")], check=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(OUT / "lecture.wav"), "-b:a", "96k", str(OUT / "lecture.mp3")], check=True)
    (OUT / "raw.avi").unlink()
    frames_dir.rmdir()

    whiteboard(["Glycolysis: glucose (6C) -> 2 pyruvate", "Net: 2 ATP + 2 NADH", "ETC: O2 = final e- acceptor"],
               OUT / "whiteboard_1.jpg", 1.5)
    whiteboard(["Midterm: two weeks from today", "Chapters 6 to 9", "Bring a calculator"], OUT / "whiteboard_2.jpg", -1.0)

    for i, q in enumerate(QUESTIONS, 1):
        qa = np.concatenate([np.zeros(int(SR * 0.4), np.float32), tts(q), np.zeros(int(SR * 0.6), np.float32)])
        write_wav(OUT / f"question_{i}.wav", qa * 0.9, SR)
    print(f"lecture: {duration:.1f} s, {len(timings)} sections")
    print(json.dumps(timings, indent=1))


if __name__ == "__main__":
    main()
