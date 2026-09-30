"""Derived facts shared by the CloudFormation and CDK generators."""
from __future__ import annotations

import re

from ..architecture import SUPPORTED_TYPES
from ..topology import COMPUTE, effective_tier

ENVIRONMENTS = ("development", "staging", "production")
REGIONS = [
    "us-east-1", "us-east-2", "us-west-1", "us-west-2", "ap-south-1", "ap-south-2", "ap-southeast-1",
    "ap-southeast-2", "ap-northeast-1", "ap-northeast-2", "ca-central-1", "eu-central-1", "eu-west-1",
    "eu-west-2", "eu-west-3", "eu-north-1", "sa-east-1",
]
SIZES = {"development": "micro", "staging": "small", "production": "medium"}
DB_PORTS = {"postgres": 5432, "mysql": 3306, "mariadb": 3306}
DEFAULT_CIDR = "10.0.0.0/16"

RESOURCE_TYPE_FOR = {
    "alb": "AWS::ElasticLoadBalancingV2::LoadBalancer", "ec2": "AWS::EC2::Instance",
    "rds": "AWS::RDS::DBInstance", "s3": "AWS::S3::Bucket", "lambda": "AWS::Lambda::Function",
    "dynamodb": "AWS::DynamoDB::Table", "sqs": "AWS::SQS::Queue", "sns": "AWS::SNS::Topic",
}


def sg_desc(label: str) -> str:
    """Security-group descriptions only accept a limited ASCII character set."""
    clean = re.sub(r"[^a-zA-Z0-9. _\-:/()#,@\[\]+=&;{}!$*]", "", str(label)).strip() or "component"
    return ("Security group for " + clean)[:250]


def pascal(text: str) -> str:
    parts = [p for p in re.split(r"[^A-Za-z0-9]+", text) if p]
    out = "".join(p[:1].upper() + p[1:] for p in parts) or "Component"
    return out if out[0].isalpha() else "C" + out


def camel(text: str) -> str:
    p = pascal(text)
    return p[0].lower() + p[1:]


class Plan:
    def __init__(self, arch: dict, options: dict):
        self.arch = arch
        self.options = options
        self.env = options.get("environment") if options.get("environment") in ENVIRONMENTS else "production"
        self.region = options.get("region") if options.get("region") in REGIONS else "us-east-1"
        prefix = re.sub(r"[^a-z0-9-]+", "-", str(options.get("prefix") or "").lower()).strip("-")
        self.prefix = prefix or f"syntaxai-{self.env}"
        self.stack_name = self.prefix if len(self.prefix) <= 128 else self.prefix[:128]
        self.req = arch["requirements"]
        self.services = [s for s in arch["services"] if s["type"] in SUPPORTED_TYPES and s["type"] != "internet"]
        self.by_type = {t: [s for s in self.services if s["type"] == t] for t in SUPPORTED_TYPES}
        self.sid = {s["id"]: s for s in self.services}
        self.tier = {s["id"]: effective_tier(s) for s in self.services}

        in_vpc = [s for s in self.services if self.tier[s["id"]] is not None]
        self.has_vpc = bool(in_vpc)
        wants = arch["network"]["availability_zones"]
        self.az_count = max(wants, 2 if (self.by_type["alb"] or self.by_type["rds"]) else 1)
        self.az_count = min(3, max(1, self.az_count))
        self.private_egress = any(self.tier[s["id"]] == "private" and s["type"] in COMPUTE for s in self.services)
        self.needs_private = any(self.tier[s["id"]] == "private" for s in self.services)
        self.needs_public = any(self.tier[s["id"]] == "public" for s in self.services) or self.private_egress
        self.ha = bool(self.req["multi_az"]) and not self.req["cost_optimization"]
        self.nat_count = (self.az_count if self.ha else 1) if self.private_egress else 0
        cidr = arch["network"].get("vpc_cidr")
        self.cidr = DEFAULT_CIDR
        if cidr and re.fullmatch(r"\d{1,3}(\.\d{1,3}){3}/(1[6-9]|20)", cidr) and all(int(o) < 256 for o in cidr.split("/")[0].split(".")):
            self.cidr = cidr
        self.https = bool(self.req["https_tls"]) and bool(self.by_type["alb"])
        self.logging = bool(self.req["cloudwatch_logging"])
        self.monitoring = bool(self.req["monitoring"])
        self.backups = bool(self.req["backups"])
        self.prod = self.env == "production"
        self.size = SIZES[self.env]

    # connections between supported components
    def conns(self):
        for c in self.arch["connections"]:
            a, b = self.sid.get(c["from"]), self.sid.get(c["to"])
            if a and b:
                yield a, b

    def db_engine(self, svc: dict) -> str:
        return svc["properties"].get("engine") or "postgres"

    def db_port(self, svc: dict) -> int:
        return DB_PORTS[self.db_engine(svc)]

    def rds_multi_az(self, svc: dict) -> bool:
        return bool(svc["properties"].get("multi_az")) or bool(self.req["multi_az"])

    def rds_backup_days(self, svc: dict) -> int:
        d = svc["properties"].get("backup_retention") or 0
        if d == 0 and (self.backups or self.prod):
            d = 7
        return d

    def alb_targets(self, alb: dict) -> list[dict]:
        return [b for a, b in self.conns() if a["id"] == alb["id"] and b["type"] == "ec2"]

    def clients_of(self, svc: dict, types=COMPUTE) -> list[dict]:
        return [a for a, b in self.conns() if b["id"] == svc["id"] and a["type"] in types]
