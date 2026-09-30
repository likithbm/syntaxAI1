"""AWS CDK (TypeScript) project generator."""
from __future__ import annotations

import json

from .plan import Plan, camel, pascal, sg_desc

CDK_VERSION = "2.170.0"

_SUFFIX = {"alb": "Alb", "ec2": "Instance", "rds": "Db", "s3": "Bucket", "lambda": "Fn",
           "dynamodb": "Table", "sqs": "Queue", "sns": "Topic"}
_SIZE = {"micro": "MICRO", "small": "SMALL", "medium": "MEDIUM"}


def _q(s: str) -> str:
    return "'" + s.replace("\\", "\\\\").replace("'", "\\'") + "'"


def stack_lines(plan: Plan) -> list[str]:
    p = plan
    L: list[str] = []
    imports = {"ec2": None, "iam": None}
    used: set[str] = set()
    v = {s["id"]: camel(s["id"]) + _SUFFIX[s["type"]] for s in p.services}
    sg = {s["id"]: camel(s["id"]) + "Sg" for s in p.services if p.tier[s["id"]] is not None}
    role = {s["id"]: camel(s["id"]) + "Role" for s in p.services if s["type"] == "ec2"}
    private_type = "ec2.SubnetType.PRIVATE_WITH_EGRESS" if p.private_egress else "ec2.SubnetType.PRIVATE_ISOLATED"
    subnets = {"public": "{ subnetType: ec2.SubnetType.PUBLIC }", "private": "{ subnetType: " + private_type + " }"}
    removal = "cdk.RemovalPolicy.RETAIN" if p.prod else "cdk.RemovalPolicy.DESTROY"
    add = L.append
    for t, ns in (("alb", "elbv2"), ("rds", "rds"), ("s3", "s3"), ("lambda", "lambda"), ("dynamodb", "dynamodb"),
                  ("sqs", "sqs"), ("sns", "sns")):
        if p.by_type[t]:
            used.add(ns)
    if p.has_vpc or p.by_type["ec2"]:
        used.add("ec2")
    if p.by_type["ec2"]:
        used.add("iam")
    if p.monitoring:
        used |= {"cloudwatch", "cw_actions", "sns"}

    add("    // ---------------------------------------------------------------- network")
    if p.has_vpc:
        cfg = []
        if p.needs_public:
            cfg.append("        { name: 'public', subnetType: ec2.SubnetType.PUBLIC, cidrMask: 24 },")
        if p.needs_private:
            cfg.append(f"        {{ name: 'private', subnetType: {private_type}, cidrMask: 24 }},")
        add("    const vpc = new ec2.Vpc(this, 'Vpc', {")
        add(f"      ipAddresses: ec2.IpAddresses.cidr({_q(p.cidr)}),")
        add(f"      maxAzs: {p.az_count},")
        add(f"      natGateways: {p.nat_count},")
        add("      subnetConfiguration: [")
        L.extend(cfg)
        add("      ],")
        add("    });")
        add("")
        if p.logging:
            add("    vpc.addFlowLog('FlowLog'); // CloudWatch Logs destination")
            add("")

    add("    // ---------------------------------------------------------------- security groups")
    for s in p.services:
        if s["id"] in sg:
            add(f"    const {sg[s['id']]} = new ec2.SecurityGroup(this, '{pascal(s['id'])}Sg', {{")
            add(f"      vpc, description: {_q(sg_desc(s['label']))}, allowAllOutbound: true,")
            add("    });")
            if s["type"] == "alb":
                add(f"    {sg[s['id']]}.addIngressRule(ec2.Peer.anyIpv4(), ec2.Port.tcp(80), 'HTTP from the internet');")
                if p.https:
                    add(f"    {sg[s['id']]}.addIngressRule(ec2.Peer.anyIpv4(), ec2.Port.tcp(443), 'HTTPS from the internet');")
    for a, b in p.conns():
        if a["id"] in sg and b["id"] in sg:
            if a["type"] == "alb" and b["type"] == "ec2":
                add(f"    {sg[b['id']]}.addIngressRule({sg[a['id']]}, ec2.Port.tcp(80), {_q(a['id'] + ' to ' + b['id'])});")
            elif a["type"] in ("ec2", "lambda") and b["type"] == "rds":
                add(f"    {sg[b['id']]}.addIngressRule({sg[a['id']]}, ec2.Port.tcp({p.db_port(b)}), {_q(a['id'] + ' to ' + b['id'])});")
    add("")

    add("    // ---------------------------------------------------------------- data services")
    for s in p.by_type["s3"]:
        add(f"    // component: {s['id']}")
        add(f"    const {v[s['id']]} = new s3.Bucket(this, '{pascal(s['id'])}Bucket', {{")
        add("      encryption: s3.BucketEncryption.S3_MANAGED,")
        add("      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,")
        add("      enforceSSL: true,")
        add(f"      versioned: {'true' if (p.backups or p.prod) else 'false'},")
        add(f"      removalPolicy: {removal},")
        if not p.prod:
            add("      autoDeleteObjects: true,")
        add("    });")
    for s in p.by_type["dynamodb"]:
        add(f"    // component: {s['id']}")
        add(f"    const {v[s['id']]} = new dynamodb.Table(this, '{pascal(s['id'])}Table', {{")
        add("      partitionKey: { name: 'pk', type: dynamodb.AttributeType.STRING },")
        add("      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,")
        add("      encryption: dynamodb.TableEncryption.AWS_MANAGED,")
        add(f"      pointInTimeRecovery: {'true' if (p.backups or p.prod) else 'false'},")
        add(f"      deletionProtection: {'true' if p.prod else 'false'},")
        add(f"      removalPolicy: {removal},")
        add("    });")
    for s in p.by_type["sqs"]:
        add(f"    // component: {s['id']}")
        add(f"    const {v[s['id']]} = new sqs.Queue(this, '{pascal(s['id'])}Queue', {{")
        add("      encryption: sqs.QueueEncryption.SQS_MANAGED,")
        add("      enforceSSL: true,")
        add("      visibilityTimeout: cdk.Duration.seconds(180),")
        add("    });")
    for s in p.by_type["sns"]:
        add(f"    // component: {s['id']}")
        add(f"    const {v[s['id']]} = new sns.Topic(this, '{pascal(s['id'])}Topic', {{")
        add("      masterKey: kms.Alias.fromAliasName(this, '" + pascal(s['id']) + "SnsKey', 'alias/aws/sns'),")
        add("    });")
        used.add("kms")
    for s in p.by_type["rds"]:
        tier = p.tier[s["id"]]
        eng = p.db_engine(s)
        engine = ("rds.DatabaseInstanceEngine.postgres({ version: rds.PostgresEngineVersion.VER_16 })" if eng == "postgres" else
                  "rds.DatabaseInstanceEngine.mysql({ version: rds.MysqlEngineVersion.VER_8_0 })" if eng == "mysql" else
                  "rds.DatabaseInstanceEngine.mariaDb({ version: rds.MariaDbEngineVersion.VER_10_11 })")
        exports = ("['postgresql', 'upgrade']" if eng == "postgres" else "['error', 'general', 'slowquery']")
        add(f"    // component: {s['id']}")
        add(f"    const {v[s['id']]} = new rds.DatabaseInstance(this, '{pascal(s['id'])}Db', {{")
        add(f"      engine: {engine},")
        add(f"      instanceType: ec2.InstanceType.of(ec2.InstanceClass.T3, ec2.InstanceSize.{_SIZE[p.size]}),")
        add("      vpc,")
        add(f"      vpcSubnets: {subnets[tier]},")
        add(f"      securityGroups: [{sg[s['id']]}],")
        add("      credentials: rds.Credentials.fromGeneratedSecret('dbadmin'),")
        add("      allocatedStorage: 20,")
        add("      storageEncrypted: true,")
        add(f"      multiAz: {'true' if p.rds_multi_az(s) else 'false'},")
        add(f"      backupRetention: cdk.Duration.days({p.rds_backup_days(s)}),")
        add(f"      deletionProtection: {'true' if p.prod else 'false'},")
        add(f"      publiclyAccessible: {'true' if tier == 'public' else 'false'},")
        if p.logging:
            add(f"      cloudwatchLogsExports: {exports},")
        add(f"      removalPolicy: {'cdk.RemovalPolicy.SNAPSHOT' if p.prod else 'cdk.RemovalPolicy.DESTROY'},")
        add("    });")
    add("")

    add("    // ---------------------------------------------------------------- compute + IAM")
    for i, s in enumerate(p.by_type["ec2"]):
        tier = p.tier[s["id"]]
        add(f"    // component: {s['id']}")
        add(f"    const {role[s['id']]} = new iam.Role(this, '{pascal(s['id'])}Role', {{")
        add("      assumedBy: new iam.ServicePrincipal('ec2.amazonaws.com'),")
        add("      managedPolicies: [iam.ManagedPolicy.fromAwsManagedPolicyName('AmazonSSMManagedInstanceCore')],")
        add("    });")
        add(f"    const {v[s['id']]} = new ec2.Instance(this, '{pascal(s['id'])}Instance', {{")
        add("      vpc,")
        add(f"      vpcSubnets: {subnets[tier]},")
        add(f"      instanceType: ec2.InstanceType.of(ec2.InstanceClass.T3, ec2.InstanceSize.{_SIZE[p.size]}),")
        add("      machineImage: ec2.MachineImage.latestAmazonLinux2023(),")
        add(f"      securityGroup: {sg[s['id']]},")
        add(f"      role: {role[s['id']]},")
        add("      requireImdsv2: true,")
        add(f"      detailedMonitoring: {'true' if p.monitoring else 'false'},")
        add("      blockDevices: [{ deviceName: '/dev/xvda', volume: ec2.BlockDeviceVolume.ebs(20, { encrypted: true }) }],")
        add("    });")
        if any(s["id"] in {t["id"] for t in p.alb_targets(a)} for a in p.by_type["alb"]):
            add(f"    {v[s['id']]}.addUserData('dnf install -y nginx', 'systemctl enable --now nginx'); // placeholder web server")
    for s in p.by_type["lambda"]:
        in_vpc = p.tier[s["id"]] == "private"
        env = []
        for a, b in p.conns():
            if a["id"] == s["id"]:
                key = b["id"].upper()
                if b["type"] == "s3":
                    env.append(f"        S3_BUCKET_{key}: {v[b['id']]}.bucketName,")
                elif b["type"] == "dynamodb":
                    env.append(f"        DYNAMODB_TABLE_{key}: {v[b['id']]}.tableName,")
                elif b["type"] == "sqs":
                    env.append(f"        SQS_QUEUE_URL_{key}: {v[b['id']]}.queueUrl,")
                elif b["type"] == "sns":
                    env.append(f"        SNS_TOPIC_ARN_{key}: {v[b['id']]}.topicArn,")
                elif b["type"] == "rds":
                    env.append(f"        DB_HOST_{key}: {v[b['id']]}.dbInstanceEndpointAddress,")
                    env.append(f"        DB_PORT_{key}: {v[b['id']]}.dbInstanceEndpointPort,")
                    env.append(f"        DB_SECRET_ARN_{key}: {v[b['id']]}.secret!.secretArn,")
        add(f"    // component: {s['id']}")
        add(f"    const {v[s['id']]} = new lambda.Function(this, '{pascal(s['id'])}Fn', {{")
        add("      runtime: lambda.Runtime.PYTHON_3_12,")
        add("      handler: 'index.handler',")
        add("      code: lambda.Code.fromInline(")
        add("        'import json\\n\\ndef handler(event, context):\\n    print(json.dumps(event))\\n    return {\"statusCode\": 200, \"body\": \"ok\"}\\n',")
        add("      ),")
        add("      timeout: cdk.Duration.seconds(30),")
        add("      memorySize: 256,")
        if in_vpc:
            add("      vpc,")
            add(f"      vpcSubnets: {subnets['private']},")
            add(f"      securityGroups: [{sg[s['id']]}],")
        if env:
            add("      environment: {")
            L.extend(env)
            add("      },")
        add("    });")
    add("")

    add("    // ---------------------------------------------------------------- connections -> least-privilege grants")
    for a, b in p.conns():
        who = role.get(a["id"]) if a["type"] == "ec2" else v.get(a["id"]) if a["type"] == "lambda" else None
        tgt = v.get(b["id"])
        if who and a["type"] in ("ec2", "lambda"):
            if b["type"] == "s3":
                add(f"    {tgt}.grantReadWrite({who});")
            elif b["type"] == "dynamodb":
                add(f"    {tgt}.grantReadWriteData({who});")
            elif b["type"] == "sqs":
                add(f"    {tgt}.grantSendMessages({who});")
                add(f"    {tgt}.grantConsumeMessages({who});")
            elif b["type"] == "sns":
                add(f"    {tgt}.grantPublish({who});")
            elif b["type"] == "rds":
                add(f"    {tgt}.secret!.grantRead({who});")
            elif b["type"] == "lambda":
                add(f"    {tgt}.grantInvoke({who});")
        if a["type"] == "sqs" and b["type"] == "lambda":
            add(f"    {tgt}.addEventSource(new eventsources.SqsEventSource({v[a['id']]}));")
            used.add("eventsources")
        if a["type"] == "sns" and b["type"] == "lambda":
            add(f"    {v[a['id']]}.addSubscription(new subs.LambdaSubscription({tgt}));")
            used.add("subs")
    add("")

    if p.by_type["alb"]:
        add("    // ---------------------------------------------------------------- load balancers")
        if p.https:
            add("    const certificateArn = new cdk.CfnParameter(this, 'CertificateArn', {")
            add("      type: 'String', description: 'ARN of an ACM certificate in this region for the HTTPS listener',")
            add("    });")
            add("    const certificate = acm.Certificate.fromCertificateArn(this, 'Certificate', certificateArn.valueAsString);")
            used.add("acm")
        for s in p.by_type["alb"]:
            targets = p.alb_targets(s)
            a = v[s["id"]]
            add(f"    // component: {s['id']}")
            add(f"    const {a} = new elbv2.ApplicationLoadBalancer(this, '{pascal(s['id'])}Alb', {{")
            add(f"      vpc, internetFacing: true, securityGroup: {sg[s['id']]}, vpcSubnets: {subnets['public']},")
            add("      dropInvalidHeaderFields: true,")
            add(f"      deletionProtection: {'true' if p.prod else 'false'},")
            add("    });")
            fixed = "elbv2.ListenerAction.fixedResponse(503, { contentType: 'text/plain', messageBody: 'No targets configured' })"
            if p.https:
                add(f"    const {a}Https = {a}.addListener('Https', {{")
                add("      port: 443, protocol: elbv2.ApplicationProtocol.HTTPS, certificates: [certificate], open: false,")
                if not targets:
                    add(f"      defaultAction: {fixed},")
                add("    });")
                add(f"    {a}.addListener('Http', {{")
                add("      port: 80, open: false,")
                add("      defaultAction: elbv2.ListenerAction.redirect({ protocol: 'HTTPS', port: '443', permanent: true }),")
                add("    });")
                lst = f"{a}Https"
            else:
                add(f"    const {a}Http = {a}.addListener('Http', {{")
                add("      port: 80, open: false,")
                if not targets:
                    add(f"      defaultAction: {fixed},")
                add("    });")
                lst = f"{a}Http"
            if targets:
                add(f"    {lst}.addTargets('{pascal(s['id'])}Targets', {{")
                add("      port: 80, protocol: elbv2.ApplicationProtocol.HTTP,")
                add("      targets: [" + ", ".join(f"new elbv2targets.InstanceIdTarget({v[t['id']]}.instanceId)" for t in targets) + "],")
                add("      healthCheck: { path: '/' },")
                add("    });")
                used.add("elbv2targets")
        add("")

    if p.monitoring:
        add("    // ---------------------------------------------------------------- monitoring")
        add("    const alarmTopic = new sns.Topic(this, 'AlarmTopic', { displayName: 'Syntax AI alarms' });")
        alarms = 0
        for s in p.by_type["ec2"]:
            n = pascal(s["id"])
            add(f"    new cloudwatch.Alarm(this, '{n}CpuAlarm', {{")
            add("      metric: new cloudwatch.Metric({ namespace: 'AWS/EC2', metricName: 'CPUUtilization', statistic: 'Average',")
            add(f"        period: cdk.Duration.minutes(5), dimensionsMap: {{ InstanceId: {v[s['id']]}.instanceId }} }}),")
            add("      threshold: 80, evaluationPeriods: 2, comparisonOperator: cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,")
            add("      treatMissingData: cloudwatch.TreatMissingData.NOT_BREACHING, alarmDescription: 'CPU above 80%',")
            add("    }).addAlarmAction(new cwActions.SnsAction(alarmTopic));")
            alarms += 1
        for s in p.by_type["rds"]:
            n = pascal(s["id"])
            add(f"    new cloudwatch.Alarm(this, '{n}CpuAlarm', {{")
            add(f"      metric: {v[s['id']]}.metricCPUUtilization({{ period: cdk.Duration.minutes(5) }}),")
            add("      threshold: 80, evaluationPeriods: 2, comparisonOperator: cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,")
            add("      treatMissingData: cloudwatch.TreatMissingData.NOT_BREACHING, alarmDescription: 'CPU above 80%',")
            add("    }).addAlarmAction(new cwActions.SnsAction(alarmTopic));")
            alarms += 1
        for s in p.by_type["alb"]:
            n = pascal(s["id"])
            add(f"    new cloudwatch.Alarm(this, '{n}Elb5xxAlarm', {{")
            add(f"      metric: {v[s['id']]}.metrics.httpCodeElb(elbv2.HttpCodeElb.ELB_5XX_COUNT, {{ period: cdk.Duration.minutes(5), statistic: 'Sum' }}),")
            add("      threshold: 10, evaluationPeriods: 2, comparisonOperator: cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,")
            add("      treatMissingData: cloudwatch.TreatMissingData.NOT_BREACHING, alarmDescription: 'More than 10 ELB 5XX in 5 minutes',")
            add("    }).addAlarmAction(new cwActions.SnsAction(alarmTopic));")
            alarms += 1
        add("    new cdk.CfnOutput(this, 'AlarmTopicArn', { value: alarmTopic.topicArn });")
        add("")

    add("    // ---------------------------------------------------------------- outputs")
    for s in p.services:
        n, x = pascal(s["id"]), v[s["id"]]
        if s["type"] == "alb":
            add(f"    new cdk.CfnOutput(this, '{n}DnsName', {{ value: {x}.loadBalancerDnsName }});")
        elif s["type"] == "rds":
            add(f"    new cdk.CfnOutput(this, '{n}Endpoint', {{ value: {x}.dbInstanceEndpointAddress }});")
            add(f"    new cdk.CfnOutput(this, '{n}SecretArn', {{ value: {x}.secret!.secretArn }});")
        elif s["type"] == "s3":
            add(f"    new cdk.CfnOutput(this, '{n}Name', {{ value: {x}.bucketName }});")
        elif s["type"] == "dynamodb":
            add(f"    new cdk.CfnOutput(this, '{n}Name', {{ value: {x}.tableName }});")
        elif s["type"] == "sqs":
            add(f"    new cdk.CfnOutput(this, '{n}Url', {{ value: {x}.queueUrl }});")
        elif s["type"] == "sns":
            add(f"    new cdk.CfnOutput(this, '{n}Arn', {{ value: {x}.topicArn }});")
        elif s["type"] == "lambda":
            add(f"    new cdk.CfnOutput(this, '{n}Name', {{ value: {x}.functionName }});")
        elif s["type"] == "ec2":
            add(f"    new cdk.CfnOutput(this, '{n}Id', {{ value: {x}.instanceId }});")

    # imports (only what is used)
    mod = {"ec2": "aws-ec2", "iam": "aws-iam", "elbv2": "aws-elasticloadbalancingv2", "rds": "aws-rds", "s3": "aws-s3",
           "lambda": "aws-lambda", "dynamodb": "aws-dynamodb", "sqs": "aws-sqs", "sns": "aws-sns", "kms": "aws-kms",
           "acm": "aws-certificatemanager", "cloudwatch": "aws-cloudwatch", "cw_actions": "aws-cloudwatch-actions",
           "cwActions": "aws-cloudwatch-actions", "elbv2targets": "aws-elasticloadbalancingv2-targets",
           "eventsources": "aws-lambda-event-sources", "subs": "aws-sns-subscriptions"}
    alias = {"cw_actions": "cwActions"}
    head = ["import * as cdk from 'aws-cdk-lib';", "import { Construct } from 'constructs';"]
    for ns in sorted(used):
        head.append(f"import * as {alias.get(ns, ns)} from 'aws-cdk-lib/{mod[ns]}';")
    return head, L


def generate(plan: Plan) -> list[dict]:
    head, body = stack_lines(plan)
    stack = "\n".join(head) + f"""

export class SyntaxAiStack extends cdk.Stack {{
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {{
    super(scope, id, props);

""" + "\n".join(body) + """
  }
}
"""
    app = f"""#!/usr/bin/env node
import * as cdk from 'aws-cdk-lib';
import {{ SyntaxAiStack }} from '../lib/syntax-ai-stack';

const app = new cdk.App();
new SyntaxAiStack(app, {_q(plan.stack_name)}, {{
  env: {{ account: process.env.CDK_DEFAULT_ACCOUNT, region: {_q(plan.region)} }},
  tags: {{ Environment: {_q(plan.env)}, 'managed-by': 'syntax-ai' }},
}});
"""
    pkg = {
        "name": "syntax-ai-cdk", "version": "0.1.0", "private": True,
        "bin": {"syntax-ai-cdk": "bin/app.js"},
        "scripts": {"build": "tsc", "synth": "cdk synth", "deploy": "cdk deploy", "destroy": "cdk destroy"},
        "dependencies": {"aws-cdk-lib": CDK_VERSION, "constructs": "^10.3.0"},
        "devDependencies": {"@types/node": "^20.14.0", "aws-cdk": "^2.170.0", "ts-node": "^10.9.2", "typescript": "~5.6.3"},
    }
    cdk_json = {"app": "npx ts-node --prefer-ts-exts bin/app.ts", "watch": {"include": ["**"], "exclude": ["node_modules", "cdk.out"]},
                "context": {"@aws-cdk/aws-lambda:recognizeLayerVersion": True}}
    tsconfig = {"compilerOptions": {
        "target": "ES2020", "module": "commonjs", "lib": ["es2020"], "declaration": True, "strict": True,
        "noImplicitAny": True, "strictNullChecks": True, "noImplicitThis": True, "alwaysStrict": True,
        "noUnusedLocals": False, "noUnusedParameters": False, "noImplicitReturns": True, "inlineSourceMap": True,
        "inlineSources": True, "experimentalDecorators": True, "strictPropertyInitialization": False,
        "typeRoots": ["./node_modules/@types"], "skipLibCheck": True}, "exclude": ["node_modules", "cdk.out"]}
    return [
        {"path": "bin/app.ts", "language": "typescript", "content": app},
        {"path": "lib/syntax-ai-stack.ts", "language": "typescript", "content": stack},
        {"path": "package.json", "language": "json", "content": json.dumps(pkg, indent=2) + "\n"},
        {"path": "cdk.json", "language": "json", "content": json.dumps(cdk_json, indent=2) + "\n"},
        {"path": "tsconfig.json", "language": "json", "content": json.dumps(tsconfig, indent=2) + "\n"},
        {"path": ".gitignore", "language": "text", "content": "node_modules\ncdk.out\n*.js\n*.d.ts\n"},
    ]
