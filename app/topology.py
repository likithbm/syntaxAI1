"""Shared topology helpers used by the policy engine and the code generators."""
from __future__ import annotations

# (source type, destination type) pairs that the generators translate into IaC.
SUPPORTED_CONNECTIONS = {
    ("internet", "alb"), ("alb", "ec2"),
    ("ec2", "s3"), ("ec2", "dynamodb"), ("ec2", "sqs"), ("ec2", "sns"), ("ec2", "rds"), ("ec2", "lambda"),
    ("lambda", "s3"), ("lambda", "dynamodb"), ("lambda", "sqs"), ("lambda", "sns"), ("lambda", "rds"),
    ("sqs", "lambda"), ("sns", "lambda"),
    ("internet", "ec2"),  # accepted but flagged: direct exposure
}

COMPUTE = ("ec2", "lambda")


def effective_tier(svc: dict) -> str | None:
    """Where the generator will place a component: 'public', 'private' or None (not in a VPC)."""
    t = svc["type"]
    tier = svc.get("tier")
    if t == "alb":
        return "public"
    if t == "rds":
        return "public" if (svc["properties"].get("public") is True or tier == "public") else "private"
    if t == "ec2":
        return "public" if tier == "public" else "private"
    if t == "lambda":
        return "private" if tier == "private" else None
    return None


def outgoing(arch: dict, sid: str) -> list[str]:
    return [c["to"] for c in arch["connections"] if c["from"] == sid]


def incoming(arch: dict, sid: str) -> list[str]:
    return [c["from"] for c in arch["connections"] if c["to"] == sid]
