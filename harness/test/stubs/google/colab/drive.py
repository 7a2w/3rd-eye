from pathlib import Path


def mount(path, **kwargs):
    (Path(path) / "MyDrive").mkdir(parents=True, exist_ok=True)
    print(f"[stub drive] mounted at {path}")
