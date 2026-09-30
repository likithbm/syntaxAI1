"""Canonical architecture model.

Everything downstream (validation, refinement, code generation) works on this
structured JSON, never on free-form model text.
"""
from __future__ import annotations

import copy
import re
from typing import Any

SUPPORTED_TYPES = ["alb", "ec2", "rds", "s3", "lambda", "dynamodb", "sqs", "sns", "internet"]

# Recognised in a diagram but not translated into IaC by this version.
KNOWN_UNSUPPORTED = [
    "api_gateway", "cloudfront", "route53", "waf", "cognito", "ecs", "eks",
    "elasticache", "efs", "kinesis", "cloudwatch", "iam_role", "other",
]

# Derived automatically from the network section; never emitted as services.
NETWORK_DERIVED = ["vpc", "subnet", "internet_gateway", "nat_gateway", "security_group"]

TYPE_LABELS = {
    "alb": "Application Load Balancer", "ec2": "EC2", "rds": "RDS", "s3": "S3",
    "lambda": "Lambda", "dynamodb": "DynamoDB", "sqs": "SQS", "sns": "SNS",
    "internet": "Internet", "api_gateway": "API Gateway", "cloudfront": "CloudFront",
    "route53": "Route 53", "waf": "WAF", "cognito": "Cognito", "ecs": "ECS", "eks": "EKS",
    "elasticache": "ElastiCache", "efs": "EFS", "kinesis": "Kinesis",
    "cloudwatch": "CloudWatch", "iam_role": "IAM role", "other": "Unknown component",
}

_ALIASES: list[tuple[str, str]] = [
    (r"application load|\balb\b|\belb\b|load ?balancer", "alb"),
    (r"api ?gateway|apigw", "api_gateway"),
    (r"cloud ?front|\bcdn\b", "cloudfront"),
    (r"route ?53|\bdns\b", "route53"),
    (r"\bwaf\b|web application firewall", "waf"),
    (r"cognito", "cognito"),
    (r"\becs\b|fargate", "ecs"),
    (r"\beks\b|kubernetes", "eks"),
    (r"elasticache|redis|memcache", "elasticache"),
    (r"\befs\b|elastic file", "efs"),
    (r"kinesis", "kinesis"),
    (r"cloud ?watch", "cloudwatch"),
    (r"nat ?gateway|\bnat\b", "nat_gateway"),
    (r"internet ?gateway|\bigw\b", "internet_gateway"),
    (r"security ?group", "security_group"),
    (r"\bvpc\b", "vpc"),
    (r"subnet", "subnet"),
    (r"\bs3\b|bucket|simple storage", "s3"),
    (r"dynamo", "dynamodb"),
    (r"\bsqs\b|queue", "sqs"),
    (r"\bsns\b|topic|notification", "sns"),
    (r"lambda|serverless function", "lambda"),
    (r"\brds\b|aurora|mysql|postgres|mariadb|database|\bdb\b", "rds"),
    (r"\bec2\b|instance|virtual machine|\bvm\b|web server|app server|server|auto ?scaling", "ec2"),
    (r"internet|user|client|browser|public web|customer", "internet"),
    (r"\biam\b|role", "iam_role"),
]

OPTION_IDS = [
    "encryption", "private_subnets", "iam_least_privilege", "cloudwatch_logging",
    "security_groups", "multi_az", "backups", "https_tls", "monitoring", "cost_optimization",
]

PROPERTY_KEYS = {"public", "encrypted", "multi_az", "backup_retention", "engine", "instance_class"}
RDS_ENGINES = {"postgres", "mysql", "mariadb"}


def slug(text: Any) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", str(text or "").lower()).strip("_")
    if not s:
        return "component"
    if s[0].isdigit():
        s = "c_" + s
    return s[:40]


def classify(raw_type: Any, label: Any = "") -> str:
    t = re.sub(r"[^a-z0-9]+", "_", str(raw_type or "").lower()).strip("_")
    if t in SUPPORTED_TYPES or t in KNOWN_UNSUPPORTED or t in NETWORK_DERIVED:
        return t
    for text in (str(raw_type or "").lower(), str(label or "").lower()):
        for pattern, target in _ALIASES:
            if re.search(pattern, text):
                return target
    return "other"


def _tri(v: Any) -> bool | None:
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        if v.strip().lower() in ("true", "yes", "y", "1"):
            return True
        if v.strip().lower() in ("false", "no", "n", "0"):
            return False
    return None


def _num(v: Any, default: int | None = None) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _conf(v: Any) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return 0.5
    return max(0.0, min(1.0, f))


def _severity(v: Any, default: str) -> str:
    v = str(v or "").lower()
    return v if v in ("critical", "warning", "recommendation") else default


def _text_items(items: Any, default_sev: str) -> list[dict]:
    out = []
    for it in items if isinstance(items, list) else []:
        if isinstance(it, str):
            out.append({"severity": default_sev, "component": None, "message": it})
        elif isinstance(it, dict) and (it.get("message") or it.get("text")):
            out.append({
                "severity": _severity(it.get("severity"), default_sev),
                "component": it.get("component") or None,
                "message": str(it.get("message") or it.get("text")),
            })
    return out


def empty_architecture() -> dict:
    return {
        "version": 1,
        "services": [], "connections": [],
        "network": {"vpc": False, "vpc_cidr": None, "availability_zones": 1, "subnets": []},
        "security_findings": [], "warnings": [], "ambiguities": [], "recommendations": [],
        "requirements": {k: False for k in OPTION_IDS} | {"notes": []},
        "image_quality": "good", "image_quality_notes": "",
    }


def normalize_architecture(raw: Any) -> dict:
    """Coerce model JSON into the canonical shape. Never raises on odd input."""
    arch = empty_architecture()
    if not isinstance(raw, dict):
        return arch

    q = str(raw.get("image_quality") or "good").lower()
    arch["image_quality"] = q if q in ("good", "fair", "poor") else "fair"
    arch["image_quality_notes"] = str(raw.get("image_quality_notes") or "")

    net_raw = raw.get("network") if isinstance(raw.get("network"), dict) else {}
    net = arch["network"]
    net["vpc"] = bool(_tri(net_raw.get("vpc")))
    cidr = net_raw.get("vpc_cidr")
    net["vpc_cidr"] = cidr if isinstance(cidr, str) and re.fullmatch(r"\d{1,3}(\.\d{1,3}){3}/\d{1,2}", cidr) else None
    net["availability_zones"] = max(1, min(3, _num(net_raw.get("availability_zones"), 1) or 1))
    for s in net_raw.get("subnets") or []:
        if isinstance(s, dict):
            tier = str(s.get("tier") or "").lower()
            net["subnets"].append({
                "id": slug(s.get("id") or s.get("name") or "subnet"),
                "tier": tier if tier in ("public", "private") else "unknown",
                "az": _num(s.get("az")),
            })

    used: set[str] = set()
    id_map: dict[str, str] = {}
    for item in raw.get("services") or []:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or item.get("name") or item.get("id") or "").strip()
        stype = classify(item.get("type"), label)
        raw_id = str(item.get("id") or label or stype)
        if stype in NETWORK_DERIVED:
            # folded into network section / generated automatically
            if stype == "vpc":
                net["vpc"] = True
            elif stype == "subnet":
                tier = "public" if "public" in (label + raw_id).lower() else "private" if "private" in (label + raw_id).lower() else "unknown"
                net["subnets"].append({"id": slug(raw_id), "tier": tier, "az": None})
            continue
        sid = slug(raw_id)
        base, n = sid, 2
        while sid in used:
            sid, n = f"{base}_{n}", n + 1
        used.add(sid)
        id_map[raw_id.lower()] = sid
        id_map[slug(raw_id)] = sid
        if label:
            id_map[label.lower()] = sid
            id_map[slug(label)] = sid
        props_raw = item.get("properties") if isinstance(item.get("properties"), dict) else {}
        tier = str(item.get("tier") or props_raw.get("tier") or "unknown").lower()
        engine = str(props_raw.get("engine") or "").lower() or None
        if engine and engine not in RDS_ENGINES:
            engine = "mysql" if "mysql" in engine else "postgres" if "postgres" in engine else None
        arch["services"].append({
            "id": sid, "type": stype, "label": label or TYPE_LABELS.get(stype, stype),
            "confidence": _conf(item.get("confidence")),
            "tier": tier if tier in ("public", "private", "unknown", "n/a") else "unknown",
            "properties": {
                "public": _tri(props_raw.get("public")),
                "encrypted": _tri(props_raw.get("encrypted")),
                "multi_az": _tri(props_raw.get("multi_az")),
                "backup_retention": _num(props_raw.get("backup_retention")),
                "engine": engine,
                "instance_class": None,
            },
            "notes": str(item.get("notes") or ""),
        })

    by_ref = dict(id_map)
    for s in arch["services"]:
        by_ref[s["id"]] = s["id"]

    def resolve(ref: Any) -> str | None:
        r = str(ref or "").strip()
        if not r:
            return None
        for key in (r, r.lower(), slug(r)):
            if key in by_ref:
                return by_ref[key]
        return None

    seen = set()
    for c in raw.get("connections") or []:
        if not isinstance(c, dict):
            continue
        src_raw, dst_raw = c.get("from"), c.get("to")
        src, dst = resolve(src_raw), resolve(dst_raw)
        for which, resolved, r in (("src", src, src_raw), ("dst", dst, dst_raw)):
            if resolved is None and classify(r, r) == "internet":
                inet = next((s for s in arch["services"] if s["type"] == "internet"), None)
                if inet is None:
                    inet = {"id": "internet", "type": "internet", "label": "Internet", "confidence": 0.9, "tier": "n/a",
                            "properties": {"public": None, "encrypted": None, "multi_az": None,
                                           "backup_retention": None, "engine": None, "instance_class": None}, "notes": ""}
                    arch["services"].insert(0, inet)
                    by_ref["internet"] = "internet"
                if which == "src":
                    src = inet["id"]
                else:
                    dst = inet["id"]
        conn = {
            "from": src or slug(src_raw), "to": dst or slug(dst_raw),
            "label": str(c.get("label") or ""), "protocol": str(c.get("protocol") or ""),
            "unresolved": src is None or dst is None,
        }
        key = (conn["from"], conn["to"])
        if key in seen or not conn["from"] or not conn["to"]:
            continue
        seen.add(key)
        arch["connections"].append(conn)

    arch["security_findings"] = _text_items(raw.get("security_findings"), "warning")
    arch["warnings"] = _text_items(raw.get("warnings"), "warning")
    arch["recommendations"] = _text_items(raw.get("recommendations"), "recommendation")
    arch["ambiguities"] = _text_items(raw.get("ambiguities"), "warning")
    for s in arch["services"]:
        if s["type"] == "internet":
            s["tier"] = "n/a"
    return arch


def load_architecture(data: Any) -> dict:
    """Re-validate an architecture sent back by the client (never trust the shape)."""
    from .errors import AppError

    if not isinstance(data, dict) or not isinstance(data.get("services"), list):
        raise AppError("BAD_ARCHITECTURE", "The request did not include a valid architecture object.", status=400)
    arch = normalize_architecture(data)
    req = data.get("requirements")
    if isinstance(req, dict):
        for k in OPTION_IDS:
            arch["requirements"][k] = bool(req.get(k))
        arch["requirements"]["notes"] = [str(n)[:300] for n in (req.get("notes") or []) if isinstance(n, str)][:20]
    return arch


# ---------------------------------------------------------------- patch ops

def service_by_id(arch: dict, sid: str) -> dict | None:
    return next((s for s in arch["services"] if s["id"] == sid), None)


def apply_ops(arch: dict, ops: list[dict]) -> tuple[dict, list[str], list[dict]]:
    """Apply whitelisted patch operations. Returns (new_arch, applied_descriptions, rejected)."""
    a = copy.deepcopy(arch)
    applied: list[str] = []
    rejected: list[dict] = []

    def reject(op, why):
        rejected.append({"op": op, "reason": why})

    for op in ops or []:
        if not isinstance(op, dict):
            reject(op, "not an object")
            continue
        kind = op.get("op")
        tgt = op.get("target")
        svc = service_by_id(a, tgt) if tgt else None
        if kind in ("set_property", "set_tier", "set_type", "rename", "remove_service") and svc is None:
            reject(op, f"unknown component '{tgt}'")
            continue
        if kind == "set_property":
            key, val = op.get("key"), op.get("value")
            if key not in PROPERTY_KEYS:
                reject(op, f"property '{key}' not allowed")
                continue
            if key in ("public", "encrypted", "multi_az"):
                val = _tri(val)
                if val is None:
                    reject(op, "expected boolean")
                    continue
            elif key == "backup_retention":
                val = _num(val)
                if val is None or not 0 <= val <= 35:
                    reject(op, "backup_retention must be 0-35")
                    continue
            elif key == "engine":
                val = str(val).lower()
                if val not in RDS_ENGINES:
                    reject(op, "engine must be postgres, mysql or mariadb")
                    continue
            svc["properties"][key] = val
            applied.append(f"{svc['label']}: {key} = {str(val).lower() if isinstance(val, bool) else val}")
        elif kind == "set_tier":
            tier = op.get("tier")
            if tier not in ("public", "private"):
                reject(op, "tier must be public or private")
                continue
            svc["tier"] = tier
            if tier == "private" and svc["type"] == "rds":
                svc["properties"]["public"] = False
            applied.append(f"{svc['label']}: placed in {tier} subnet")
        elif kind == "set_type":
            if op.get("type") not in SUPPORTED_TYPES + KNOWN_UNSUPPORTED:
                reject(op, "unsupported type")
                continue
            svc["type"] = op["type"]
            svc["confidence"] = 1.0
            applied.append(f"{svc['label']}: type set to {TYPE_LABELS.get(op['type'], op['type'])}")
        elif kind == "rename":
            label = str(op.get("label") or "").strip()[:60]
            if not label:
                reject(op, "empty label")
                continue
            svc["label"] = label
            applied.append(f"Renamed {tgt} to {label}")
        elif kind == "remove_service":
            a["services"] = [s for s in a["services"] if s["id"] != tgt]
            a["connections"] = [c for c in a["connections"] if tgt not in (c["from"], c["to"])]
            applied.append(f"Removed {svc['label']}")
        elif kind == "add_service":
            stype = op.get("type")
            if stype not in SUPPORTED_TYPES:
                reject(op, "cannot add unsupported type")
                continue
            base = slug(op.get("id") or op.get("label") or stype)
            sid, n = base, 2
            while service_by_id(a, sid):
                sid, n = f"{base}_{n}", n + 1
            default_tier = {"alb": "public", "internet": "n/a"}.get(stype, "private" if stype in ("ec2", "rds", "lambda") else "n/a")
            a["services"].append({
                "id": sid, "type": stype, "label": str(op.get("label") or TYPE_LABELS[stype]),
                "confidence": 1.0, "tier": op.get("tier") if op.get("tier") in ("public", "private") else default_tier,
                "properties": {"public": None, "encrypted": None, "multi_az": None,
                               "backup_retention": None, "engine": None, "instance_class": None},
                "notes": "added by user",
            })
            applied.append(f"Added {TYPE_LABELS[stype]} ({sid})")
        elif kind in ("add_connection", "remove_connection", "reverse_connection"):
            src, dst = op.get("from"), op.get("to")
            # removing a dangling connection must work even though one endpoint does not exist
            if kind != "remove_connection" and (not service_by_id(a, src) or not service_by_id(a, dst)):
                reject(op, "unknown endpoint")
                continue
            existing = next((c for c in a["connections"] if c["from"] == src and c["to"] == dst), None)
            if kind == "add_connection":
                if existing or src == dst:
                    continue
                a["connections"].append({"from": src, "to": dst, "label": "", "protocol": "", "unresolved": False})
                applied.append(f"Connected {src} -> {dst}")
            elif kind == "remove_connection":
                a["connections"] = [c for c in a["connections"] if not (c["from"] == src and c["to"] == dst)]
                applied.append(f"Removed connection {src} -> {dst}")
            else:
                if existing:
                    existing["from"], existing["to"] = dst, src
                    applied.append(f"Reversed connection {src} -> {dst}")
        elif kind == "set_azs":
            n = _num(op.get("value"))
            if n is None or not 1 <= n <= 3:
                reject(op, "availability zones must be 1-3")
                continue
            a["network"]["availability_zones"] = n
            applied.append(f"Availability Zones: {n}")
        elif kind == "set_vpc":
            a["network"]["vpc"] = bool(op.get("value", True))
            applied.append("VPC included" if a["network"]["vpc"] else "VPC removed")
        elif kind == "set_requirement":
            key = op.get("key")
            if key not in OPTION_IDS:
                reject(op, f"unknown requirement '{key}'")
                continue
            a["requirements"][key] = bool(op.get("value", True))
            applied.append(f"Requirement '{key}' = {bool(op.get('value', True))}")
        elif kind == "remove_note":
            i = _num(op.get("index"))
            notes = a["requirements"]["notes"]
            if i is None or not 0 <= i < len(notes):
                reject(op, "no such note")
                continue
            applied.append(f"Removed note: {notes.pop(i)}")
        elif kind == "add_note":
            text = str(op.get("text") or "").strip()[:300]
            if text:
                a["requirements"]["notes"].append(text)
                applied.append(f"Note recorded: {text}")
        else:
            reject(op, f"unknown operation '{kind}'")
    return a, applied, rejected


def options_to_ops(arch: dict, options: list[str]) -> list[dict]:
    """Translate the selectable refinement checkboxes into concrete patch operations."""
    ops: list[dict] = []
    for opt in options or []:
        if opt not in OPTION_IDS:
            continue
        ops.append({"op": "set_requirement", "key": opt, "value": True})
        for s in arch["services"]:
            t = s["type"]
            if opt == "encryption" and t in ("s3", "rds", "dynamodb", "sqs", "sns", "ec2"):
                ops.append({"op": "set_property", "target": s["id"], "key": "encrypted", "value": True})
            elif opt == "private_subnets" and t in ("ec2", "rds", "lambda"):
                ops.append({"op": "set_tier", "target": s["id"], "tier": "private"})
            elif opt == "multi_az" and t == "rds":
                ops.append({"op": "set_property", "target": s["id"], "key": "multi_az", "value": True})
            elif opt == "backups" and t == "rds" and not (s["properties"].get("backup_retention") or 0):
                ops.append({"op": "set_property", "target": s["id"], "key": "backup_retention", "value": 7})
        if opt == "multi_az" and arch["network"]["availability_zones"] < 2:
            ops.append({"op": "set_azs", "value": 2})
    return ops
