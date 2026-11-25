# Third Eye test harness

Runs the Third Eye laptop app end to end on a machine with no webcam, mic or speakers (an Ubuntu 24.04 VM, Python 3.12), using recorded sample inputs. Nothing in here goes into the app folder or the zip.

## What's here

- `drive.py` starts `main.py` and clicks through the dashboard's HTTP API the way a user would. It goes setup, start, pause/resume, voice question, recorded lecture, typed question, end lecture, file downloads, a question after the lecture, new lecture, rescan/camera/mic, then quit. It only uses the standard library, so any `python3` can run it. It writes `events.txt`, `app.log` and the `/state` JSON at setup, recording and done into the output folder, and the lecture notes into `OUT/notes/`.
- `make_samples.py` rebuilds `samples/`. You only need it if you want to change the lecture. It needs Piper TTS; see the top of the file.
- `stubs/google/colab/` is a stand-in for `google.colab` (files, drive, userdata, output) so the Colab notebook can run outside Colab. See its `__init__.py` for the env vars.
- `samples/` holds the sample inputs:
  - `lecture.wav` and `lecture.mp3`: a 146 s BIOL 1010 lecture on cellular respiration read by a TTS voice, with light room noise. It mentions homework and a midterm, so the study sheet gets to-dos.
  - `lecture_slides.mp4`: a 1280x720, 15 fps camera view of a projector screen with the same audio. There are six slide changes; `timings.json` has when each one starts.
  - `lecture_silent.mp4`: the same video with no audio.
  - `whiteboard_1.jpg` and `whiteboard_2.jpg`: phone photos of a whiteboard, for `colab_helpers.add_slide_photos`.
  - `question_1.wav` ("What is the final electron acceptor?") and `question_2.wav` ("Where does glycolysis happen?"): spoken questions.
  - `slide_ref_1..6.png`: one clean frame per slide, for checking OCR and slide detection.

## Setup (once per VM)

```bash
sudo apt-get update
sudo apt-get install -y python3.12-venv libportaudio2 tesseract-ocr espeak-ng ffmpeg
# libportaudio2: without it `import sounddevice` fails on Linux and the app silently has no mic
# tesseract-ocr: slide text (OCR); espeak-ng: spoken answers; ffmpeg: only for make_samples.py

H=/cursor/stores/bc-2da190a9-e638-48a0-8dcb-770e6fdc201d/internal/third-eye-work/harness
mkdir -p /tmp/te && cd /tmp/te
unzip -q /cursor/stores/bc-2da190a9-e638-48a0-8dcb-770e6fdc201d/internal/uploads/third_eye.zip -d orig
python3 -m venv venv && . venv/bin/activate
pip install -U pip
pip install -r orig/third_eye/requirements.txt
pip install "av==18.1.1"
```

Pin `av==18.1.1`. The original `requirements.txt` is unpinned, so it now installs PyAV 19, and faster-whisper 1.2.1 still calls `av.open(..., metadata_errors="ignore")`, which PyAV 19 removed. Any audio file input then fails: `--audio-file` shows `[audio] open() got an unexpected keyword argument 'metadata_errors'`, `/api/start` returns `{"ok": false}`, and the notebook's transcribe cell fails too. PyAV 16.1 to 18.1.1 work.

The first run downloads the faster-whisper `base.en` model (about 140 MB) from Hugging Face into `~/.cache/huggingface`.

## Run the original app on the samples

```bash
cd /tmp/te
TE_SKIP_VOICE_ASK=1 python $H/test/drive.py /tmp/te/orig/third_eye /tmp/te/venv/bin/python /tmp/te/runs/orig \
    --audio-file $H/samples/lecture.wav --mute --no-camera
```

It takes about 3.5 minutes, because the lecture plays in real time. The arguments after the output folder go straight to `main.py`, and the driver always adds `--no-browser --port 8010`. Notes go to `OUT/notes/` because the driver sets `THIRD_EYE_SYNC`. If you have no API key the app runs offline, so answers come from transcript search and the study sheet is the offline version.

To test your rewritten files, copy the original folder, drop your files in, and run the same command with a different output folder. Then compare `events.txt` and the `state_*.json` files. Transcript lines can differ by a word or so between runs, but the counts, phases, files and endpoints should match.

Leave out `TE_SKIP_VOICE_ASK=1` to also test the voice-question button. With no mic, the original app gets the error "sounddevice is not installed..." from that call (which is also the wrong message on Linux). It then leaves the audio-file lecture paused while the indicator still says REC, so nothing more gets recorded. The driver prints `BUG:` when that happens. This bug is fixed in `fixes.patch`.

To look at the dashboard yourself, set `TE_SKIP_END=1` and the driver leaves the app running on http://127.0.0.1:8010 after the typed question. Kill it with `pkill -f "main.py --no-browser"`.

Other inputs:
- `--audio-file $H/samples/lecture.mp3` (or `lecture_slides.mp4`) tests the other decoders.
- Without `--mute` the app tries to play the lecture aloud. With no sound card the playback thread dies and nothing is transcribed. That's another bug fixed in the patch.
- The original app has no way to feed a video into the live camera path. With `--no-camera` the camera panel just shows "Camera is off". `fixes.patch` adds `--video-file`.

## Colab notebook outside Colab

`stubs/` lets `Third_Eye_Colab.ipynb` run under nbclient: put `$H/test/stubs` on `PYTHONPATH` and create a writable `/content`. The notebook runner and a fake Anthropic/Gemini API server for testing LLM calls without keys are being added here next (`run_notebook.py`, `fake_llm.py`).
