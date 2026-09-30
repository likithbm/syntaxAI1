"""Deployment metadata + exact run instructions matching the generated output."""
from __future__ import annotations

from .codegen.plan import Plan


def _iam_permissions(plan: Plan, cdk: bool) -> list[str]:
    perms = ["cloudformation:* on the stack (create/update/delete stacks and change sets)"]
    if plan.has_vpc:
        perms.append("ec2:* for VPC, subnets, route tables, NAT/internet gateways, security groups" + (", instances" if plan.by_type["ec2"] else ""))
    if plan.by_type["alb"]:
        perms.append("elasticloadbalancing:* (load balancer, target group, listener)")
    if plan.by_type["rds"]:
        perms += ["rds:* (instance, subnet group)", "secretsmanager:CreateSecret / TagResource (RDS managed master password)"]
    if plan.by_type["s3"]:
        perms.append("s3:CreateBucket, PutBucketPolicy, PutEncryptionConfiguration, PutBucketPublicAccessBlock, PutBucketVersioning")
    if plan.by_type["dynamodb"]:
        perms.append("dynamodb:CreateTable, UpdateContinuousBackups, TagResource")
    if plan.by_type["sqs"]:
        perms.append("sqs:CreateQueue, SetQueueAttributes, TagQueue")
    if plan.by_type["sns"] or plan.monitoring:
        perms.append("sns:CreateTopic, Subscribe, TagResource")
    if plan.by_type["lambda"]:
        perms.append("lambda:CreateFunction, AddPermission, CreateEventSourceMapping")
    perms.append("iam:CreateRole, PutRolePolicy, AttachRolePolicy, PassRole, CreateInstanceProfile (roles created by the stack)")
    if plan.logging or plan.monitoring:
        perms.append("logs:CreateLogGroup, PutRetentionPolicy; cloudwatch:PutMetricAlarm")
    if plan.by_type["ec2"]:
        perms.append("ssm:GetParameters (resolves the Amazon Linux 2023 AMI parameter)")
    if cdk:
        perms.append("sts:AssumeRole on the cdk-* bootstrap roles (created by `cdk bootstrap`)")
    return perms


def meta_cfn(plan: Plan, files: list[dict]) -> dict:
    r = plan.region
    params = [f"Environment={plan.env}"]
    if plan.https:
        params.append("CertificateArn=<YOUR_ACM_CERTIFICATE_ARN>")
    deploy = (f"aws cloudformation deploy --template-file template.yaml --stack-name {plan.stack_name} "
              f"--capabilities CAPABILITY_IAM --region {r} --parameter-overrides {' '.join(params)}")
    steps = [
        {"title": "Save the template", "detail": "Create an empty folder and save the code as template.yaml in it, then open a terminal in that folder.", "commands": []},
        {"title": "Configure AWS credentials", "detail": "Use an IAM identity that has the permissions listed above (SSO, profile, or access keys).",
         "commands": ["aws configure", "# or, with SSO:  aws sso login --profile <your-profile>"]},
        {"title": "Select the region", "detail": f"The region is set with --region {r} in every command below, so no extra configuration is needed.", "commands": []},
        {"title": "Validate the template", "detail": "Checks syntax with the CloudFormation service (needs credentials).",
         "commands": [f"aws cloudformation validate-template --template-body file://template.yaml --region {r}"]},
        {"title": "Deploy the stack", "detail": ("Replace <YOUR_ACM_CERTIFICATE_ARN> with an ACM certificate in " + r + ". " if plan.https else "") +
         "The first deployment takes several minutes (NAT gateway / RDS).", "commands": [deploy]},
        {"title": "Read the outputs", "detail": "Endpoints, bucket names and ARNs created by the stack.",
         "commands": [f'aws cloudformation describe-stacks --stack-name {plan.stack_name} --region {r} --query "Stacks[0].Outputs"']},
        {"title": "Clean up (optional)", "detail": "Deletes the stack. Resources with Retain/Snapshot policies (production data stores) are kept.",
         "commands": [f"aws cloudformation delete-stack --stack-name {plan.stack_name} --region {r}"]},
    ]
    return {
        "format": "cloudformation", "title": "CloudFormation YAML", "language": "yaml",
        "file_names": [f["path"] for f in files],
        "dependencies": ["AWS CLI v2 (aws --version)"],
        "deployment_command": deploy,
        "configuration": [f"Region: {r}", f"Environment: {plan.env}", f"Stack name: {plan.stack_name}",
                          "VPC CIDR default: " + plan.cidr if plan.has_vpc else "No VPC needed"],
        "aws_region": r,
        "environment_variables": ["AWS_PROFILE (optional, selects the credentials profile)", "AWS_DEFAULT_REGION (optional - the commands pass --region explicitly)"],
        "parameters": params,
        "iam_permissions": _iam_permissions(plan, cdk=False),
        "prerequisites": ["An AWS account and credentials", "AWS CLI v2 installed"] + (["An issued ACM certificate in " + r] if plan.https else []),
        "steps": steps,
    }


def tree(files: list[dict]) -> str:
    paths = sorted(f["path"] for f in files)
    lines = ["syntax-ai-cdk/"]
    dirs: dict[str, list[str]] = {}
    top: list[str] = []
    for p in paths:
        if "/" in p:
            d, n = p.split("/", 1)
            dirs.setdefault(d, []).append(n)
        else:
            top.append(p)
    entries = [(d + "/", dirs[d]) for d in sorted(dirs)] + [(t, None) for t in top]
    for i, (name, kids) in enumerate(entries):
        last = i == len(entries) - 1
        lines.append(("└── " if last else "├── ") + name)
        for j, k in enumerate(kids or []):
            lines.append(("    " if last else "│   ") + ("└── " if j == len(kids) - 1 else "├── ") + k)
    return "\n".join(lines)


def meta_cdk(plan: Plan, files: list[dict]) -> dict:
    r = plan.region
    param = " --parameters CertificateArn=<YOUR_ACM_CERTIFICATE_ARN>" if plan.https else ""
    deploy = f"npx cdk deploy{param}"
    steps = [
        {"title": "Create the project folder", "detail": "Save each file below at exactly this path (use Download all / each file's Download button):\n" + tree(files), "commands": ["cd syntax-ai-cdk"]},
        {"title": "Install dependencies", "detail": "Installs aws-cdk-lib, constructs, TypeScript, ts-node and the CDK CLI listed in package.json.", "commands": ["npm install"]},
        {"title": "Configure AWS credentials", "detail": "Any credentials the AWS CLI understands work; CDK reads the account from them.",
         "commands": ["aws configure", "# or, with SSO:  aws sso login --profile <your-profile>"]},
        {"title": "Bootstrap CDK (once per account/region)", "detail": f"Creates the CDK toolkit resources in {r}. Skip if this account/region is already bootstrapped.",
         "commands": [f"npx cdk bootstrap aws://<ACCOUNT_ID>/{r}"]},
        {"title": "Synthesize", "detail": "Compiles the TypeScript and produces the CloudFormation template; fails here if anything is wrong.", "commands": ["npx cdk synth"]},
        {"title": "Deploy", "detail": ("Replace <YOUR_ACM_CERTIFICATE_ARN> with an ACM certificate in " + r + ". " if plan.https else "") +
         "The first deployment takes several minutes (NAT gateway / RDS).", "commands": [deploy]},
        {"title": "Clean up (optional)", "detail": "Destroys the stack. Production data stores use RETAIN/SNAPSHOT policies and are kept.", "commands": ["npx cdk destroy"]},
    ]
    return {
        "format": "cdk", "title": "AWS CDK (TypeScript)", "language": "typescript",
        "file_names": [f["path"] for f in files], "tree": tree(files),
        "dependencies": ["Node.js 18 or newer", "npm", "aws-cdk-lib 2.170.0, constructs, typescript, ts-node, aws-cdk (installed by npm install)"],
        "deployment_command": deploy,
        "configuration": [f"Region: {r} (set in bin/app.ts)", f"Environment: {plan.env}", f"Stack name: {plan.stack_name}"],
        "aws_region": r,
        "environment_variables": ["AWS_PROFILE (optional)", "CDK_DEFAULT_ACCOUNT / CDK_DEFAULT_REGION (set automatically by the CDK CLI from your credentials)"],
        "parameters": (["CertificateArn=<YOUR_ACM_CERTIFICATE_ARN>"] if plan.https else []),
        "iam_permissions": _iam_permissions(plan, cdk=True),
        "prerequisites": ["An AWS account and credentials", "Node.js 18+ and npm installed"] + (["An issued ACM certificate in " + r] if plan.https else []),
        "steps": steps,
    }
