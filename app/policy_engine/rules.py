"""Deterministic architecture rules.

Every issue carries `source`:
  - "deterministic": produced by these rules (can block generation when critical)
  - "ai":            advisory findings reported by the vision model (never block)
"""
from __future__ import annotations

from ..architecture import SUPPORTED_TYPES, TYPE_LABELS, service_by_id
from ..topology import COMPUTE, SUPPORTED_CONNECTIONS, effective_tier, incoming, outgoing

SEV_ORDER = {"critical": 0, "warning": 1, "recommendation": 2, "valid": 3}


def _issue(code, severity, component, problem, reason, suggestion, fixes=None, editable=True, source="deterministic"):
    return {
        "id": f"{code}:{component or '-'}",
        "code": code, "severity": severity, "source": source, "component": component,
        "problem": problem, "reason": reason, "suggestion": suggestion,
        "fixes": fixes or [], "editable": editable,
    }


def evaluate_architecture(arch: dict) -> list[dict]:
    issues: list[dict] = []
    svcs = arch["services"]
    req = arch["requirements"]
    net = arch["network"]
    azs = net["availability_zones"]
    by_type: dict[str, list[dict]] = {}
    for s in svcs:
        by_type.setdefault(s["type"], []).append(s)
    label = lambda s: f"{s['label']} ({s['id']})" if s["label"].lower() != s["id"] else s["label"]

    # ---- image quality
    if arch.get("image_quality") == "poor":
        issues.append(_issue("IMG-QUALITY", "warning", None, "The image is unclear or low quality",
                             arch.get("image_quality_notes") or "Components and arrows may have been misread.",
                             "Review every detected component carefully, or upload a clearer image.", editable=False))

    # ---- components: ambiguity / unsupported / duplicates
    seen_labels: dict[tuple, str] = {}
    for s in svcs:
        sid = s["id"]
        if s["type"] == "other" or s["confidence"] < 0.6:
            issues.append(_issue("AMBIG-COMPONENT", "warning", sid,
                                 f"{label(s)} could not be identified with confidence ({round(s['confidence'] * 100)}%)",
                                 "The icon or label is unclear, so the AWS service is uncertain. It will not be silently assumed.",
                                 "Use Edit to set the correct service type, or remove the component."))
        elif s["type"] not in SUPPORTED_TYPES:
            issues.append(_issue("UNSUPPORTED-COMPONENT", "warning", sid,
                                 f"{TYPE_LABELS.get(s['type'], s['type'])} is not supported for IaC generation",
                                 "This version cannot generate code for this service; it will be skipped.",
                                 "Remove it from the architecture (it will not appear in the code) or change its type.",
                                 fixes=[{"op": "remove_service", "target": sid}]))
        key = (s["type"], s["label"].strip().lower())
        if key in seen_labels:
            issues.append(_issue("DUP-COMPONENT", "warning", sid,
                                 f"{label(s)} looks like a duplicate of {seen_labels[key]}",
                                 "Two components share the same type and name.",
                                 "Remove the duplicate if it is the same resource drawn twice.",
                                 fixes=[{"op": "remove_service", "target": sid}]))
        else:
            seen_labels[key] = s["id"]

    # ---- network
    needs_vpc = any(s["type"] in ("ec2", "rds", "alb") for s in svcs) or any(
        s["type"] == "lambda" and s["tier"] == "private" for s in svcs)
    if needs_vpc and not net["vpc"]:
        issues.append(_issue("NET-VPC", "warning", None, "No VPC is shown, but VPC-bound resources exist",
                             "EC2, RDS and load balancers must live in a VPC with subnets.",
                             "A new VPC with public and private subnets will be generated.",
                             fixes=[{"op": "set_vpc", "value": True}]))
    if (by_type.get("alb") or by_type.get("rds")) and azs < 2:
        issues.append(_issue("NET-AZ", "warning", None, "Only one Availability Zone is defined",
                             "Application Load Balancers and RDS subnet groups need subnets in at least two AZs.",
                             "Use two Availability Zones.", fixes=[{"op": "set_azs", "value": 2}]))

    # ---- placement / exposure
    for s in svcs:
        sid, t = s["id"], s["type"]
        fronted = "alb" in [service_by_id(arch, i)["type"] for i in incoming(arch, sid) if service_by_id(arch, i)]
        if t == "rds":
            if s["properties"].get("public") is True or s["tier"] == "public":
                issues.append(_issue("RDS-PUBLIC", "critical", sid, f"{label(s)} is publicly reachable / in a public subnet",
                                     "Database resources should normally be isolated from direct public access.",
                                     "Move the database to a private subnet and disable public access.",
                                     fixes=[{"op": "set_property", "target": sid, "key": "public", "value": False},
                                            {"op": "set_tier", "target": sid, "tier": "private"}]))
            elif s["tier"] == "unknown":
                issues.append(_issue("PLACEMENT-UNKNOWN", "warning", sid, f"Subnet placement of {label(s)} is not shown",
                                     "Without placement the generator would have to guess.",
                                     "Place the database in a private subnet.",
                                     fixes=[{"op": "set_tier", "target": sid, "tier": "private"}]))
        elif t in COMPUTE:
            if s["tier"] == "unknown":
                issues.append(_issue("PLACEMENT-UNKNOWN", "warning", sid, f"Subnet placement of {label(s)} is not shown",
                                     "The diagram does not say whether it is public or private.",
                                     "Place it in a private subnet (outbound access through a NAT gateway).",
                                     fixes=[{"op": "set_tier", "target": sid, "tier": "private"}]))
            elif s["tier"] == "public" and fronted:
                issues.append(_issue("EC2-PUBLIC-BEHIND-ALB", "recommendation", sid,
                                     f"{label(s)} is in a public subnet although a load balancer fronts it",
                                     "Targets behind a load balancer do not need direct internet exposure.",
                                     "Move it to a private subnet.",
                                     fixes=[{"op": "set_tier", "target": sid, "tier": "private"}]))
        if t == "s3" and s["properties"].get("public") is True:
            issues.append(_issue("S3-PUBLIC", "critical", sid, f"{label(s)} is configured as publicly accessible",
                                 "Public buckets are a leading cause of data exposure.",
                                 "Block all public access.",
                                 fixes=[{"op": "set_property", "target": sid, "key": "public", "value": False}]))

    # ---- encryption / backups / HA
    for s in svcs:
        sid, t = s["id"], s["type"]
        if t in ("s3", "rds", "dynamodb", "sqs", "sns"):
            enc = s["properties"].get("encrypted")
            fix = [{"op": "set_property", "target": sid, "key": "encrypted", "value": True}]
            if enc is False:
                issues.append(_issue("ENC-DISABLED", "critical" if t in ("s3", "rds") else "warning", sid,
                                     f"Encryption is disabled for {label(s)}", "Data at rest should be encrypted.",
                                     "Enable encryption at rest.", fixes=fix))
            elif enc is None:
                issues.append(_issue("ENC-UNSPECIFIED", "warning", sid, f"Encryption for {label(s)} is not specified",
                                     "The diagram does not state whether data at rest is encrypted. "
                                     "Generated code encrypts by default, but the intent should be explicit.",
                                     "Enable encryption at rest.", fixes=fix))
        if t == "rds":
            if not (s["properties"].get("backup_retention") or 0):
                issues.append(_issue("RDS-BACKUP", "warning", sid, f"Automated backups are not configured for {label(s)}",
                                     "Without backups a failure or bad change can cause permanent data loss.",
                                     "Retain automated backups for 7 days.",
                                     fixes=[{"op": "set_property", "target": sid, "key": "backup_retention", "value": 7}]))
            if s["properties"].get("multi_az") is not True:
                issues.append(_issue("RDS-MULTIAZ", "recommendation", sid, f"{label(s)} is not Multi-AZ",
                                     "A single-AZ database has no automatic failover.",
                                     "Enable Multi-AZ (uses two Availability Zones).",
                                     fixes=[{"op": "set_property", "target": sid, "key": "multi_az", "value": True},
                                            {"op": "set_azs", "value": max(2, azs)}]))
            clients = [i for i in incoming(arch, sid) if (service_by_id(arch, i) or {}).get("type") in COMPUTE]
            if not clients:
                issues.append(_issue("SG-NO-CLIENT", "warning", sid, f"No compute component connects to {label(s)}",
                                     "Security groups only allow traffic from connected components, so nothing could reach the database.",
                                     "Add a connection from the EC2/Lambda component that uses it (Connections panel).",
                                     editable=False))
        if t == "alb":
            targets = [i for i in outgoing(arch, sid) if (service_by_id(arch, i) or {}).get("type") == "ec2"]
            if not targets:
                issues.append(_issue("ALB-NO-TARGET", "warning", sid, f"{label(s)} has no EC2 target connection",
                                     "A load balancer without targets returns errors.",
                                     "Add a connection from the load balancer to its EC2 instances.", editable=False))

    # ---- connections
    ids = {s["id"] for s in svcs}
    for c in arch["connections"]:
        f, t_ = c["from"], c["to"]
        cid = f"{f}->{t_}"
        if f not in ids or t_ not in ids or c.get("unresolved"):
            issues.append(_issue("CONN-INVALID", "critical", cid, f"Connection {f} -> {t_} refers to an unknown component",
                                 "An endpoint of this arrow could not be matched to a detected component.",
                                 "Remove the connection or add the missing component.",
                                 fixes=[{"op": "remove_connection", "from": f, "to": t_}], editable=False))
            continue
        fs, ts = service_by_id(arch, f), service_by_id(arch, t_)
        pair = (fs["type"], ts["type"])
        if fs["type"] == "internet" and ts["type"] == "rds":
            issues.append(_issue("RDS-INTERNET", "critical", cid, f"Internet connects directly to {label(ts)}",
                                 "Exposing a database directly to the internet is an invalid, insecure relationship.",
                                 "Remove the connection; reach the database through the application tier.",
                                 fixes=[{"op": "remove_connection", "from": f, "to": t_}], editable=False))
        elif pair == ("internet", "ec2"):
            fix = [{"op": "add_service", "type": "alb", "id": "alb", "label": "Application Load Balancer", "tier": "public"},
                   {"op": "add_connection", "from": f, "to": "alb"}, {"op": "add_connection", "from": "alb", "to": t_},
                   {"op": "remove_connection", "from": f, "to": t_}]
            if "alb" in ids:
                fix = [{"op": "add_connection", "from": f, "to": "alb"}, {"op": "add_connection", "from": "alb", "to": t_},
                       {"op": "remove_connection", "from": f, "to": t_}]
            issues.append(_issue("EC2-DIRECT-INTERNET", "warning", cid, f"{label(ts)} is exposed directly to the internet",
                                 "Instances normally sit behind a load balancer so only ports 80/443 are public.",
                                 "Put an Application Load Balancer in front of it.", fixes=fix, editable=False))
        elif fs["type"] in ("rds", "s3", "dynamodb") and ts["type"] in COMPUTE:
            issues.append(_issue("CONN-DIRECTION", "warning", cid, f"{label(fs)} appears to initiate a connection to {label(ts)}",
                                 "Storage and database services do not call compute; the arrow is probably reversed.",
                                 "Reverse the connection.", fixes=[{"op": "reverse_connection", "from": f, "to": t_}], editable=False))
        elif pair not in SUPPORTED_CONNECTIONS and "other" not in pair and fs["type"] in SUPPORTED_TYPES and ts["type"] in SUPPORTED_TYPES:
            issues.append(_issue("CONN-UNSUPPORTED", "warning", cid,
                                 f"Connection {label(fs)} -> {label(ts)} is not translated into code",
                                 "This relationship has no IaC mapping in this version, so no permission or network rule is generated for it.",
                                 "Remove it, or add the wiring manually after generation.",
                                 fixes=[{"op": "remove_connection", "from": f, "to": t_}], editable=False))

    # ---- IAM / SG confirmations (valid)
    for c in arch["connections"]:
        fs, ts = service_by_id(arch, c["from"]), service_by_id(arch, c["to"])
        if not fs or not ts:
            continue
        if fs["type"] in COMPUTE and ts["type"] in ("s3", "dynamodb", "sqs", "sns", "rds", "lambda"):
            issues.append(_issue("IAM-SCOPED", "valid", f"{fs['id']}->{ts['id']}",
                                 f"IAM: {label(fs)} gets access to {label(ts)} only",
                                 "A dedicated role is generated with actions limited to this one resource ARN.",
                                 "No action needed.", editable=False))
        if ts["type"] == "rds" and fs["type"] in COMPUTE:
            issues.append(_issue("SG-SCOPED", "valid", f"{fs['id']}->{ts['id']}",
                                 f"Security group: only {label(fs)} can reach {label(ts)}",
                                 "The database security group allows the DB port from the client's security group only.",
                                 "No action needed.", editable=False))

    # ---- requirements-driven recommendations
    if not req["cloudwatch_logging"]:
        issues.append(_issue("LOG-OFF", "recommendation", None, "Logging is not enabled",
                             "VPC flow logs and database logs help with auditing and incident response.",
                             "Enable CloudWatch logging.",
                             fixes=[{"op": "set_requirement", "key": "cloudwatch_logging", "value": True}], editable=False))
    if by_type.get("alb") and not req["https_tls"]:
        issues.append(_issue("TLS-OFF", "recommendation", None, "The load balancer will serve plain HTTP only",
                             "Traffic to the load balancer is unencrypted without a TLS listener.",
                             "Enable HTTPS (an ACM certificate ARN is supplied at deploy time).",
                             fixes=[{"op": "set_requirement", "key": "https_tls", "value": True}], editable=False))
    if by_type.get("s3"):
        issues.append(_issue("S3-BASELINE", "valid", None, "S3 baseline: public access blocked, TLS-only bucket policy",
                             "Generated buckets always block public access and deny non-TLS requests.",
                             "No action needed.", editable=False))

    # ---- AI advisory findings (never block generation)
    n = 0
    for bucket, sev_default in (("ambiguities", "warning"), ("security_findings", "warning"),
                                ("warnings", "warning"), ("recommendations", "recommendation")):
        for item in arch.get(bucket, []):
            n += 1
            sev = item["severity"] if bucket == "security_findings" else sev_default
            issues.append(_issue(f"AI-{bucket[:5].upper()}-{n}", sev, item.get("component"),
                                 item["message"], "Reported by the vision model from the image (advisory, not verified by rules).",
                                 "Review and use Edit, refinements or Ignore.", editable=bool(item.get("component")), source="ai"))
            issues[-1]["id"] = f"AI-{n}:{item.get('component') or '-'}"

    if not any(i["severity"] in ("critical", "warning") for i in issues if i["source"] == "deterministic") and svcs:
        issues.append(_issue("ARCH-OK", "valid", None, "No blocking structural problems found",
                             "All deterministic architecture rules passed.", "No action needed.", editable=False))
    issues.sort(key=lambda i: (SEV_ORDER[i["severity"]], i["id"]))
    return issues


def blocking_issues(issues: list[dict], overrides: list[str] | None = None) -> list[dict]:
    """Deterministic critical issues the user has neither fixed nor explicitly overridden."""
    ov = set(overrides or [])
    return [i for i in issues if i["source"] == "deterministic" and i["severity"] == "critical" and i["id"] not in ov]
