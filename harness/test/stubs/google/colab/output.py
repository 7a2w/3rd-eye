import base64
import os
from pathlib import Path


def eval_js(js, **kwargs):
    if "recordQuestion" not in js:
        raise ValueError("unexpected JS: " + js[:80])
    return base64.b64encode(Path(os.environ["TE_MIC_FILE"]).read_bytes()).decode()
