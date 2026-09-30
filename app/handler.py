"""AWS Lambda entry point (API Gateway HTTP API, payload format 2.0)."""
from __future__ import annotations

import base64
import json
import logging
import os
import traceback

from . import pipeline
from .errors import AppError

log = logging.getLogger()
log.setLevel(logging.INFO)

ROUTES = {
    ("POST", "/analyze"): pipeline.analyze,
    ("POST", "/refine"): pipeline.refine,
    ("POST", "/patch"): pipeline.patch,
    ("POST", "/revalidate"): pipeline.revalidate,
    ("POST", "/generate"): pipeline.generate,
    ("POST", "/verify"): pipeline.verify,
}


def _cors():
    return {
        "Access-Control-Allow-Origin": os.environ.get("ALLOWED_ORIGIN", "*"),
        "Access-Control-Allow-Headers": "content-type",
        "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
    }


def _resp(status: int, body: dict) -> dict:
    return {"statusCode": status, "headers": {"content-type": "application/json", **_cors()}, "body": json.dumps(body)}


def lambda_handler(event, context=None):
    http = (event.get("requestContext") or {}).get("http") or {}
    method = (http.get("method") or event.get("httpMethod") or "GET").upper()
    path = event.get("rawPath") or event.get("path") or "/"
    stage = (event.get("requestContext") or {}).get("stage")
    if stage and stage != "$default" and path.startswith(f"/{stage}/"):
        path = path[len(stage) + 1:]
    path = path.rstrip("/") or "/"
    if path.startswith("/api/"):  # local dev proxy prefix
        path = path[4:]
    if method == "OPTIONS":
        return {"statusCode": 204, "headers": _cors(), "body": ""}
    if method == "GET" and path == "/health":
        from .bedrock_client import bedrock_enabled
        return _resp(200, {"ok": True, "bedrock_configured": bedrock_enabled(),
                           "model": os.environ.get("BEDROCK_MODEL_ID"), "fixture_mode": bool(os.environ.get("ANALYSIS_FIXTURE"))})
    fn = ROUTES.get((method, path))
    if fn is None:
        return _resp(404, {"error": {"code": "NOT_FOUND", "message": f"No route for {method} {path}", "retryable": False}})
    try:
        raw = event.get("body") or "{}"
        if event.get("isBase64Encoded"):
            raw = base64.b64decode(raw).decode("utf-8")
        try:
            body = json.loads(raw)
        except json.JSONDecodeError as e:
            raise AppError("BAD_JSON", f"Request body is not valid JSON: {e.msg}", 400) from e
        if not isinstance(body, dict):
            raise AppError("BAD_JSON", "Request body must be a JSON object.", 400)
        return _resp(200, fn(body))
    except AppError as e:
        log.warning("AppError %s: %s", e.code, e.message)
        return _resp(e.status, e.to_dict())
    except Exception as e:  # never crash the API
        log.error("Unhandled error: %s\n%s", e, traceback.format_exc())
        return _resp(500, {"error": {"code": "INTERNAL_ERROR", "message": f"Unexpected error: {type(e).__name__}: {e}", "retryable": True}})
