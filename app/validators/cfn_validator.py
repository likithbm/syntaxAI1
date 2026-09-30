"""CloudFormation template validation (no AWS calls, no external tools)."""
from __future__ import annotations

import re
from typing import Any

import yaml

KNOWN_SERVICES = {
    "EC2", "S3", "RDS", "IAM", "Lambda", "DynamoDB", "SQS", "SNS", "ElasticLoadBalancingV2", "ElasticLoadBalancing",
    "Logs", "CloudWatch", "SSM", "SecretsManager", "KMS", "CloudFront", "Route53", "ApiGateway", "ApiGatewayV2",
    "Cognito", "ECS", "EKS", "ECR", "ElastiCache", "EFS", "Kinesis", "Events", "StepFunctions", "AutoScaling",
    "CertificateManager", "WAFv2", "Config", "CloudTrail", "Backup", "SES", "Athena", "Glue", "Redshift",
    "OpenSearchService", "Elasticsearch", "CodeBuild", "CodePipeline", "CloudFormation", "Serverless",
}

KNOWN_TYPES = {
    "AWS::EC2::VPC", "AWS::EC2::Subnet", "AWS::EC2::InternetGateway", "AWS::EC2::VPCGatewayAttachment",
    "AWS::EC2::RouteTable", "AWS::EC2::Route", "AWS::EC2::SubnetRouteTableAssociation", "AWS::EC2::EIP",
    "AWS::EC2::NatGateway", "AWS::EC2::SecurityGroup", "AWS::EC2::SecurityGroupIngress", "AWS::EC2::SecurityGroupEgress",
    "AWS::EC2::Instance", "AWS::EC2::FlowLog", "AWS::EC2::VPCEndpoint", "AWS::EC2::LaunchTemplate", "AWS::EC2::Volume",
    "AWS::S3::Bucket", "AWS::S3::BucketPolicy", "AWS::RDS::DBInstance", "AWS::RDS::DBSubnetGroup", "AWS::RDS::DBCluster",
    "AWS::IAM::Role", "AWS::IAM::InstanceProfile", "AWS::IAM::Policy", "AWS::IAM::ManagedPolicy",
    "AWS::Lambda::Function", "AWS::Lambda::Permission", "AWS::Lambda::EventSourceMapping",
    "AWS::DynamoDB::Table", "AWS::SQS::Queue", "AWS::SQS::QueuePolicy", "AWS::SNS::Topic", "AWS::SNS::Subscription",
    "AWS::SNS::TopicPolicy", "AWS::ElasticLoadBalancingV2::LoadBalancer", "AWS::ElasticLoadBalancingV2::TargetGroup",
    "AWS::ElasticLoadBalancingV2::Listener", "AWS::ElasticLoadBalancingV2::ListenerRule",
    "AWS::Logs::LogGroup", "AWS::CloudWatch::Alarm", "AWS::SecretsManager::Secret", "AWS::KMS::Key", "AWS::KMS::Alias",
    "AWS::SSM::Parameter", "AWS::CertificateManager::Certificate", "AWS::AutoScaling::AutoScalingGroup",
    "AWS::CloudFront::Distribution", "AWS::Route53::RecordSet", "AWS::ApiGateway::RestApi",
}

PSEUDO = {"AWS::Region", "AWS::StackName", "AWS::StackId", "AWS::AccountId", "AWS::Partition", "AWS::URLSuffix",
          "AWS::NoValue", "AWS::NotificationARNs"}

REQUIRED = {
    "AWS::EC2::VPC": ["CidrBlock"], "AWS::EC2::Subnet": ["VpcId", "CidrBlock"], "AWS::EC2::SecurityGroup": ["GroupDescription"],
    "AWS::EC2::Instance": ["ImageId"], "AWS::EC2::Route": ["RouteTableId"], "AWS::EC2::SubnetRouteTableAssociation": ["SubnetId", "RouteTableId"],
    "AWS::EC2::NatGateway": ["SubnetId"], "AWS::EC2::VPCGatewayAttachment": ["VpcId"], "AWS::EC2::SecurityGroupIngress": ["IpProtocol"],
    "AWS::S3::BucketPolicy": ["Bucket", "PolicyDocument"], "AWS::RDS::DBInstance": ["DBInstanceClass"],
    "AWS::RDS::DBSubnetGroup": ["DBSubnetGroupDescription", "SubnetIds"], "AWS::IAM::Role": ["AssumeRolePolicyDocument"],
    "AWS::IAM::InstanceProfile": ["Roles"], "AWS::Lambda::Function": ["Code", "Role"],
    "AWS::Lambda::Permission": ["Action", "FunctionName", "Principal"], "AWS::Lambda::EventSourceMapping": ["FunctionName"],
    "AWS::DynamoDB::Table": ["KeySchema"], "AWS::SQS::QueuePolicy": ["PolicyDocument", "Queues"],
    "AWS::SNS::Subscription": ["Protocol", "TopicArn"], "AWS::ElasticLoadBalancingV2::TargetGroup": [],
    "AWS::ElasticLoadBalancingV2::Listener": ["DefaultActions", "LoadBalancerArn"], "AWS::CloudWatch::Alarm": ["ComparisonOperator", "EvaluationPeriods"],
    "AWS::EC2::FlowLog": ["ResourceId", "ResourceType"],
}

GETATT = {
    "AWS::S3::Bucket": {"Arn", "DomainName", "RegionalDomainName", "WebsiteURL", "DualStackDomainName"},
    "AWS::DynamoDB::Table": {"Arn", "StreamArn"}, "AWS::SQS::Queue": {"Arn", "QueueName", "QueueUrl"},
    "AWS::Lambda::Function": {"Arn", "SnapStartResponse.ApplyOn", "SnapStartResponse.OptimizationStatus"},
    "AWS::IAM::Role": {"Arn", "RoleId"}, "AWS::EC2::SecurityGroup": {"GroupId", "VpcId"},
    "AWS::EC2::VPC": {"CidrBlock", "VpcId", "DefaultSecurityGroup", "DefaultNetworkAcl"}, "AWS::EC2::EIP": {"AllocationId", "PublicIp"},
    "AWS::ElasticLoadBalancingV2::LoadBalancer": {"DNSName", "LoadBalancerFullName", "LoadBalancerName", "CanonicalHostedZoneID", "SecurityGroups", "LoadBalancerArn"},
    "AWS::ElasticLoadBalancingV2::TargetGroup": {"TargetGroupFullName", "TargetGroupName", "LoadBalancerArns"},
    "AWS::RDS::DBInstance": {"Endpoint.Address", "Endpoint.Port", "DBInstanceArn", "MasterUserSecret.SecretArn", "DbiResourceId", "Endpoint.HostedZoneId"},
    "AWS::Logs::LogGroup": {"Arn"}, "AWS::SNS::Topic": {"TopicName", "TopicArn"}, "AWS::EC2::Instance": {"PrivateIp", "PublicIp", "PrivateDnsName", "PublicDnsName", "AvailabilityZone"},
    "AWS::EC2::NatGateway": {"NatGatewayId"}, "AWS::CloudWatch::Alarm": {"Arn"},
}

# (resource type, property) -> resource types the referenced value must resolve to
EXPECTED_REF = {
    ("AWS::EC2::Subnet", "VpcId"): {"AWS::EC2::VPC"},
    ("AWS::EC2::SecurityGroup", "VpcId"): {"AWS::EC2::VPC"},
    ("AWS::EC2::RouteTable", "VpcId"): {"AWS::EC2::VPC"},
    ("AWS::EC2::VPCGatewayAttachment", "VpcId"): {"AWS::EC2::VPC"},
    ("AWS::EC2::VPCGatewayAttachment", "InternetGatewayId"): {"AWS::EC2::InternetGateway"},
    ("AWS::EC2::Route", "RouteTableId"): {"AWS::EC2::RouteTable"},
    ("AWS::EC2::Route", "GatewayId"): {"AWS::EC2::InternetGateway"},
    ("AWS::EC2::Route", "NatGatewayId"): {"AWS::EC2::NatGateway"},
    ("AWS::EC2::SubnetRouteTableAssociation", "SubnetId"): {"AWS::EC2::Subnet"},
    ("AWS::EC2::SubnetRouteTableAssociation", "RouteTableId"): {"AWS::EC2::RouteTable"},
    ("AWS::EC2::NatGateway", "SubnetId"): {"AWS::EC2::Subnet"},
    ("AWS::EC2::NatGateway", "AllocationId"): {"AWS::EC2::EIP"},
    ("AWS::EC2::Instance", "SubnetId"): {"AWS::EC2::Subnet"},
    ("AWS::EC2::Instance", "SecurityGroupIds"): {"AWS::EC2::SecurityGroup"},
    ("AWS::EC2::Instance", "IamInstanceProfile"): {"AWS::IAM::InstanceProfile"},
    ("AWS::EC2::SecurityGroupIngress", "GroupId"): {"AWS::EC2::SecurityGroup"},
    ("AWS::EC2::SecurityGroupIngress", "SourceSecurityGroupId"): {"AWS::EC2::SecurityGroup"},
    ("AWS::IAM::InstanceProfile", "Roles"): {"AWS::IAM::Role"},
    ("AWS::RDS::DBSubnetGroup", "SubnetIds"): {"AWS::EC2::Subnet"},
    ("AWS::RDS::DBInstance", "DBSubnetGroupName"): {"AWS::RDS::DBSubnetGroup"},
    ("AWS::RDS::DBInstance", "VPCSecurityGroups"): {"AWS::EC2::SecurityGroup"},
    ("AWS::ElasticLoadBalancingV2::LoadBalancer", "SecurityGroups"): {"AWS::EC2::SecurityGroup"},
    ("AWS::ElasticLoadBalancingV2::LoadBalancer", "Subnets"): {"AWS::EC2::Subnet"},
    ("AWS::ElasticLoadBalancingV2::TargetGroup", "VpcId"): {"AWS::EC2::VPC"},
    ("AWS::ElasticLoadBalancingV2::TargetGroup", "Targets"): {"AWS::EC2::Instance"},
    ("AWS::ElasticLoadBalancingV2::Listener", "LoadBalancerArn"): {"AWS::ElasticLoadBalancingV2::LoadBalancer"},
    ("AWS::Lambda::Function", "Role"): {"AWS::IAM::Role"},
    ("AWS::Lambda::Function", "VpcConfig"): {"AWS::EC2::Subnet", "AWS::EC2::SecurityGroup"},
    ("AWS::Lambda::EventSourceMapping", "FunctionName"): {"AWS::Lambda::Function"},
    ("AWS::Lambda::EventSourceMapping", "EventSourceArn"): {"AWS::SQS::Queue"},
    ("AWS::Lambda::Permission", "FunctionName"): {"AWS::Lambda::Function"},
    ("AWS::S3::BucketPolicy", "Bucket"): {"AWS::S3::Bucket"},
    ("AWS::SQS::QueuePolicy", "Queues"): {"AWS::SQS::Queue"},
    ("AWS::SNS::Subscription", "TopicArn"): {"AWS::SNS::Topic"},
    ("AWS::EC2::FlowLog", "ResourceId"): {"AWS::EC2::VPC"},
    ("AWS::EC2::FlowLog", "DeliverLogsPermissionArn"): {"AWS::IAM::Role"},
}

_SHORT_TAGS = ["Ref", "GetAtt", "Sub", "Join", "Select", "GetAZs", "If", "Equals", "Not", "And", "Or", "FindInMap",
               "Base64", "Cidr", "ImportValue", "Split", "Condition", "Transform", "Length", "ToJsonString"]


class _Loader(yaml.SafeLoader):
    pass


def _tag(loader, suffix, node):
    if isinstance(node, yaml.ScalarNode):
        val = loader.construct_scalar(node)
    elif isinstance(node, yaml.SequenceNode):
        val = loader.construct_sequence(node, deep=True)
    else:
        val = loader.construct_mapping(node, deep=True)
    if suffix == "Ref":
        return {"Ref": val}
    if suffix == "Condition":
        return {"Condition": val}
    if suffix == "GetAtt":
        return {"Fn::GetAtt": val.split(".", 1) if isinstance(val, str) else val}
    return {f"Fn::{suffix}": val}


_Loader.add_multi_constructor("!", _tag)


def finding(code, severity, message, location=None, fixable=False, component=None, file="template.yaml"):
    return {"code": code, "severity": severity, "message": message, "location": location, "fixable": fixable,
            "component": component, "file": file, "source": "deterministic"}


def _walk(node, path=()):
    yield path, node
    if isinstance(node, dict):
        for k, v in node.items():
            yield from _walk(v, path + (k,))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _walk(v, path + (i,))


def _refs_in(node) -> list[tuple[str, str]]:
    """(kind, name) for every Ref/GetAtt/Sub reference inside a value."""
    out = []
    for _, n in _walk(node):
        if isinstance(n, dict) and len(n) == 1:
            (k, v), = n.items()
            if k == "Ref" and isinstance(v, str):
                out.append(("ref", v))
            elif k == "Fn::GetAtt":
                if isinstance(v, str):
                    v = v.split(".", 1)
                if isinstance(v, list) and v and isinstance(v[0], str):
                    out.append(("getatt", v[0] + "." + ".".join(str(x) for x in v[1:])))
            elif k == "Fn::Sub":
                s = v[0] if isinstance(v, list) else v
                local = set(v[1].keys()) if isinstance(v, list) and len(v) > 1 and isinstance(v[1], dict) else set()
                if isinstance(s, str):
                    for m in re.findall(r"\$\{([^}]+)\}", s):
                        if m.startswith("!") or m in local:
                            continue
                        out.append(("sub", m))
    return out


def parse(text: str) -> tuple[dict | None, list[dict]]:
    try:
        doc = yaml.load(text, Loader=_Loader)
    except yaml.YAMLError as e:
        mark = getattr(e, "problem_mark", None)
        loc = f"line {mark.line + 1}, column {mark.column + 1}" if mark else None
        return None, [finding("CFN-YAML-SYNTAX", "critical", f"YAML syntax error: {getattr(e, 'problem', e)}", loc)]
    if not isinstance(doc, dict):
        return None, [finding("CFN-YAML-SYNTAX", "critical", "Template root must be a YAML mapping")]
    return doc, []


def validate_cfn(text: str, arch: dict | None = None) -> dict:
    checks: list[dict] = []
    findings: list[dict] = []

    def done(name, start_len, detail=""):
        bad = [f for f in findings[start_len:] if f["severity"] == "critical"]
        warn = [f for f in findings[start_len:] if f["severity"] == "warning"]
        checks.append({"name": name, "status": "fail" if bad else "warn" if warn else "pass", "detail": detail})

    doc, errs = parse(text)
    findings += errs
    checks.append({"name": "YAML syntax", "status": "fail" if errs else "pass", "detail": errs[0]["message"] if errs else ""})
    if doc is None:
        return {"ok": False, "checks": checks, "findings": findings}

    n0 = len(findings)
    for key in doc:
        if key not in ("AWSTemplateFormatVersion", "Description", "Metadata", "Parameters", "Mappings", "Conditions",
                       "Transform", "Resources", "Outputs", "Rules"):
            findings.append(finding("CFN-TOPLEVEL", "critical", f"Unknown top-level section '{key}'"))
    res = doc.get("Resources")
    if not isinstance(res, dict) or not res:
        findings.append(finding("CFN-NO-RESOURCES", "critical", "Template has no Resources section"))
        res = {}
    params = doc.get("Parameters") or {}
    done("Template structure", n0)

    # resource types / required props
    n0 = len(findings)
    for lid, r in res.items():
        if not re.fullmatch(r"[A-Za-z0-9]+", str(lid)):
            findings.append(finding("CFN-LOGICAL-ID", "critical", f"Logical ID '{lid}' must be alphanumeric", lid))
        if not isinstance(r, dict) or "Type" not in r:
            findings.append(finding("CFN-NO-TYPE", "critical", f"Resource {lid} has no Type", lid))
            continue
        t = r["Type"]
        m = re.fullmatch(r"(AWS|Alexa)::([A-Za-z0-9]+)::([A-Za-z0-9]+)", str(t))
        if not m and not str(t).startswith("Custom::"):
            findings.append(finding("CFN-TYPE-INVALID", "critical", f"Resource {lid}: '{t}' is not a valid resource type name", lid))
        elif m and m.group(2) not in KNOWN_SERVICES:
            findings.append(finding("CFN-SERVICE-UNKNOWN", "critical", f"Resource {lid}: '{m.group(2)}' is not an AWS service name", lid))
        elif m and t not in KNOWN_TYPES:
            findings.append(finding("CFN-TYPE-UNVERIFIED", "warning", f"Resource {lid}: type {t} is not in the local type list; verify with cfn-lint", lid))
        props = r.get("Properties") or {}
        for req in REQUIRED.get(t, []):
            if req not in props:
                findings.append(finding("CFN-MISSING-PROP", "critical", f"Resource {lid} ({t}) is missing required property {req}", lid))
        if t == "AWS::EC2::SecurityGroupIngress" and not ("GroupId" in props or "GroupName" in props):
            findings.append(finding("CFN-MISSING-PROP", "critical", f"Resource {lid} needs GroupId or GroupName", lid))
    done("Resource types & required properties", n0)

    # references
    n0 = len(findings)
    for lid, r in res.items():
        if not isinstance(r, dict):
            continue
        for kind, name in _refs_in(r):
            base = name.split(".")[0]
            if base in res or base in params or name in PSEUDO or base in PSEUDO or name.startswith("AWS::"):
                if kind in ("getatt", "sub") and base in res and "." in name:
                    attr = name.split(".", 1)[1]
                    t = res[base].get("Type") if isinstance(res[base], dict) else None
                    if t in GETATT and attr not in GETATT[t] and kind == "getatt":
                        findings.append(finding("CFN-GETATT-INVALID", "critical",
                                                f"Resource {lid}: {base} ({t}) has no attribute '{attr}'", lid))
                elif kind == "getatt" and base in params:
                    findings.append(finding("CFN-REF-INVALID", "critical", f"Resource {lid}: GetAtt on parameter {base}", lid))
                continue
            findings.append(finding("CFN-REF-MISSING", "critical",
                                    f"Resource {lid} references '{name}' which is not defined", lid))
        deps = r.get("DependsOn", [])
        for d in [deps] if isinstance(deps, str) else deps:
            if d not in res:
                findings.append(finding("CFN-DEPENDSON-MISSING", "critical", f"Resource {lid}: DependsOn '{d}' does not exist", lid, fixable=True))
    for out_name, out in (doc.get("Outputs") or {}).items():
        for kind, name in _refs_in(out):
            base = name.split(".")[0]
            if base not in res and base not in params and not name.startswith("AWS::"):
                findings.append(finding("CFN-REF-MISSING", "critical", f"Output {out_name} references undefined '{name}'", out_name))
            elif kind == "getatt" and base in res and "." in name:
                attr, t = name.split(".", 1)[1], (res[base].get("Type") if isinstance(res[base], dict) else None)
                if t in GETATT and attr not in GETATT[t]:
                    findings.append(finding("CFN-GETATT-INVALID", "critical", f"Output {out_name}: {base} ({t}) has no attribute '{attr}'", out_name))
    done("References (Ref / GetAtt / Sub)", n0)

    # relationships: property values point at the right resource type
    n0 = len(findings)
    for lid, r in res.items():
        if not isinstance(r, dict):
            continue
        t, props = r.get("Type"), r.get("Properties") or {}
        for (rt, prop), allowed in EXPECTED_REF.items():
            if rt != t or prop not in props:
                continue
            for kind, name in _refs_in(props[prop]):
                base = name.split(".")[0]
                target = res.get(base)
                if isinstance(target, dict) and target.get("Type") not in allowed:
                    findings.append(finding("CFN-REL-TYPE", "critical",
                                            f"Resource {lid}: {prop} must reference {' / '.join(sorted(allowed))} but '{base}' is {target.get('Type')}", lid))
        if t == "AWS::RDS::DBSubnetGroup":
            ids = (props.get("SubnetIds") or [])
            if len(ids) < 2:
                findings.append(finding("CFN-REL-DBSUBNETS", "critical", f"{lid}: a DB subnet group needs subnets in at least two AZs", lid))
        if t == "AWS::ElasticLoadBalancingV2::LoadBalancer" and (props.get("Type", "application") == "application"):
            if len(props.get("Subnets") or []) < 2:
                findings.append(finding("CFN-REL-ALBSUBNETS", "critical", f"{lid}: an Application Load Balancer needs subnets in at least two AZs", lid))
    done("Resource relationships", n0)

    # dependency cycles
    n0 = len(findings)
    graph = {}
    for lid, r in res.items():
        deps = set()
        if isinstance(r, dict):
            for kind, name in _refs_in(r):
                b = name.split(".")[0]
                if b in res and b != lid:
                    deps.add(b)
            d = r.get("DependsOn", [])
            deps |= {x for x in ([d] if isinstance(d, str) else d) if x in res}
        graph[lid] = deps
    state: dict[str, int] = {}

    def dfs(n, stack):
        state[n] = 1
        for m in graph[n]:
            if state.get(m) == 1:
                findings.append(finding("CFN-CYCLE", "critical", "Circular dependency: " + " -> ".join(stack + [n, m]), n))
                return True
            if state.get(m) is None and dfs(m, stack + [n]):
                return True
        state[n] = 2
        return False

    for n in graph:
        if state.get(n) is None and dfs(n, []):
            break
    done("Dependency order (no cycles)", n0)

    # architecture coverage
    if arch is not None:
        n0 = len(findings)
        from ..codegen.plan import RESOURCE_TYPE_FOR
        found: dict[str, str] = {}
        for lid, r in res.items():
            comp = ((r or {}).get("Metadata") or {}).get("SyntaxAI", {}).get("Component") if isinstance(r, dict) else None
            if comp:
                found[comp] = r.get("Type")
        for s in arch["services"]:
            want = RESOURCE_TYPE_FOR.get(s["type"])
            if not want:
                continue
            if s["id"] not in found:
                findings.append(finding("CFN-ARCH-MISSING", "critical",
                                        f"Detected component '{s['label']}' ({s['id']}) has no matching {want} in the template", s["id"]))
            elif found[s["id"]] != want:
                findings.append(finding("CFN-ARCH-TYPE", "critical", f"Component {s['id']} maps to {found[s['id']]}, expected {want}", s["id"]))
        done("Matches detected architecture", n0)
    return {"ok": not any(f["severity"] == "critical" for f in findings), "checks": checks, "findings": findings, "doc": doc}
