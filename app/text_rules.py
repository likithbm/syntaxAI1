"""Rule-based interpreter for refinement text.

Used when Bedrock is not configured or fails. It only emits whitelisted patch
operations; anything it cannot map is returned in `unmapped` (never silently dropped).
"""
from __future__ import annotations

import re

from .architecture import SUPPORTED_TYPES, TYPE_LABELS, classify, slug

_TYPE_WORDS = {
    "rds": r"rds|database|\bdb\b|postgres|mysql|mariadb",
    "ec2": r"ec2|instances?|servers?|compute|web tier|app tier",
    "s3": r"s3|buckets?",
    "alb": r"alb|load ?balancer",
    "lambda": r"lambda|functions?",
    "dynamodb": r"dynamo\w*|tables?",
    "sqs": r"sqs|queues?",
    "sns": r"sns|topics?",
}


def _targets(arch: dict, phrase: str) -> list[dict]:
    """Components a phrase refers to (by id, label or type word)."""
    phrase_l = phrase.lower()
    hits = [s for s in arch["services"] if s["id"] in phrase_l.replace(" ", "_") or (len(s["label"]) > 2 and s["label"].lower() in phrase_l)]
    if hits:
        return hits
    for stype, words in _TYPE_WORDS.items():
        if re.search(words, phrase_l):
            return [s for s in arch["services"] if s["type"] == stype]
    return []


def interpret(arch: dict, text: str) -> tuple[list[dict], list[str]]:
    ops: list[dict] = []
    unmapped: list[str] = []
    clauses = [c.strip() for c in re.split(r"[.;\n]|\band\b(?=\s+(?:make|enable|use|add|remove|delete|connect|move|deploy|apply|turn))", text or "") if c.strip()]
    for clause in clauses:
        for piece in [p.strip() for p in clause.split(",") if p.strip()]:
            c = piece.lower()
            before = len(ops)

            m = re.search(r"\b(?:make|move|put|place|keep)\b(.*?)\b(private|public)\b", c)
            if m and "subnet" not in m.group(1)[:0]:
                tier = m.group(2)
                targets = _targets(arch, m.group(1)) or []
                if not targets and "subnet" in c and re.search(r"private subnets?", c):
                    ops.append({"op": "set_requirement", "key": "private_subnets", "value": True})
                for s in targets:
                    if s["type"] == "rds":
                        ops.append({"op": "set_property", "target": s["id"], "key": "public", "value": tier == "public"})
                    if s["type"] in ("rds", "ec2", "lambda"):
                        ops.append({"op": "set_tier", "target": s["id"], "tier": tier})
                    elif s["type"] == "s3":
                        ops.append({"op": "set_property", "target": s["id"], "key": "public", "value": tier == "public"})

            if re.search(r"encrypt", c):
                ops.append({"op": "set_requirement", "key": "encryption", "value": True})
                for s in arch["services"]:
                    if s["type"] in ("s3", "rds", "dynamodb", "sqs", "sns"):
                        ops.append({"op": "set_property", "target": s["id"], "key": "encrypted", "value": True})
            if re.search(r"least[- ]privilege|\biam\b", c):
                ops.append({"op": "set_requirement", "key": "iam_least_privilege", "value": True})
            if re.search(r"backup", c):
                ops.append({"op": "set_requirement", "key": "backups", "value": True})
                for s in arch["services"]:
                    if s["type"] == "rds" and not (s["properties"].get("backup_retention") or 0):
                        ops.append({"op": "set_property", "target": s["id"], "key": "backup_retention", "value": 7})
            if re.search(r"multi[- ]?az", c):
                ops.append({"op": "set_requirement", "key": "multi_az", "value": True})
                ops.append({"op": "set_azs", "value": 2})
                for s in arch["services"]:
                    if s["type"] == "rds":
                        ops.append({"op": "set_property", "target": s["id"], "key": "multi_az", "value": True})
            m = re.search(r"(\d)\s*(?:availability zones?|azs?)|(two|three)\s+(?:availability zones?|azs?)", c)
            if m:
                n = int(m.group(1)) if m.group(1) else {"two": 2, "three": 3}[m.group(2)]
                ops.append({"op": "set_azs", "value": n})
            if re.search(r"https|\btls\b|\bssl\b", c):
                ops.append({"op": "set_requirement", "key": "https_tls", "value": True})
            if re.search(r"monitor|alarm", c):
                ops.append({"op": "set_requirement", "key": "monitoring", "value": True})
            if re.search(r"\blogg?ing\b|\blogs\b|cloudwatch", c):
                ops.append({"op": "set_requirement", "key": "cloudwatch_logging", "value": True})
            if re.search(r"cost", c):
                ops.append({"op": "set_requirement", "key": "cost_optimization", "value": True})
            if re.search(r"security groups?", c):
                ops.append({"op": "set_requirement", "key": "security_groups", "value": True})
            if re.search(r"private subnets?", c) and not re.search(r"\b(make|move|put|place|keep)\b", c):
                ops.append({"op": "set_requirement", "key": "private_subnets", "value": True})
            m = re.search(r"\b(mysql|postgres(?:ql)?|mariadb)\b", c)
            if m and re.search(r"\buse\b|engine", c):
                eng = "postgres" if m.group(1).startswith("postgres") else m.group(1)
                for s in arch["services"]:
                    if s["type"] == "rds":
                        ops.append({"op": "set_property", "target": s["id"], "key": "engine", "value": eng})

            m = re.search(r"\badd\b\s+(?:an?\s+|the\s+)?(.+)", c)
            if m:
                stype = classify(m.group(1), m.group(1))
                if stype in SUPPORTED_TYPES and stype != "internet":
                    new_id = slug(stype) if not any(s["id"] == slug(stype) for s in arch["services"]) else slug(stype) + "_2"
                    ops.append({"op": "add_service", "type": stype, "id": new_id, "label": TYPE_LABELS[stype]})
                    if stype == "alb":
                        inet = next((s for s in arch["services"] if s["type"] == "internet"), None)
                        if inet:
                            ops.append({"op": "add_connection", "from": inet["id"], "to": new_id})
                        for s in arch["services"]:
                            if s["type"] == "ec2":
                                ops.append({"op": "add_connection", "from": new_id, "to": s["id"]})

            m = re.search(r"\b(?:remove|delete)\b\s+(?:the\s+)?(.+)", c)
            if m:
                for s in _targets(arch, m.group(1)):
                    ops.append({"op": "remove_service", "target": s["id"]})

            m = re.search(r"\bconnect\b\s+(?:the\s+)?(.+?)\s+(?:to|with)\s+(?:the\s+)?(.+)", c)
            if m:
                a, b = _targets(arch, m.group(1)), _targets(arch, m.group(2))
                for x in a[:3]:
                    for y in b[:3]:
                        ops.append({"op": "add_connection", "from": x["id"], "to": y["id"]})

            if len(ops) == before:
                unmapped.append(piece)
    return ops, unmapped
