# Third Eye app cleanup: shared brief

Source: /cursor/stores/bc-2da190a9-e638-48a0-8dcb-770e6fdc201d/internal/uploads/third_eye.zip. Do not modify it.

It is Best Team's (CEN100) laptop and Colab prototype of Third Eye, an ear-worn AI lecture assistant. It contains:
- main.py, config.py, sync.py and indicator.py
- ui_server.py, which serves web/dashboard.html
- audio_capture.py, camera_test.py, transcriber.py, vision.py, assistant.py and study_sheet.py
- colab_helpers.py and Third_Eye_Colab.ipynb
- README.md, requirements.txt and "Start Third Eye.bat"

The user's request, verbatim: "unzip this go through the code and make sure it is compatible for a test implimentation and then humanize it make it have no trace of ai redo the ui in a non ai way"

## Who does what

Each agent writes only to its own folder under /cursor/stores/bc-2da190a9-e638-48a0-8dcb-770e6fdc201d/internal/third-eye-work/:

- **Laptop prototype app:** owns requirements.txt, the test harness, and the bug fixes (as fixes.patch). It also does the final merge.
- **dashboard/ (Dashboard redesign):** web/dashboard.html.
- **core/ (App core modules):** main.py, config.py, ui_server.py, sync.py, indicator.py and Start Third Eye.bat.
- **modules/ (Capture and AI modules):** audio_capture.py, camera_test.py, transcriber.py, vision.py, assistant.py, study_sheet.py and colab_helpers.py.
- **docs/ (README and Colab notebook):** README.md and the text of Third_Eye_Colab.ipynb.

Only the merge step writes the final outputs: app/third_eye/, docs/third_eye.zip and docs/third-eye-app-review.md.

## Rules for every rewrite

- Start from the original files in the zip.
- Behavior stays the same. Leave bugs as they are and list them in your report; the merge step fixes them.
- Don't rename or change anything another file uses:
  - public functions, classes and module-level names
  - signatures and CLI flags
  - config keys and endpoint paths
  - JSON fields and file formats
- Keep the existing snake_case naming and the existing log and print format, so every file reads the same.
- The app keeps its AI features (transcription, LLM calls). The goal is that the code and UI don't read as AI-written.

## Plain writing (code, comments, README, UI copy)

Remove the usual AI tells:
- comments that narrate obvious code, banner or divider comments, and emoji anywhere
- boilerplate Args/Returns docstrings on trivial functions (keep short, useful ones)
- generic try/except everywhere, and needless abstraction
- words like comprehensive, seamless, robust, leverage, AI-powered, intelligent and enhanced
- any mention of ChatGPT, Claude, Cursor or "generated", and AI-tool metadata

Keep comments that are actually useful, and use plain names. Don't add fake typos or deliberate mistakes.

## Dashboard

Avoid:
- purple or blue gradients
- glassmorphism and glows
- emoji or sparkle icons
- "AI-powered" badges and marketing copy
- big hero banners
- everything as rounded cards with heavy shadows

Aim for a deliberate, practical tool: a neutral palette with one accent colour, clear type, compact controls, plain labels and a sensible layout. Every feature, and every endpoint it calls, must keep working.

## Testing

- Pin av==18.1.1. Newer PyAV breaks transcription in faster-whisper 1.2.1.
- The test harness and sample inputs (fake lecture audio, slide and whiteboard photos) go in /cursor/stores/bc-2da190a9-e638-48a0-8dcb-770e6fdc201d/internal/third-eye-work/harness/. Its README explains how to use them. It may land a few minutes after you start.
- To check your files, drop them into a copy of the original app and run the same test as on the original. Compare the results.
