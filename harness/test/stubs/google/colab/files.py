import os
import shutil
from pathlib import Path

_batches = [b for b in os.environ.get("TE_UPLOADS", "").split(";;") if b]
_calls = 0
downloaded = []


def upload():
    global _calls
    batch = _batches[_calls] if _calls < len(_batches) else ""
    _calls += 1
    out = {}
    for p in [x for x in batch.split(os.pathsep) if x]:
        p = Path(p)
        data = p.read_bytes()
        shutil.copy(p, Path.cwd() / p.name)
        out[p.name] = data
        print(f"[stub upload] {p.name} ({len(data)} bytes)")
    return out


def download(path):
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)
    downloaded.append(str(path))
    print(f"[stub download] {path.name} ({path.stat().st_size} bytes)")
