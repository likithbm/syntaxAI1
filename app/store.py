"""Analysis cache + run history.

DynamoDB when TABLE_NAME is set, otherwise an in-process dict (fine for local
development and for warm Lambda containers).
"""
from __future__ import annotations

import json
import os
import time

_mem: dict[str, tuple[float, str]] = {}
_TTL = 24 * 3600
_table = None


def _ddb():
    global _table
    name = os.environ.get("TABLE_NAME")
    if not name:
        return None
    if _table is None:
        import boto3
        _table = boto3.resource("dynamodb").Table(name)
    return _table


def get(key: str) -> dict | None:
    try:
        t = _ddb()
        if t is not None:
            item = t.get_item(Key={"pk": key}).get("Item")
            if item and int(item.get("expires", 0)) > time.time():
                return json.loads(item["data"])
            return None
    except Exception:
        return None  # cache problems must never break the request
    hit = _mem.get(key)
    if hit and hit[0] > time.time():
        return json.loads(hit[1])
    return None


def put(key: str, value: dict) -> None:
    data = json.dumps(value)
    try:
        t = _ddb()
        if t is not None:
            t.put_item(Item={"pk": key, "data": data, "expires": int(time.time()) + _TTL})
            return
    except Exception:
        return
    _mem[key] = (time.time() + _TTL, data)
