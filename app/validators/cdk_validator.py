"""CDK TypeScript project validation.

No TypeScript compiler is available inside Lambda, so this is a structured
heuristic check (syntax balance, imports, identifiers, known constructs,
package files). `npx cdk synth` (part of the run instructions) is the final authority.
"""
from __future__ import annotations

import difflib
import json
import re

from .cfn_validator import finding

KNOWN_MODULES = {
    "aws-ec2", "aws-iam", "aws-elasticloadbalancingv2", "aws-rds", "aws-s3", "aws-lambda", "aws-dynamodb", "aws-sqs", "aws-sns",
    "aws-kms", "aws-certificatemanager", "aws-cloudwatch", "aws-cloudwatch-actions", "aws-elasticloadbalancingv2-targets",
    "aws-lambda-event-sources", "aws-sns-subscriptions", "aws-logs", "aws-secretsmanager", "aws-ssm", "aws-route53",
    "aws-cloudfront", "aws-ecs", "aws-autoscaling", "aws-events", "aws-events-targets", "aws-apigateway",
}

CONSTRUCTS = {
    "ec2": {"Vpc", "SecurityGroup", "Instance", "InstanceType", "InstanceClass", "InstanceSize", "MachineImage", "BlockDeviceVolume",
            "Peer", "Port", "IpAddresses", "SubnetType", "FlowLogDestination", "FlowLog", "Volume", "LaunchTemplate", "UserData",
            "GatewayVpcEndpoint", "InterfaceVpcEndpoint", "GatewayVpcEndpointAwsService", "InterfaceVpcEndpointAwsService",
            "Subnet", "SubnetSelection", "CfnInstance", "CfnSecurityGroup", "EbsDeviceVolumeType", "OperatingSystemType"},
    "iam": {"Role", "ServicePrincipal", "ManagedPolicy", "PolicyStatement", "PolicyDocument", "Policy", "User", "Group", "Effect",
            "AnyPrincipal", "ArnPrincipal", "AccountPrincipal", "CfnRole", "InstanceProfile", "OpenIdConnectProvider"},
    "elbv2": {"ApplicationLoadBalancer", "ApplicationTargetGroup", "ApplicationListener", "ListenerAction", "ApplicationProtocol",
              "HttpCodeElb", "HttpCodeTarget", "NetworkLoadBalancer", "ListenerCondition", "TargetType", "SslPolicy", "Protocol",
              "ListenerCertificate", "TargetGroupBase", "IpAddressType"},
    "elbv2targets": {"InstanceIdTarget", "InstanceTarget", "LambdaTarget", "IpTarget", "AlbTarget"},
    "rds": {"DatabaseInstance", "DatabaseInstanceEngine", "Credentials", "PostgresEngineVersion", "MysqlEngineVersion",
            "MariaDbEngineVersion", "DatabaseCluster", "SubnetGroup", "StorageType", "ParameterGroup", "DatabaseSecret",
            "DatabaseInstanceReadReplica", "CfnDBInstance", "CaCertificate", "AuroraPostgresEngineVersion", "AuroraMysqlEngineVersion",
            "DatabaseClusterEngine", "OptionGroup", "PerformanceInsightRetention", "NetworkType"},
    "s3": {"Bucket", "BucketEncryption", "BlockPublicAccess", "BucketPolicy", "BucketAccessControl", "ObjectOwnership", "StorageClass",
           "EventType", "HttpMethods", "CfnBucket"},
    "lambda": {"Function", "Runtime", "Code", "Architecture", "Alias", "Version", "LayerVersion", "FunctionUrlAuthType", "Tracing",
               "InlineCode", "AssetCode", "DockerImageFunction", "CfnFunction", "EventSourceMapping", "StartingPosition"},
    "dynamodb": {"Table", "AttributeType", "BillingMode", "TableEncryption", "TableClass", "StreamViewType", "CfnTable", "ProjectionType"},
    "sqs": {"Queue", "QueueEncryption", "QueuePolicy", "DeadLetterQueue", "CfnQueue"},
    "sns": {"Topic", "Subscription", "SubscriptionProtocol", "TopicPolicy", "CfnTopic"},
    "kms": {"Key", "Alias", "KeySpec", "KeyUsage"},
    "acm": {"Certificate", "CertificateValidation", "DnsValidatedCertificate"},
    "cloudwatch": {"Alarm", "Metric", "ComparisonOperator", "TreatMissingData", "Dashboard", "Stats", "Unit", "MathExpression", "CompositeAlarm"},
    "cwActions": {"SnsAction", "AutoScalingAction"},
    "eventsources": {"SqsEventSource", "SnsEventSource", "S3EventSource", "DynamoEventSource", "ApiEventSource"},
    "subs": {"LambdaSubscription", "EmailSubscription", "SqsSubscription", "UrlSubscription", "SmsSubscription"},
    "cdk": {"App", "Stack", "CfnParameter", "CfnOutput", "Duration", "RemovalPolicy", "StackProps", "Tags", "Size", "Fn", "Aws",
            "CfnResource", "Tag", "Aspects", "Stage", "Token", "SecretValue", "CfnCondition", "Annotations"},
}


GLOBALS = {"this", "super", "cdk", "process", "Math", "JSON", "Object", "Array", "String", "Number", "console", "undefined", "null",
           "true", "false", "props", "scope", "id"}
IMPORT_LINE = {
    "ec2": "import * as ec2 from 'aws-cdk-lib/aws-ec2';", "iam": "import * as iam from 'aws-cdk-lib/aws-iam';",
    "elbv2": "import * as elbv2 from 'aws-cdk-lib/aws-elasticloadbalancingv2';", "rds": "import * as rds from 'aws-cdk-lib/aws-rds';",
    "s3": "import * as s3 from 'aws-cdk-lib/aws-s3';", "lambda": "import * as lambda from 'aws-cdk-lib/aws-lambda';",
    "dynamodb": "import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';", "sqs": "import * as sqs from 'aws-cdk-lib/aws-sqs';",
    "sns": "import * as sns from 'aws-cdk-lib/aws-sns';", "kms": "import * as kms from 'aws-cdk-lib/aws-kms';",
    "acm": "import * as acm from 'aws-cdk-lib/aws-certificatemanager';",
    "cloudwatch": "import * as cloudwatch from 'aws-cdk-lib/aws-cloudwatch';",
    "cwActions": "import * as cwActions from 'aws-cdk-lib/aws-cloudwatch-actions';",
    "elbv2targets": "import * as elbv2targets from 'aws-cdk-lib/aws-elasticloadbalancingv2-targets';",
    "eventsources": "import * as eventsources from 'aws-cdk-lib/aws-lambda-event-sources';",
    "subs": "import * as subs from 'aws-cdk-lib/aws-sns-subscriptions';",
    "cdk": "import * as cdk from 'aws-cdk-lib';",
}


def strip_code(src: str) -> str:
    """Remove comments and string/template literal contents (keeps quotes) for structural checks."""
    out, i, n = [], 0, len(src)
    while i < n:
        c = src[i]
        if src.startswith("//", i):
            while i < n and src[i] != "\n":
                i += 1
        elif src.startswith("/*", i):
            j = src.find("*/", i + 2)
            i = n if j == -1 else j + 2
        elif c in "'\"`":
            q = c
            out.append(q)
            i += 1
            while i < n and src[i] != q:
                if src[i] == "\\":
                    i += 1
                if q != "`" and src[i:i + 1] == "\n":
                    break
                i += 1
            out.append(q)
            i += 1
        else:
            out.append(c)
            i += 1
    return "".join(out)


def _balance(code: str) -> str | None:
    pairs = {")": "(", "]": "[", "}": "{"}
    stack: list[tuple[str, int]] = []
    line = 1
    for ch in code:
        if ch == "\n":
            line += 1
        elif ch in "([{":
            stack.append((ch, line))
        elif ch in pairs:
            if not stack or stack[-1][0] != pairs[ch]:
                return f"unexpected '{ch}' on line {line}"
            stack.pop()
    if stack:
        return f"'{stack[-1][0]}' opened on line {stack[-1][1]} is never closed"
    return None


def validate_cdk(files: dict[str, str], arch: dict | None = None) -> dict:
    checks, findings = [], []

    def done(name, start, detail=""):
        bad = [x for x in findings[start:] if x["severity"] == "critical"]
        warn = [x for x in findings[start:] if x["severity"] == "warning"]
        checks.append({"name": name, "status": "fail" if bad else "warn" if warn else "pass", "detail": detail})

    def F(code, sev, msg, file, fixable=False, component=None):
        findings.append(finding(code, sev, msg, None, fixable, component, file))

    n0 = len(findings)
    for req in ("package.json", "cdk.json", "tsconfig.json", "bin/app.ts", "lib/syntax-ai-stack.ts"):
        if req not in files:
            F("CDK-FILE-MISSING", "critical", f"Project file {req} is missing", req)
    pkg = None
    for name in ("package.json", "cdk.json", "tsconfig.json"):
        if name in files:
            try:
                data = json.loads(files[name])
                if name == "package.json":
                    pkg = data
            except json.JSONDecodeError as e:
                F("CDK-JSON-SYNTAX", "critical", f"{name} is not valid JSON: {e.msg} (line {e.lineno})", name)
    if pkg is not None:
        deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
        for d in ("aws-cdk-lib", "constructs", "typescript", "aws-cdk", "ts-node"):
            if d not in deps:
                F("CDK-DEP-MISSING", "critical", f"package.json does not list dependency '{d}'", "package.json")
    if "cdk.json" in files:
        try:
            app_cmd = json.loads(files["cdk.json"]).get("app", "")
            m = re.search(r"(bin/[\w.-]+\.ts)", app_cmd)
            if not m or m.group(1) not in files:
                F("CDK-APP-ENTRY", "critical", f"cdk.json 'app' command does not point to an existing entry file ({app_cmd})", "cdk.json")
        except json.JSONDecodeError:
            pass
    done("Project structure & package files", n0)

    ts_files = {k: v for k, v in files.items() if k.endswith(".ts")}
    n0 = len(findings)
    stripped = {}
    for path, src in ts_files.items():
        code = strip_code(src)
        stripped[path] = code
        msg = _balance(code)
        if msg:
            F("CDK-TS-SYNTAX", "critical", f"TypeScript syntax: {msg}", path)
        for stmt in re.findall(r"^\s*(?:const|let)\s+\w+\s*=\s*$", code, flags=re.M):
            F("CDK-TS-SYNTAX", "critical", "Declaration without a value", path)
    done("TypeScript syntax", n0)

    n0 = len(findings)
    for path, src in ts_files.items():
        code = stripped[path]
        imported: dict[str, str] = {}
        for m in re.finditer(r"import\s+\*\s+as\s+(\w+)\s+from\s+'([^']+)'", src):
            imported[m.group(1)] = m.group(2)
            spec = m.group(2)
            if spec.startswith("aws-cdk-lib/") and spec.split("/", 1)[1] not in KNOWN_MODULES:
                F("CDK-IMPORT-INVALID", "critical", f"Import '{spec}' is not an aws-cdk-lib module", path)
        for m in re.finditer(r"import\s+\{([^}]+)\}\s+from\s+'([^']+)'", src):
            for nm in m.group(1).split(","):
                nm = nm.strip().split(" as ")[-1].strip()
                if nm:
                    imported[nm] = m.group(2)
            spec = m.group(2)
            if spec.startswith("aws-cdk-lib/") and spec.split("/", 1)[1] not in KNOWN_MODULES:
                F("CDK-IMPORT-INVALID", "critical", f"Import '{spec}' is not an aws-cdk-lib module", path)
        for m in re.finditer(r"import\s+(\w+)\s+from", src):
            imported[m.group(1)] = "default"
        # namespaces used but not imported
        for ns in set(re.findall(r"(?<![\w.$])(ec2|iam|elbv2|elbv2targets|rds|s3|lambda|dynamodb|sqs|sns|kms|acm|cloudwatch|cwActions|eventsources|subs|cdk)\.", code)):
            if ns not in imported:
                F("CDK-IMPORT-MISSING", "critical", f"'{ns}' is used but not imported", path, fixable=True, component=ns)
        for ns in imported:
            if ns in CONSTRUCTS and not re.search(rf"(?<![\w.$]){ns}\.", code) and imported[ns] != "default":
                F("CDK-IMPORT-UNUSED", "warning", f"Import '{ns}' is never used", path)
        # construct / export names: a near-miss of a known name is a typo (critical); an unknown name is unverified (warning)
        seen_names: set[tuple[str, str]] = set()
        for ns, name in re.findall(r"(?:new\s+)?(?<![\w.$])(ec2|iam|elbv2|elbv2targets|rds|s3|lambda|dynamodb|sqs|sns|kms|acm|cloudwatch|cwActions|eventsources|subs|cdk)\.([A-Z]\w+)", code):
            if (ns, name) in seen_names or name in CONSTRUCTS[ns]:
                continue
            seen_names.add((ns, name))
            close = difflib.get_close_matches(name, CONSTRUCTS[ns], n=1, cutoff=0.8)
            if close:
                F("CDK-CONSTRUCT-INVALID", "critical", f"'{ns}.{name}' is not a CDK export - did you mean '{ns}.{close[0]}'?", path)
            else:
                F("CDK-CONSTRUCT-UNVERIFIED", "warning", f"'{ns}.{name}' is not in the local export list; `cdk synth` will confirm it", path)
        for m in re.finditer(r"new\s+([A-Z]\w+)\(", code):
            nm = m.group(1)
            if nm not in imported and nm not in ("Error", "Date", "Map", "Set", "Promise", "Array", "Object") and nm not in re.findall(r"class\s+(\w+)", code):
                F("CDK-IMPORT-MISSING", "critical", f"'{nm}' is used but not imported or defined", path)
    done("Imports & CDK constructs", n0)

    n0 = len(findings)
    for path, src in ts_files.items():
        code = stripped[path]
        declared = set(GLOBALS) | set(re.findall(r"\b(?:const|let|var|function|class)\s+(\w+)", code))
        for m in re.finditer(r"import\s+\*\s+as\s+(\w+)", src):
            declared.add(m.group(1))
        for m in re.finditer(r"import\s+\{([^}]+)\}", src):
            declared |= {x.strip().split(" as ")[-1].strip() for x in m.group(1).split(",")}
        for m in re.finditer(r"\(([^()]*)\)\s*(?::\s*[\w.<>\[\]| ]+)?\s*(?:=>|\{)", code):
            for part in m.group(1).split(","):
                nm = re.match(r"\s*(\w+)", part)
                if nm:
                    declared.add(nm.group(1))
        # identifiers used as `name.` or as call/arg values that were never declared
        defined_at: dict[str, int] = {}
        for m in re.finditer(r"\b(?:const|let)\s+(\w+)", code):
            defined_at.setdefault(m.group(1), m.start())
        for m in re.finditer(r"(?<![\w.$'\"])([A-Za-z_]\w*)\s*\.(?=\s*[A-Za-z_])", code):
            nm = m.group(1)
            if nm not in declared:
                F("CDK-UNDEFINED", "critical", f"'{nm}' is used but never declared or imported", path)
            elif nm in defined_at and m.start() < defined_at[nm]:
                F("CDK-USE-BEFORE-DEFINE", "critical", f"'{nm}' is used before it is declared", path)
        for m in re.finditer(r"\b(?:securityGroups?|role|vpc):\s*\[?\s*([A-Za-z_]\w*)", code):
            nm = m.group(1)
            if nm not in declared:
                F("CDK-UNDEFINED", "critical", f"'{nm}' is referenced but never declared", path)
            elif nm in defined_at and m.start() < defined_at[nm]:
                F("CDK-USE-BEFORE-DEFINE", "critical", f"'{nm}' is used before it is declared", path)
    done("Variables & references", n0)

    if arch is not None:
        n0 = len(findings)
        text = "\n".join(files.get(k, "") for k in ts_files)
        want = {"alb": "elbv2.ApplicationLoadBalancer", "ec2": "ec2.Instance", "rds": "rds.DatabaseInstance", "s3": "s3.Bucket",
                "lambda": "lambda.Function", "dynamodb": "dynamodb.Table", "sqs": "sqs.Queue", "sns": "sns.Topic"}
        for s in arch["services"]:
            if s["type"] in want and f"// component: {s['id']}\n" not in text:
                F("CDK-ARCH-MISSING", "critical", f"Detected component '{s['label']}' ({s['id']}) is not defined in the stack", "lib/syntax-ai-stack.ts", component=s["id"])
        for t, cls in want.items():
            expected = sum(1 for s in arch["services"] if s["type"] == t)
            actual = len(re.findall(rf"new {re.escape(cls)}\(", text))
            if actual < expected:
                F("CDK-ARCH-COUNT", "critical", f"Expected {expected} x {cls} but found {actual}", "lib/syntax-ai-stack.ts")
        done("Matches detected architecture", n0)

    return {"ok": not any(x["severity"] == "critical" for x in findings), "checks": checks, "findings": findings}
