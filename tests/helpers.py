"""Shared helpers for the test-suite (standard library only: run with `python -m unittest`)."""
import base64
import copy
import json
import os
import struct
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.pop("BEDROCK_MODEL_ID", None)
os.environ["BEDROCK_DISABLED"] = "1"
os.environ.pop("ANALYSIS_FIXTURE", None)
os.environ.pop("TABLE_NAME", None)
os.environ.pop("UPLOAD_BUCKET", None)

FIXTURE = ROOT / "tests" / "fixtures" / "sample_analysis.json"


def make_png(w=64, h=64) -> bytes:
    def chunk(t, d):
        c = struct.pack(">I", len(d)) + t + d
        return c + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + b"\x80\x80\x80" * w for _ in range(h))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


def png_b64() -> str:
    return base64.b64encode(make_png()).decode()


def raw_analysis() -> dict:
    return json.loads(FIXTURE.read_text())


def sample_arch() -> dict:
    from app.architecture import normalize_architecture
    return normalize_architecture(raw_analysis())


def clean_arch() -> dict:
    """The sample architecture after every deterministic fix has been applied (what a user would confirm)."""
    from app.architecture import apply_ops
    from app.policy_engine import evaluate_architecture
    a = copy.deepcopy(sample_arch())
    a, _, _ = apply_ops(a, [{"op": "remove_service", "target": "mystery"}])
    for _ in range(4):
        ops = [op for i in evaluate_architecture(a) if i["source"] == "deterministic" and i["severity"] != "valid" for op in i["fixes"]]
        a, _, _ = apply_ops(a, ops)
    return a


def ids(issues, sev=None):
    return {i["id"] for i in issues if sev is None or i["severity"] == sev}
