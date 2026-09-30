"""Deterministic security rules applied to GENERATED code (CloudFormation dict / CDK TypeScript text)."""
from __future__ import annotations

import re

READ_ONLY_OK = re.compile(r"^(ec2:Describe|logs:|cloudwatch:PutMetricData|xray:|ecr:GetAuthorizationToken|sts:GetCallerIdentity)")


def f(code, severity, message, component=None, file="template.yaml", fixable=False):
    return {"code": code, "severity": severity, "message": message, "component": component, "file": file,
            "fixable": fixable, "source": "deterministic", "key": f"{code}:{component or '-'}"}


def _as_list(x):
    return x if isinstance(x, list) else [x] if x is not None else []


def _int(x):
    try:
        return int(x)
    except (TypeError, ValueError):
        return None


def evaluate_cfn(doc: dict) -> list[dict]:
    out = []
    res = doc.get("Resources") or {}
    # which SG ids belong to load balancers (intentionally public on 80/443)
    for lid, r in res.items():
        if not isinstance(r, dict):
            continue
        t, p = r.get("Type"), r.get("Properties") or {}
        comp = ((r.get("Metadata") or {}).get("SyntaxAI") or {}).get("Component") or lid
        if t == "AWS::S3::Bucket":
            pab = p.get("PublicAccessBlockConfiguration") or {}
            if not all(pab.get(k) is True for k in ("BlockPublicAcls", "BlockPublicPolicy", "IgnorePublicAcls", "RestrictPublicBuckets")):
                out.append(f("SEC-S3-PUBLIC", "critical", f"S3 bucket {lid} does not block all public access", comp, fixable=True))
            if not p.get("BucketEncryption"):
                out.append(f("SEC-S3-ENC", "critical", f"S3 bucket {lid} has no default encryption", comp, fixable=True))
        elif t == "AWS::S3::BucketPolicy":
            for st in _as_list((p.get("PolicyDocument") or {}).get("Statement")):
                if st.get("Effect") == "Allow" and st.get("Principal") in ("*", {"AWS": "*"}):
                    out.append(f("SEC-S3-POLICY-PUBLIC", "critical", f"Bucket policy {lid} allows access to everyone", comp))
        elif t == "AWS::RDS::DBInstance":
            if p.get("StorageEncrypted") is not True:
                out.append(f("SEC-RDS-ENC", "critical", f"RDS instance {lid} storage is not encrypted", comp, fixable=True))
            if p.get("PubliclyAccessible") is True:
                out.append(f("SEC-RDS-PUBLIC", "critical", f"RDS instance {lid} is publicly accessible", comp, fixable=True))
            if not _int(p.get("BackupRetentionPeriod")):
                out.append(f("SEC-RDS-BACKUP", "warning", f"RDS instance {lid} has automated backups disabled", comp))
            if "MasterUserPassword" in p:
                out.append(f("SEC-SECRET-INLINE", "critical", f"RDS instance {lid} embeds a master password in the template; use ManageMasterUserPassword", comp))
        elif t == "AWS::EC2::Instance":
            for bdm in _as_list(p.get("BlockDeviceMappings")):
                if (bdm.get("Ebs") or {}).get("Encrypted") is not True:
                    out.append(f("SEC-EBS-ENC", "warning", f"EC2 instance {lid} has an unencrypted EBS volume", comp))
            if (p.get("MetadataOptions") or {}).get("HttpTokens") != "required":
                out.append(f("SEC-IMDSV2", "warning", f"EC2 instance {lid} does not require IMDSv2", comp))
        elif t == "AWS::DynamoDB::Table":
            if not (p.get("SSESpecification") or {}).get("SSEEnabled"):
                out.append(f("SEC-DDB-ENC", "warning", f"DynamoDB table {lid} has no explicit server-side encryption", comp))
        elif t == "AWS::SQS::Queue":
            if not (p.get("SqsManagedSseEnabled") or p.get("KmsMasterKeyId")):
                out.append(f("SEC-SQS-ENC", "warning", f"SQS queue {lid} is not encrypted", comp))
        elif t == "AWS::EC2::SecurityGroup":
            for rule in _as_list(p.get("SecurityGroupIngress")):
                out += _sg_rule(lid, comp, rule)
        elif t == "AWS::EC2::SecurityGroupIngress":
            out += _sg_rule(lid, comp, p)
        elif t in ("AWS::IAM::Role", "AWS::IAM::Policy", "AWS::IAM::ManagedPolicy"):
            trust = p.get("AssumeRolePolicyDocument") or {}
            for st in _as_list(trust.get("Statement")):
                princ = st.get("Principal")
                if st.get("Effect") == "Allow" and (princ == "*" or (isinstance(princ, dict) and "*" in _as_list(princ.get("AWS")))):
                    out.append(f("SEC-IAM-TRUST-ANY", "critical", f"Role {lid} can be assumed by any principal", comp))
            docs = [pol.get("PolicyDocument") for pol in _as_list(p.get("Policies"))] + [p.get("PolicyDocument")]
            for d in docs:
                for st in _as_list((d or {}).get("Statement")):
                    if st.get("Effect") != "Allow":
                        continue
                    actions = [str(a) for a in _as_list(st.get("Action"))]
                    resources = _as_list(st.get("Resource"))
                    if any(a == "*" or a == "*:*" for a in actions):
                        out.append(f("SEC-IAM-ADMIN", "critical", f"{lid} grants all actions (*)", comp))
                    elif any(a.endswith(":*") for a in actions):
                        out.append(f("SEC-IAM-WILDCARD-ACTION", "warning", f"{lid} grants service-wide actions ({', '.join(a for a in actions if a.endswith(':*'))})", comp))
                    if "*" in resources and not all(READ_ONLY_OK.match(a) for a in actions):
                        out.append(f("SEC-IAM-WILDCARD-RESOURCE", "warning", f"{lid} allows actions on Resource '*'", comp))
    return out


def _sg_rule(lid, comp, rule):
    out = []
    cidr = rule.get("CidrIp") or rule.get("CidrIpv6")
    proto = str(rule.get("IpProtocol"))
    if proto == "-1" and cidr:
        out.append(f("SEC-SG-ALLOW-ALL", "critical", f"{lid} allows all protocols and ports from {cidr}", comp))
    elif cidr in ("0.0.0.0/0", "::/0"):
        lo, hi = _int(rule.get("FromPort")), _int(rule.get("ToPort"))
        if not (lo == hi and lo in (80, 443)):
            out.append(f"SEC-SG-OPEN")
            out[-1] = f("SEC-SG-OPEN", "critical", f"{lid} opens ports {lo}-{hi} to the whole internet (only 80/443 are acceptable on a load balancer)", comp)
    return out


# ---------------------------------------------------------------- CDK (text heuristics)

def evaluate_cdk(files: dict[str, str]) -> list[dict]:
    out = []
    text = "\n".join(v for k, v in files.items() if k.endswith(".ts"))
    path = next((k for k in files if k.startswith("lib/") and k.endswith(".ts")), "lib/syntax-ai-stack.ts")
    if "new s3.Bucket" in text:
        if "blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL" not in text:
            out.append(f("SEC-S3-PUBLIC", "critical", "S3 bucket does not use BlockPublicAccess.BLOCK_ALL", None, path, True))
        if "enforceSSL: true" not in text:
            out.append(f("SEC-S3-TLS", "warning", "S3 bucket does not enforce TLS (enforceSSL)", None, path))
        if "encryption:" not in text:
            out.append(f("SEC-S3-ENC", "critical", "S3 bucket has no explicit encryption", None, path))
    for m in re.finditer(r"(?:// component: (\w+)\n    )?const \w+ = new rds\.DatabaseInstance\(this, '(\w+)'(.*?)\n    \}\);", text, flags=re.S):
        body, comp = m.group(3), (m.group(1) or m.group(2))
        if "storageEncrypted: true" not in body:
            out.append(f("SEC-RDS-ENC", "critical", f"RDS {comp}: storageEncrypted is not true", comp, path))
        if "publiclyAccessible: true" in body:
            out.append(f("SEC-RDS-PUBLIC", "critical", f"RDS {comp}: publiclyAccessible is true", comp, path))
        if re.search(r"backupRetention: cdk\.Duration\.days\(0\)", body):
            out.append(f("SEC-RDS-BACKUP", "warning", f"RDS {comp}: backups disabled", comp, path))
        if "credentials:" in body and "fromGeneratedSecret" not in body:
            out.append(f("SEC-SECRET-INLINE", "critical", f"RDS {comp}: credentials must come from Secrets Manager", comp, path))
    if "new ec2.Instance" in text and "requireImdsv2: true" not in text:
        out.append(f("SEC-IMDSV2", "warning", "EC2 instance does not require IMDSv2", None, path))
    if re.search(r"actions:\s*\[[^\]]*'\*'", text) or re.search(r"actions:\s*\[[^\]]*:\*'", text):
        out.append(f("SEC-IAM-WILDCARD-ACTION", "critical", "PolicyStatement uses wildcard actions", None, path))
    if re.search(r"resources:\s*\[[^\]]*'\*'", text):
        out.append(f("SEC-IAM-WILDCARD-RESOURCE", "warning", "PolicyStatement uses Resource '*'", None, path))
    if "AdministratorAccess" in text or "PowerUserAccess" in text:
        out.append(f("SEC-IAM-ADMIN", "critical", "An administrator managed policy is attached", None, path))
    for m in re.finditer(r"(\w+)\.addIngressRule\(ec2\.Peer\.(?:anyIpv4|anyIpv6)\(\), ec2\.Port\.(\w+)\(([^)]*)\)", text):
        port = m.group(3).strip()
        if not (m.group(2) == "tcp" and port in ("80", "443")):
            out.append(f("SEC-SG-OPEN", "critical", f"{m.group(1)} opens {m.group(2)}({port}) to the internet (only 80/443 acceptable)", m.group(1), path))
    return out
