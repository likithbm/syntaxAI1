"""Deterministic auto-fixers for generated code. Each fixer handles one finding code."""
from __future__ import annotations

import re

from ..codegen.cloudformation import dump_yaml
from .cdk_validator import IMPORT_LINE
from .cfn_validator import parse


def fix_cfn(text: str, findings: list[dict], skip_keys: set[str]) -> tuple[str, list[str]]:
    doc, errs = parse(text)
    if doc is None:
        return text, []
    applied: list[str] = []
    res = doc.get("Resources") or {}
    for fnd in findings:
        if fnd.get("key") in skip_keys or not fnd.get("fixable"):
            continue
        code, comp = fnd["code"], fnd.get("component")
        targets = [(lid, r) for lid, r in res.items() if isinstance(r, dict)
                   and (comp in (lid, ((r.get("Metadata") or {}).get("SyntaxAI") or {}).get("Component")))]
        if code == "SEC-S3-PUBLIC":
            for lid, r in targets:
                r.setdefault("Properties", {})["PublicAccessBlockConfiguration"] = {
                    "BlockPublicAcls": True, "BlockPublicPolicy": True, "IgnorePublicAcls": True, "RestrictPublicBuckets": True}
                applied.append(f"{lid}: enabled S3 Block Public Access")
        elif code == "SEC-S3-ENC":
            for lid, r in targets:
                r.setdefault("Properties", {})["BucketEncryption"] = {"ServerSideEncryptionConfiguration": [
                    {"ServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}]}
                applied.append(f"{lid}: enabled default encryption (AES256)")
        elif code == "SEC-RDS-ENC":
            for lid, r in targets:
                r.setdefault("Properties", {})["StorageEncrypted"] = True
                applied.append(f"{lid}: StorageEncrypted = true")
        elif code == "SEC-RDS-PUBLIC":
            for lid, r in targets:
                r.setdefault("Properties", {})["PubliclyAccessible"] = False
                applied.append(f"{lid}: PubliclyAccessible = false")
        elif code == "CFN-DEPENDSON-MISSING":
            for lid, r in res.items():
                if isinstance(r, dict) and "DependsOn" in r:
                    deps = [r["DependsOn"]] if isinstance(r["DependsOn"], str) else list(r["DependsOn"])
                    keep = [d for d in deps if d in res]
                    if keep != deps:
                        if keep:
                            r["DependsOn"] = keep
                        else:
                            del r["DependsOn"]
                        applied.append(f"{lid}: removed DependsOn on a resource that does not exist")
    if not applied:
        return text, []
    header = "".join(l + "\n" for l in text.splitlines() if l.startswith("#") and text.startswith("#")) if text.startswith("#") else ""
    return header + dump_yaml(doc), applied


def fix_cdk(files: dict[str, str], findings: list[dict], skip_keys: set[str]) -> tuple[dict[str, str], list[str]]:
    files = dict(files)
    applied: list[str] = []
    for fnd in findings:
        if fnd.get("key") in skip_keys:
            continue
        path, code = fnd.get("file"), fnd["code"]
        if path not in files:
            continue
        src = files[path]
        if code == "CDK-IMPORT-MISSING" and fnd.get("component") in IMPORT_LINE:
            line = IMPORT_LINE[fnd["component"]]
            if line not in src:
                lines = src.split("\n")
                last = max((i for i, l in enumerate(lines) if l.startswith("import ")), default=-1)
                lines.insert(last + 1, line)
                files[path] = "\n".join(lines)
                applied.append(f"{path}: added missing import `{line}`")
        elif code == "CDK-IMPORT-UNUSED":
            m = re.search(r"'(\w+)' is never used|Import '(\w+)'", fnd["message"])
            ns = (m.group(1) or m.group(2)) if m else None
            if ns:
                new = re.sub(rf"^import \* as {ns} from '[^']+';\n", "", src, flags=re.M)
                if new != src:
                    files[path] = new
                    applied.append(f"{path}: removed unused import '{ns}'")
        elif code == "SEC-S3-PUBLIC":
            new = re.sub(r"(new s3\.Bucket\(this, '\w+', \{\n)(?![^}]*blockPublicAccess)",
                         r"\1      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,\n", src)
            if new != src:
                files[path] = new
                applied.append(f"{path}: added blockPublicAccess: BLOCK_ALL")
        elif code == "SEC-S3-TLS":
            new = re.sub(r"(new s3\.Bucket\(this, '\w+', \{\n)", r"\1      enforceSSL: true,\n", src)
            if new != src and "enforceSSL: true" not in src:
                files[path] = new
                applied.append(f"{path}: added enforceSSL: true")
        elif code == "SEC-RDS-ENC":
            new = src.replace("storageEncrypted: false", "storageEncrypted: true")
            if new != src:
                files[path] = new
                applied.append(f"{path}: storageEncrypted = true")
        elif code == "SEC-RDS-PUBLIC":
            new = src.replace("publiclyAccessible: true", "publiclyAccessible: false")
            if new != src:
                files[path] = new
                applied.append(f"{path}: publiclyAccessible = false")
    return files, applied
