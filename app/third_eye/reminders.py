"""
Reminder timer. For every task with a due time it speaks and shows a notification
one hour before, and once more at the due time. Tasks are remembered across sessions
until both reminders have gone off.
"""
import platform
import subprocess
import threading
import time
from datetime import datetime, timedelta

from assistant import speak
from brain import _parse_due

LEAD = timedelta(hours=1)
LATE = timedelta(minutes=15)     # a reminder this late is still given; older ones are skipped


def notify(title: str, text: str):
    """Windows notification-area balloon. Best effort: never raises."""
    if platform.system() != "Windows":
        return
    try:
        safe = lambda s: s.replace("'", "''")
        script = ("Add-Type -AssemblyName System.Windows.Forms; Add-Type -AssemblyName System.Drawing; "
                  "$n=New-Object System.Windows.Forms.NotifyIcon; $n.Icon=[System.Drawing.SystemIcons]::Information; "
                  f"$n.Visible=$true; $n.ShowBalloonTip(8000,'{safe(title)}','{safe(text)}','Info'); "
                  "Start-Sleep -Seconds 9; $n.Dispose()")
        subprocess.Popen(["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", script],
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except Exception as e:
        print(f"[reminder] notification failed: {e}")


class ReminderTimer:
    def __init__(self, get_tasks):
        """get_tasks() returns the current session's task list (brain.task_list())."""
        self.get_tasks = get_tasks
        self.tasks = {}              # id -> task dict
        self.fired = set()           # (id, "hour" | "due")
        self._lock = threading.Lock()
        threading.Thread(target=self._loop, daemon=True).start()

    def _sync(self):
        try:
            current = self.get_tasks() or []
        except Exception:
            current = []
        with self._lock:
            for t in current:
                self.tasks[t["id"]] = t

    def _pending(self):
        """(when, task, kind) for every reminder not yet given, soonest first."""
        out = []
        with self._lock:
            tasks = list(self.tasks.values())
        for t in tasks:
            due = _parse_due(t.get("due"))
            if not due or t.get("done"):
                continue
            for kind, at in (("hour", due - LEAD), ("due", due)):
                if (t["id"], kind) not in self.fired:
                    out.append((at, t, kind))
        return sorted(out, key=lambda x: x[0])

    def upcoming(self, n: int = 3):
        now = datetime.now()
        return [{"task": t["task"], "at": at.strftime("%Y-%m-%d %H:%M")}
                for at, t, _ in self._pending() if at >= now - LATE][:n]

    def _loop(self):
        while True:
            self._sync()
            now = datetime.now()
            for at, t, kind in self._pending():
                if at > now:
                    break
                self.fired.add((t["id"], kind))
                if now - at > LATE:
                    continue
                text = (f"Reminder: {t['task']} is due in 1 hour" if kind == "hour"
                        else f"Reminder: {t['task']} is due now")
                print(f"[reminder] {text}")
                speak(text)
                notify("Third Eye", text)
            time.sleep(20)
