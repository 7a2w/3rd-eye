"""
Offline queue for prompts (stand-in for the phone's queue when it has no internet).

A prompt that can't reach the AI is kept with an ID. Every OFFLINE_CHECK_SECONDS the queue checks
for internet; when it is back it says so and answers what was waiting, oldest first.
"""
import threading
import urllib.error
import urllib.request
import uuid

import config
from assistant import speak

CHECK_URL = "https://www.gstatic.com/generate_204"


def is_online(timeout: float = 4) -> bool:
    """True if the internet can be reached (uses the same proxy settings as the AI calls)."""
    try:
        urllib.request.urlopen(CHECK_URL, timeout=timeout).close()
        return True
    except urllib.error.HTTPError:
        return True
    except Exception:
        return False


class OfflineQueue:
    def __init__(self, answer):
        """answer(question) is called for each queued prompt once the internet is back."""
        self.answer = answer
        self.items = []             # {"id", "question"}
        self.online = True
        self._lock = threading.Lock()
        self._wake = threading.Event()
        threading.Thread(target=self._loop, daemon=True).start()

    def __len__(self):
        return len(self.items)

    def add(self, question: str) -> str:
        item = {"id": uuid.uuid4().hex[:8], "question": question}
        with self._lock:
            first = not self.items
            self.items.append(item)
        self.online = False
        print(f"[offline] queued prompt {item['id']}: {question}")
        if first:
            speak("I'm offline. I'll keep recording and answer when I'm back.")
        self._wake.set()
        return item["id"]

    def _loop(self):
        while True:
            self._wake.wait()
            self._wake.clear()
            while self.items:
                if is_online():
                    self.online = True
                    speak("I'm back online.")
                    self._drain()
                    break
                self.online = False
                threading.Event().wait(config.OFFLINE_CHECK_SECONDS)

    def _drain(self):
        while True:
            with self._lock:
                if not self.items:
                    return
                item = self.items.pop(0)
            print(f"[offline] answering queued prompt {item['id']}")
            try:
                self.answer(item["question"])
            except Exception as e:
                print(f"[offline] {item['id']} failed: {e}")
