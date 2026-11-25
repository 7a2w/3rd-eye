# Third Eye for iPhone

A static web app in `app/third_eye_iphone/`. It runs in iPhone Safari, uses the phone's microphone and camera, and can be added to the Home Screen. No build step and no server.

## Run it

Safari needs HTTPS for the microphone and camera. Host the folder on any static HTTPS host (GitHub Pages works, all URLs are relative), open the address in Safari, tap Share, then Add to Home Screen.

For a quick test on a computer: `python -m http.server 8123` inside the folder, then open `http://localhost:8123`.

## What it does

Third Eye is an always-listening assistant, not only a lecture recorder. It works out the situation (lecture, meeting, conversation, call), notes tasks and deadlines on its own, explains things unprompted, and answers when you say "Hey Third Eye, ...". After 10 minutes of quiet it ends the session and writes a summary.


- Records the lecture from the mic and turns it into time-stamped notes. Speech to text uses Gemini or OpenAI with a key, or Safari's own recognizer with no key.
- Watches the camera and saves a slide when the picture changes and holds still, then reads its text (Tesseract on the phone, or AI vision).
- Ask a question by voice or by typing. Claude or Gemini answers from the notes so far; with no key it quotes the matching lines.
- Pause for privacy. The eye in the header is the recording light: red recording, amber listening, grey paused.
- After the lecture it writes a study sheet (key points, terms, test questions, homework, review dates), plus `reminders.ics`, `study_sheet.md`, `study_sheet.json` and the transcript. Share sends them to Files, iCloud Drive or Mail.
- Past lectures are kept on the phone in the Lectures tab.

Keys are stored only in the phone's local storage and sent only to their own provider.

## Limits

- iPhone stops the microphone and camera when the screen locks or you switch apps. Third Eye marks the gap in the notes and carries on when you return. Keep the screen on while recording.
- Not built yet: the 30 second rolling clip buffer and the Word (.docx) export from the build contract.
- Not yet tested on a real iPhone. The logic was exercised in a desktop browser at phone size.
