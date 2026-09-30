"""Bedrock access (Converse API). All model output is parsed into JSON here."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from .errors import AppError

PROMPT_DIR = Path(__file__).parent / "prompts"
_prompt_cache: dict[str, str] = {}


def prompt(name: str) -> str:
    if name not in _prompt_cache:
        _prompt_cache[name] = (PROMPT_DIR / f"{name}.md").read_text(encoding="utf-8")
    return _prompt_cache[name]


def bedrock_enabled() -> bool:
    return bool(os.environ.get("BEDROCK_MODEL_ID")) and os.environ.get("BEDROCK_DISABLED") != "1"


_client = None


def _get_client():
    global _client
    if _client is None:
        import boto3
        from botocore.config import Config

        _client = boto3.client(
            "bedrock-runtime",
            region_name=os.environ.get("BEDROCK_REGION") or os.environ.get("AWS_REGION") or "us-east-1",
            config=Config(read_timeout=int(os.environ.get("BEDROCK_TIMEOUT_S", "40")),
                          connect_timeout=5, retries={"max_attempts": 2, "mode": "standard"}),
        )
    return _client


def extract_json(text: str) -> dict:
    """Pull the first JSON object out of model text (tolerates fences / stray prose)."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.S)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    if start == -1:
        raise ValueError("no JSON object found")
    depth, in_str, esc = 0, False, False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start:i + 1])
    raise ValueError("unterminated JSON object")


def _converse(content: list[dict], system: str, max_tokens: int, model_id: str | None = None) -> str:
    model_id = model_id or os.environ["BEDROCK_MODEL_ID"]
    try:
        resp = _get_client().converse(
            modelId=model_id,
            system=[{"text": system}],
            messages=[{"role": "user", "content": content}],
            inferenceConfig={"maxTokens": max_tokens, "temperature": 0},
        )
    except Exception as e:  # botocore ClientError etc.
        name = type(e).__name__
        code = getattr(e, "response", {}).get("Error", {}).get("Code", name)
        retryable = code in ("ThrottlingException", "ModelTimeoutException", "ServiceUnavailableException",
                             "InternalServerException", "ReadTimeoutError", "EndpointConnectionError")
        raise AppError("BEDROCK_ERROR", f"Bedrock request failed ({code}): {e}", status=502, retryable=retryable) from e
    parts = resp.get("output", {}).get("message", {}).get("content", [])
    text = "".join(p.get("text", "") for p in parts)
    if resp.get("stopReason") == "max_tokens":
        raise AppError("BEDROCK_TRUNCATED", "The model response was cut off (too long).", status=502, retryable=True)
    return text


def _json_call(content: list[dict], system: str, max_tokens: int, model_id: str | None = None) -> dict:
    text = _converse(content, system, max_tokens, model_id)
    try:
        return extract_json(text)
    except (ValueError, json.JSONDecodeError):
        # One cheap, text-only repair attempt (the image is NOT sent again).
        repair = _converse(
            [{"text": "The following was meant to be one valid JSON object but is malformed. "
                      "Return ONLY the corrected JSON object.\n\n" + text[:12000]}],
            "You repair malformed JSON. Output only JSON.", max_tokens, model_id)
        try:
            return extract_json(repair)
        except (ValueError, json.JSONDecodeError) as e:
            raise AppError("BEDROCK_MALFORMED", "The model returned a response that could not be parsed as JSON.",
                           status=502, retryable=True, details={"sample": text[:400]}) from e


def analyze_image(image_bytes: bytes, fmt: str) -> dict:
    content = [
        {"image": {"format": fmt, "source": {"bytes": image_bytes}}},
        {"text": "Analyze this architecture diagram and return the JSON object described in the instructions."},
    ]
    return _json_call(content, prompt("analyze"), max_tokens=4096)


def interpret_refinement(arch_summary: dict, text: str) -> dict:
    model = os.environ.get("BEDROCK_TEXT_MODEL_ID") or None
    content = [{"text": "CURRENT ARCHITECTURE:\n" + json.dumps(arch_summary) + "\n\nUSER REQUEST:\n" + text}]
    return _json_call(content, prompt("refine"), max_tokens=1500, model_id=model)


def ai_fix_code(files: dict[str, str], errors: list[dict]) -> dict:
    model = os.environ.get("BEDROCK_TEXT_MODEL_ID") or None
    body = {"files": files, "errors": [{"code": e["code"], "message": e["message"], "file": e.get("file")} for e in errors]}
    return _json_call([{"text": json.dumps(body)}], prompt("fix"), max_tokens=8000, model_id=model)
