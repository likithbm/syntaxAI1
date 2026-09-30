"""Orchestration of the whole workflow with REAL per-stage timings.

Stages / endpoints:
  analyze  : image -> Bedrock (one multimodal call) -> structured JSON -> normalize -> validate
  refine   : options + free text -> patch ops -> apply -> re-validate
  patch    : explicit patch ops (Apply Correction / Edit) -> apply -> re-validate
  generate : confirm architecture (blocking check) -> deterministic IaC generation from the JSON
  verify   : validate generated code, auto-fix, re-validate; security report
The image is sent to the model exactly once; every later stage works on JSON.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager

from . import bedrock_client, guide, store
from .architecture import OPTION_IDS, apply_ops, load_architecture, normalize_architecture, options_to_ops
from .codegen import cdk as cdk_gen
from .codegen import cloudformation as cfn_gen
from .codegen.plan import ENVIRONMENTS, REGIONS, Plan
from .errors import AppError
from .policy_engine import blocking_issues, evaluate_architecture
from .policy_engine import code_rules
from .text_rules import interpret
from .validators import fixer
from .validators.cdk_validator import validate_cdk
from .validators.cfn_validator import validate_cfn

MAX_IMAGE_BYTES = 3_700_000  # Bedrock Converse image limit is 3.75 MB
MAX_FIX_ROUNDS = 3


class Timings:
    def __init__(self):
        self.ms: dict[str, float] = {}
        self._t0 = time.perf_counter()

    @contextmanager
    def stage(self, name: str):
        t = time.perf_counter()
        try:
            yield
        finally:
            self.ms[name] = self.ms.get(name, 0.0) + (time.perf_counter() - t) * 1000

    def add(self, name: str, ms: float):
        self.ms[name] = self.ms.get(name, 0.0) + ms

    def dump(self) -> dict:
        d = {f"{k}_ms": int(round(v)) for k, v in self.ms.items()}
        d["total_ms"] = int(round((time.perf_counter() - self._t0) * 1000))
        return d


# ------------------------------------------------------------------ image

def _sniff(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    return None


def decode_image(b64: str) -> tuple[bytes, str]:
    if not isinstance(b64, str) or not b64:
        raise AppError("NO_IMAGE", "No image was provided.", 400)

    if b64.startswith("data:"):
        b64 = b64.split(",", 1)[-1]

    try:
        data = base64.b64decode(b64, validate=False)
    except Exception as e:
        raise AppError(
            "BAD_IMAGE",
            "The image data could not be decoded.",
            400
        ) from e

    fmt = _sniff(data)

    if fmt is None:
        raise AppError(
            "BAD_IMAGE",
            "This file is not a valid PNG, JPEG, WEBP or GIF image.",
            400
        )

    if len(data) > MAX_IMAGE_BYTES:
        raise AppError(
            "IMAGE_TOO_LARGE",
            f"The image is {len(data) / 1e6:.1f} MB; the limit is 3.7 MB. Resize or compress it.",
            413
        )

    return data, fmt


def _store_upload(data: bytes, fmt: str, digest: str, out: dict):
    bucket = os.environ.get("UPLOAD_BUCKET")
    if not bucket:
        return
    try:
        import boto3
        boto3.client("s3").put_object(Bucket=bucket, Key=f"uploads/{digest}.{fmt}", Body=data,
                                      ContentType=f"image/{fmt}", ServerSideEncryption="AES256")
        out["stored"] = True
    except Exception as e:  # never fail the analysis because of the archive copy
        out["error"] = str(e)


# ------------------------------------------------------------------ analyze

def analyze(body: dict) -> dict:
    t = Timings()
    with t.stage("image_decode"):
        data, fmt = decode_image(body.get("image_base64"))
    digest = hashlib.sha256(data).hexdigest()
    model = os.environ.get("BEDROCK_MODEL_ID", "none")
    key = f"analysis:{digest}:{hashlib.sha1(bedrock_client.prompt('analyze').encode()).hexdigest()[:8]}:{model}"
    raw, source = None, "bedrock"
    if not body.get("force"):
        cached = store.get(key)
        if cached:
            raw, source = cached, "cache"
    upload: dict = {}
    if raw is None:
        fixture = os.environ.get("ANALYSIS_FIXTURE")
        if fixture:
            with t.stage("image_analysis"):
                with open(fixture, encoding="utf-8") as fh:
                    raw = json.load(fh)
            source = "fixture"
        elif bedrock_client.bedrock_enabled():
            th = threading.Thread(target=_store_upload, args=(data, fmt, digest, upload), daemon=True)
            th.start()  # archive copy runs in parallel with the model call
            with t.stage("image_analysis"):
                raw = bedrock_client.analyze_image(data, fmt)
            th.join(timeout=2)
            store.put(key, raw)
        else:
            raise AppError("BEDROCK_NOT_CONFIGURED",
                           "Bedrock is not configured. Set BEDROCK_MODEL_ID (and AWS credentials/region). See README.", 503)
    with t.stage("architecture_validation"):
        arch = normalize_architecture(raw)
        if not arch["services"]:
            raise AppError("NO_COMPONENTS", "No AWS components could be detected in this image. Try a clearer or higher-resolution diagram.",
                           422, retryable=False, details={"image_quality": arch["image_quality"], "notes": arch["image_quality_notes"]})
        issues = evaluate_architecture(arch)
    return {"analysis_id": digest[:16], "source": source, "model": model if source != "fixture" else "fixture",
            "stored_in_s3": bool(upload.get("stored")), "architecture": arch, "issues": issues,
            "blocking": [i["id"] for i in blocking_issues(issues)], "timings": t.dump()}


# ------------------------------------------------------------------ refine / patch

def _summary(arch: dict) -> dict:
    return {"components": [{"id": s["id"], "type": s["type"], "label": s["label"], "tier": s["tier"]} for s in arch["services"]],
            "connections": [[c["from"], c["to"]] for c in arch["connections"]],
            "availability_zones": arch["network"]["availability_zones"]}


def interpret_text(arch: dict, text: str) -> tuple[list[dict], list[str], str | None, list[str]]:
    """free text -> (ops, unmapped, interpreter, warnings)"""
    text = (text or "").strip()

    if not text:
        return [], [], None, []

    warnings: list[str] = []

    if bedrock_client.bedrock_enabled():
        try:
            res = bedrock_client.interpret_refinement(_summary(arch), text)

            ops = res.get("ops") if isinstance(res.get("ops"), list) else []

            unmapped = (
                [str(u) for u in res.get("unmapped", [])]
                if isinstance(res.get("unmapped"), list)
                else []
            )

            return ops, unmapped, "bedrock", warnings

        except AppError as e:
            warnings.append(
                f"AI interpretation failed ({e.code}); "
                "used the built-in rule interpreter instead."
            )

        except Exception as e:
            warnings.append(
                f"AI interpretation failed ({type(e).__name__}); "
                "used the built-in rule interpreter instead."
            )

    ops, unmapped = interpret(arch, text)

    return ops, unmapped, "rules", warnings


def _revalidate(arch: dict, t: Timings) -> list[dict]:
    with t.stage("architecture_validation"):
        return evaluate_architecture(arch)


def refine(body: dict) -> dict:
    t = Timings()
    arch = load_architecture(body.get("architecture"))
    options = [o for o in body.get("options", []) if o in OPTION_IDS]
    text = str(body.get("text") or "")[:2000]
    with t.stage("refinement"):
        ops = options_to_ops(arch, options)
        text_ops, unmapped, interpreter, warnings = interpret_text(arch, text)
        arch, applied, rejected = apply_ops(arch, ops + text_ops)
    issues = _revalidate(arch, t)
    return {"architecture": arch, "issues": issues, "applied": applied, "rejected": rejected, "unmapped": unmapped,
            "interpreter": interpreter, "warnings": warnings, "blocking": [i["id"] for i in blocking_issues(issues)],
            "timings": t.dump()}


def patch(body: dict) -> dict:
    t = Timings()
    arch = load_architecture(body.get("architecture"))
    ops = body.get("ops")
    if not isinstance(ops, list) or len(ops) > 50:
        raise AppError("BAD_OPS", "ops must be a list of at most 50 operations.", 400)
    arch, applied, rejected = apply_ops(arch, ops)
    issues = _revalidate(arch, t)
    return {"architecture": arch, "issues": issues, "applied": applied, "rejected": rejected,
            "blocking": [i["id"] for i in blocking_issues(issues)], "timings": t.dump()}


def revalidate(body: dict) -> dict:
    t = Timings()
    arch = load_architecture(body.get("architecture"))
    issues = _revalidate(arch, t)
    return {"architecture": arch, "issues": issues, "blocking": [i["id"] for i in blocking_issues(issues)], "timings": t.dump()}


# ------------------------------------------------------------------ generate

def _options(body: dict) -> dict:
    o = body.get("options") or {}
    formats = [f for f in o.get("formats", ["cloudformation", "cdk"]) if f in ("cloudformation", "cdk")]
    if not formats:
        raise AppError("NO_FORMAT", "Select at least one output format (CloudFormation and/or CDK).", 400)
    region = o.get("region") or "us-east-1"
    if region not in REGIONS:
        raise AppError("BAD_REGION", f"Unsupported region '{region}'.", 400)
    env = o.get("environment") or "production"
    if env not in ENVIRONMENTS:
        raise AppError("BAD_ENV", f"Environment must be one of {', '.join(ENVIRONMENTS)}.", 400)
    return {"formats": formats, "region": region, "environment": env, "prefix": str(o.get("prefix") or "")[:60],
            "security": [x for x in o.get("security", []) if x in OPTION_IDS], "extra": str(o.get("extra") or "")[:2000]}


def generate(body: dict) -> dict:
    t = Timings()
    opts = _options(body)
    overrides = [str(x) for x in body.get("overrides", [])]
    arch = load_architecture(body.get("architecture"))
    with t.stage("requirements"):
        ops = options_to_ops(arch, opts["security"])
        text_ops, unmapped, interpreter, warnings = interpret_text(arch, opts["extra"])
        arch, applied, rejected = apply_ops(arch, ops + text_ops)
    issues = _revalidate(arch, t)
    block = blocking_issues(issues, overrides)
    if block:
        raise AppError("ARCH_BLOCKED", f"{len(block)} critical issue(s) must be fixed or explicitly overridden before code can be generated.",
                       409, details={"issues": [{"id": i["id"], "problem": i["problem"]} for i in block]})
    with t.stage("code_generation"):
        plan = Plan(arch, opts)
        outputs = {}
        if "cloudformation" in opts["formats"]:
            files = [{"path": "template.yaml", "language": "yaml", "content": cfn_gen.generate(plan)}]
            outputs["cloudformation"] = {"files": files, "meta": guide.meta_cfn(plan, files)}
        if "cdk" in opts["formats"]:
            files = cdk_gen.generate(plan)
            outputs["cdk"] = {"files": files, "meta": guide.meta_cdk(plan, files)}
    skipped = [s["label"] for s in arch["services"] if s["type"] not in ("alb", "ec2", "rds", "s3", "lambda", "dynamodb", "sqs", "sns", "internet")]
    notes = []
    for s in arch["services"]:
        if s["type"] == "s3" and s["properties"].get("public") is True:
            notes.append(f"{s['label']}: public access stays BLOCKED in the generated code (this tool never generates public buckets), even though the override was accepted.")
        if s["properties"].get("encrypted") is False and s["type"] in ("s3", "rds", "dynamodb", "sqs", "sns"):
            notes.append(f"{s['label']}: encryption at rest is always enabled in generated code, regardless of the diagram.")
        if s["type"] == "rds" and plan.tier[s["id"]] == "public":
            notes.append(f"{s['label']}: generated as PUBLICLY ACCESSIBLE in a public subnet because you explicitly overrode the critical issue.")
    if plan.az_count != arch["network"]["availability_zones"]:
        notes.append(f"Availability Zones raised to {plan.az_count}: load balancers and RDS subnet groups require at least two.")
    return {"architecture": arch, "issues": issues, "applied": applied, "rejected": rejected, "unmapped": unmapped,
            "interpreter": interpreter, "warnings": warnings, "outputs": outputs, "skipped_components": skipped, "notes": notes,
            "options": opts, "timings": t.dump()}


# ------------------------------------------------------------------ verify

_OVERRIDE_MAP = {"RDS-PUBLIC": ["SEC-RDS-PUBLIC"], "S3-PUBLIC": ["SEC-S3-PUBLIC"], "ENC-DISABLED": ["SEC-RDS-ENC", "SEC-S3-ENC"]}


def expand_overrides(overrides) -> set[str]:
    """An overridden architecture issue also covers the matching finding in the generated code."""
    out = set()
    for o in overrides or []:
        o = str(o)
        out.add(o)
        code, _, comp = o.partition(":")
        for c in _OVERRIDE_MAP.get(code, []):
            out.add(f"{c}:{comp}")
    return out

def _check(fmt: str, files: dict[str, str], arch: dict) -> list[dict]:
    if fmt == "cloudformation":
        r = validate_cfn(files.get("template.yaml", ""), arch)
        checks, findings, doc = r["checks"], r["findings"], r.get("doc")
        pol = code_rules.evaluate_cfn(doc) if doc else []
    else:
        r = validate_cdk(files, arch)
        checks, findings = r["checks"], r["findings"]
        pol = code_rules.evaluate_cdk(files)
    for f in findings:
        f.setdefault("key", f"{f['code']}:{f.get('component') or '-'}")
    return checks, findings + pol


def _verify_format(fmt: str, files: list[dict], arch: dict, overrides: set[str], allow_ai: bool) -> dict:
    cur = {f["path"]: f["content"] for f in files}
    fix_log: list[dict] = []
    checks, findings = _check(fmt, cur, arch)
    round_no = 0
    while round_no < MAX_FIX_ROUNDS:
        blocking = [f for f in findings if f["severity"] == "critical" and f["key"] not in overrides]
        if not blocking:
            break
        round_no += 1
        applied: list[str] = []
        if fmt == "cloudformation":
            new, applied = fixer.fix_cfn(cur["template.yaml"], blocking, overrides)
            cur["template.yaml"] = new
        else:
            cur, applied = fixer.fix_cdk(cur, blocking, overrides)
        how = "rules"
        if not applied and allow_ai and bedrock_client.bedrock_enabled():
            try:
                res = bedrock_client.ai_fix_code(cur, blocking)
                new_files = res.get("files") if isinstance(res.get("files"), dict) else {}
                changed = {k: v for k, v in new_files.items() if isinstance(v, str) and k in cur and v != cur[k]}
                if changed:
                    cur.update(changed)
                    applied, how = [f"AI corrected {', '.join(changed)}: {res.get('explanation', '')}".strip()], "ai"
            except AppError as e:
                fix_log.append({"round": round_no, "how": "ai", "applied": [], "note": f"AI fix unavailable: {e.code}"})
        if not applied:
            break
        fix_log.append({"round": round_no, "how": how, "applied": applied, "fixed_codes": sorted({f['code'] for f in blocking})})
        checks, findings = _check(fmt, cur, arch)
    blocking = [f for f in findings if f["severity"] == "critical" and f["key"] not in overrides]
    out_files = [{**f, "content": cur.get(f["path"], f["content"])} for f in files]
    return {"files": out_files, "verified": not blocking, "checks": checks,
            "findings": [dict(f, overridden=f["key"] in overrides) for f in findings], "fix_log": fix_log,
            "rounds": round_no, "blocking": [f["key"] for f in blocking]}


def _security_report(arch: dict, plan: Plan, findings: list[dict]) -> dict:
    by = lambda prefix: [f for f in findings if f["code"].startswith(prefix)]
    def status(fs, applicable=True):
        if not applicable:
            return "n/a"
        if any(f["severity"] == "critical" for f in fs):
            return "fail"
        return "warn" if fs else "pass"
    p = plan
    data_svcs = p.by_type["s3"] or p.by_type["rds"] or p.by_type["dynamodb"] or p.by_type["sqs"] or p.by_type["sns"]
    rows = [
        ("IAM least privilege", status(by("SEC-IAM"), bool(p.by_type["ec2"] or p.by_type["lambda"])), "Roles are generated per component with actions limited to the connected resource ARNs."),
        ("Encryption at rest", status([f for f in findings if f["code"] in ("SEC-S3-ENC", "SEC-RDS-ENC", "SEC-EBS-ENC", "SEC-DDB-ENC", "SEC-SQS-ENC")], bool(data_svcs or p.by_type["ec2"])), "S3, RDS, EBS, DynamoDB and SQS encryption checked in the generated code."),
        ("Encryption in transit", "warn" if p.by_type["alb"] and not p.https else "pass" if (p.by_type["alb"] or p.by_type["s3"] or p.by_type["sqs"]) else "n/a",
         "S3/SQS deny non-TLS requests. " + ("HTTPS listener with redirect." if p.https else ("The load balancer serves HTTP only (enable HTTPS/TLS)." if p.by_type["alb"] else ""))),
        ("Private database placement", status(by("SEC-RDS-PUBLIC"), bool(p.by_type["rds"])), "RDS must not be publicly accessible."),
        ("Security groups", status(by("SEC-SG"), p.has_vpc), "Only load balancers accept internet traffic, and only on 80/443; other tiers accept traffic from their upstream security group."),
        ("Public exposure", "warn" if any(p.tier[s["id"]] == "public" for s in p.by_type["ec2"] + p.by_type["rds"]) else "pass" if p.has_vpc else "n/a",
         "Only the load balancer is internet-facing." ),
        ("S3 public access", status(by("SEC-S3-PUBLIC") + by("SEC-S3-POLICY"), bool(p.by_type["s3"])), "Block Public Access is enabled on every bucket."),
        ("Logging", "pass" if p.logging else "warn", "VPC flow logs / RDS log exports enabled." if p.logging else "Logging requirement is off: no flow logs or database log exports."),
        ("Backups", "n/a" if not (p.by_type["rds"] or p.by_type["dynamodb"] or p.by_type["s3"]) else status(by("SEC-RDS-BACKUP")) if p.by_type["rds"] else "pass",
         "RDS automated backups; DynamoDB PITR and S3 versioning when backups/production."),
        ("Secrets handling", status(by("SEC-SECRET"), bool(p.by_type["rds"])), "The database password is generated and stored in Secrets Manager; nothing secret is in the template."),
    ]
    return {
        "deterministic": [{"category": c, "status": s, "detail": d, "source": "deterministic"} for c, s, d in rows],
        "findings": [f for f in findings if f["code"].startswith("SEC-")],
        "ai_advisory": [{"severity": i["severity"], "component": i.get("component"), "message": i["message"]}
                        for k in ("security_findings", "warnings", "recommendations", "ambiguities") for i in arch.get(k, [])],
        "user_requirements": [k for k in OPTION_IDS if arch["requirements"].get(k)] ,
        "user_notes": arch["requirements"]["notes"],
        "disclaimer": ("These checks are rule-based and cover the listed categories only. AI-generated or rule-generated infrastructure "
                       "is not automatically secure - review it, run cdk synth / cfn-lint, and follow your organisation's security review before production use."),
    }


def verify(body: dict) -> dict:
    t = Timings()
    arch = load_architecture(body.get("architecture"))
    outputs_in = body.get("outputs")
    if not isinstance(outputs_in, dict) or not outputs_in:
        raise AppError("NO_OUTPUTS", "No generated code was provided to verify.", 400)
    overrides = expand_overrides(body.get("overrides", []))
    opts = _options({"options": body.get("options") or {"formats": list(outputs_in)}})
    plan = Plan(arch, opts)
    results = {}
    with t.stage("final_validation"):
        jobs = {}
        with ThreadPoolExecutor(max_workers=2) as ex:
            for fmt, out in outputs_in.items():
                if fmt in ("cloudformation", "cdk") and isinstance(out, dict) and isinstance(out.get("files"), list):
                    jobs[fmt] = ex.submit(_verify_format, fmt, out["files"], arch, overrides, bool(body.get("allow_ai", True)))
            for fmt, job in jobs.items():
                results[fmt] = job.result()
    for fmt, r in results.items():
        r["meta"] = (guide.meta_cfn if fmt == "cloudformation" else guide.meta_cdk)(plan, r["files"])
    all_findings = [f for r in results.values() for f in r["findings"]]
    return {"outputs": results, "verified": all(r["verified"] for r in results.values()),
            "security_report": _security_report(arch, plan, all_findings), "timings": t.dump()}
