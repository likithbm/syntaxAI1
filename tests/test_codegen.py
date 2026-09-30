import copy
import re
import unittest

from tests import helpers as h
from app.architecture import apply_ops, normalize_architecture, options_to_ops
from app.codegen import cdk as cdk_gen
from app.codegen import cloudformation as cfn_gen
from app.codegen.plan import Plan
from app.policy_engine import code_rules
from app.validators import fixer
from app.validators.cdk_validator import strip_code, validate_cdk
from app.validators.cfn_validator import validate_cfn

ALL_OPTS = ["encryption", "private_subnets", "iam_least_privilege", "cloudwatch_logging", "security_groups",
            "multi_az", "backups", "https_tls", "monitoring"]


def serverless_arch():
    return normalize_architecture({
        "network": {"vpc": False, "availability_zones": 1},
        "services": [
            {"id": "internet", "type": "internet"},
            {"id": "api_fn", "type": "lambda", "label": "API", "tier": "private"},
            {"id": "worker", "type": "lambda", "label": "Worker", "tier": "n/a"},
            {"id": "orders", "type": "dynamodb", "label": "Orders"},
            {"id": "jobs", "type": "sqs", "label": "Jobs"},
            {"id": "events", "type": "sns", "label": "Events"},
            {"id": "files", "type": "s3", "label": "Files"},
            {"id": "db", "type": "rds", "label": "DB", "tier": "private", "properties": {"engine": "postgres"}}],
        "connections": [
            {"from": "api_fn", "to": "orders"}, {"from": "api_fn", "to": "jobs"}, {"from": "jobs", "to": "worker"},
            {"from": "events", "to": "worker"}, {"from": "worker", "to": "files"}, {"from": "api_fn", "to": "events"},
            {"from": "api_fn", "to": "db"}]})


def with_opts(arch, opts):
    a, _, rej = apply_ops(arch, options_to_ops(arch, opts))
    assert not rej, rej
    return a


class CodegenTests(unittest.TestCase):
    def build(self, arch, **o):
        opts = {"environment": "production", "region": "ap-south-1", **o}
        plan = Plan(arch, opts)
        cfn = cfn_gen.generate(plan)
        cdk = {f["path"]: f["content"] for f in cdk_gen.generate(plan)}
        return plan, cfn, cdk

    def assert_valid(self, arch, **o):
        plan, cfn, cdk = self.build(arch, **o)
        r = validate_cfn(cfn, arch)
        crit = [f for f in r["findings"] if f["severity"] == "critical"]
        self.assertEqual(crit, [], f"CFN validator errors: {crit}")
        pol = [f for f in code_rules.evaluate_cfn(r["doc"]) if f["severity"] == "critical"]
        self.assertEqual(pol, [], f"CFN policy errors: {pol}")
        rc = validate_cdk(cdk, arch)
        crit = [f for f in rc["findings"] if f["severity"] == "critical"]
        self.assertEqual(crit, [], f"CDK validator errors: {crit}")
        pol = [f for f in code_rules.evaluate_cdk(cdk) if f["severity"] == "critical"]
        self.assertEqual(pol, [], f"CDK policy errors: {pol}")
        return plan, cfn, cdk, r

    def test_sample_architecture_all_options(self):
        a = with_opts(h.clean_arch(), ALL_OPTS)
        for env in ("development", "staging", "production"):
            plan, cfn, cdk, r = self.assert_valid(a, environment=env)
            self.assertTrue(plan.https and plan.logging and plan.monitoring)
            self.assertIn("CertificateArn", cfn)

    def test_sample_architecture_minimal(self):
        plan, cfn, cdk, r = self.assert_valid(h.clean_arch())
        doc = r["doc"]
        types = {v["Type"] for v in doc["Resources"].values()}
        for t in ("AWS::EC2::VPC", "AWS::EC2::Instance", "AWS::RDS::DBInstance", "AWS::S3::Bucket", "AWS::ElasticLoadBalancingV2::LoadBalancer"):
            self.assertIn(t, types)
        db = next(v for v in doc["Resources"].values() if v["Type"] == "AWS::RDS::DBInstance")["Properties"]
        self.assertIs(db["PubliclyAccessible"], False)
        self.assertIs(db["StorageEncrypted"], True)
        self.assertEqual(db["Engine"], "mysql")
        self.assertIn("ManageMasterUserPassword", db)
        self.assertNotIn("MasterUserPassword", db)

    def test_serverless_architecture(self):
        a = serverless_arch()
        for opts in ([], ALL_OPTS):
            plan, cfn, cdk, r = self.assert_valid(with_opts(a, opts))
            types = [v["Type"] for v in r["doc"]["Resources"].values()]
            for t in ("AWS::Lambda::Function", "AWS::DynamoDB::Table", "AWS::SQS::Queue", "AWS::SNS::Topic",
                      "AWS::Lambda::EventSourceMapping", "AWS::SNS::Subscription", "AWS::Lambda::Permission"):
                self.assertIn(t, types)

    def test_alb_without_targets_and_private_ec2_only(self):
        a = normalize_architecture({"network": {"vpc": True, "availability_zones": 2}, "services": [
            {"id": "lb", "type": "alb"}, {"id": "vm", "type": "ec2", "tier": "private"}], "connections": []})
        self.assert_valid(a)
        self.assert_valid(with_opts(a, ["https_tls", "monitoring"]))

    def test_engines(self):
        for eng in ("postgres", "mysql", "mariadb"):
            a = copy.deepcopy(h.clean_arch())
            a, _, _ = apply_ops(a, [{"op": "set_property", "target": "orders_db", "key": "engine", "value": eng}])
            plan, cfn, cdk, r = self.assert_valid(with_opts(a, ["cloudwatch_logging"]))
            port = {"postgres": 5432, "mysql": 3306, "mariadb": 3306}[eng]
            self.assertIn(f"Port.tcp({port})", cdk["lib/syntax-ai-stack.ts"])

    def test_least_privilege_policies_are_scoped(self):
        _, cfn, cdk, r = self.assert_valid(h.clean_arch())
        for lid, res in r["doc"]["Resources"].items():
            if res["Type"] == "AWS::IAM::Role":
                for pol in res["Properties"].get("Policies", []):
                    for st in pol["PolicyDocument"]["Statement"]:
                        acts = st["Action"] if isinstance(st["Action"], list) else [st["Action"]]
                        self.assertFalse(any(a.endswith("*") for a in acts))
                        self.assertNotEqual(st["Resource"], "*")

    def test_security_groups_reference_each_other(self):
        _, cfn, cdk, r = self.assert_valid(h.clean_arch())
        ingress = [v["Properties"] for v in r["doc"]["Resources"].values() if v["Type"] == "AWS::EC2::SecurityGroupIngress"]
        self.assertTrue(any(i["FromPort"] == 3306 for i in ingress))
        self.assertTrue(any(i["FromPort"] == 80 for i in ingress))
        self.assertTrue(all("SourceSecurityGroupId" in i for i in ingress))

    def test_cdk_project_files(self):
        _, _, cdk = self.build(h.clean_arch())
        self.assertEqual(set(cdk), {"bin/app.ts", "lib/syntax-ai-stack.ts", "package.json", "cdk.json", "tsconfig.json", ".gitignore"})
        self.assertIn("ap-south-1", cdk["bin/app.ts"])


class ValidatorTests(unittest.TestCase):
    def setUp(self):
        self.arch = h.clean_arch()
        plan = Plan(self.arch, {"environment": "production", "region": "us-east-1"})
        self.cfn = cfn_gen.generate(plan)
        self.cdk = {f["path"]: f["content"] for f in cdk_gen.generate(plan)}

    def codes(self, r):
        return {f["code"] for f in r["findings"] if f["severity"] == "critical"}

    def test_yaml_syntax_error_reported_with_location(self):
        r = validate_cfn("Resources:\n  A:\n    Type: AWS::S3::Bucket\n   Bad: [", self.arch)
        self.assertIn("CFN-YAML-SYNTAX", self.codes(r))
        self.assertFalse(r["ok"])

    def test_missing_reference_invalid_type_and_missing_prop(self):
        bad = self.cfn.replace("Ref: Vpc", "Ref: NoSuchVpc", 1).replace("AWS::S3::Bucket", "AWS::S4::Bucket", 1)
        r = validate_cfn(bad, self.arch)
        self.assertLessEqual({"CFN-REF-MISSING", "CFN-SERVICE-UNKNOWN"}, self.codes(r))
        r = validate_cfn("Resources:\n  V:\n    Type: AWS::EC2::VPC\n    Properties: {}\n")
        self.assertIn("CFN-MISSING-PROP", self.codes(r))

    def test_wrong_relationship_and_getatt_and_cycle_and_coverage(self):
        doc = validate_cfn(self.cfn)["doc"]
        inst = next(v for v in doc["Resources"].values() if v["Type"] == "AWS::EC2::Instance")
        inst["Properties"]["SubnetId"] = {"Ref": "Vpc"}
        r = validate_cfn(cfn_gen.dump_yaml(doc), self.arch)
        self.assertIn("CFN-REL-TYPE", self.codes(r))
        r = validate_cfn(self.cfn.replace("- DNSName", "- NoSuchAttr").replace("DNSName", "NoSuchAttr"), self.arch)
        self.assertIn("CFN-GETATT-INVALID", self.codes(r))
        cyc = ("Resources:\n  A:\n    Type: AWS::SQS::Queue\n    DependsOn: B\n  B:\n    Type: AWS::SQS::Queue\n    DependsOn: A\n")
        self.assertIn("CFN-CYCLE", self.codes(validate_cfn(cyc)))
        arch2 = copy.deepcopy(self.arch)
        arch2, _, _ = apply_ops(arch2, [{"op": "add_service", "type": "sqs", "id": "extra_q"}])
        self.assertIn("CFN-ARCH-MISSING", self.codes(validate_cfn(self.cfn, arch2)))

    def test_short_form_intrinsics_are_understood(self):
        t = "Resources:\n  V:\n    Type: AWS::EC2::VPC\n    Properties:\n      CidrBlock: 10.0.0.0/16\n  S:\n    Type: AWS::EC2::Subnet\n    Properties:\n      VpcId: !Ref V\n      CidrBlock: !Select [0, !Cidr [!GetAtt V.CidrBlock, 2, 8]]\n"
        self.assertTrue(validate_cfn(t)["ok"])
        self.assertIn("CFN-REF-MISSING", self.codes(validate_cfn(t.replace("!Ref V", "!Ref Nope"))))

    def test_policy_rules_catch_insecure_templates(self):
        doc = validate_cfn(self.cfn)["doc"]
        bucket = next(v for v in doc["Resources"].values() if v["Type"] == "AWS::S3::Bucket")
        del bucket["Properties"]["PublicAccessBlockConfiguration"]
        db = next(v for v in doc["Resources"].values() if v["Type"] == "AWS::RDS::DBInstance")
        db["Properties"]["PubliclyAccessible"] = True
        db["Properties"]["StorageEncrypted"] = False
        role = next(v for v in doc["Resources"].values() if v["Type"] == "AWS::IAM::Role")
        role["Properties"]["Policies"] = [{"PolicyName": "x", "PolicyDocument": {"Statement": [{"Effect": "Allow", "Action": "*", "Resource": "*"}]}}]
        doc["Resources"]["OpenSg"] = {"Type": "AWS::EC2::SecurityGroup", "Properties": {"GroupDescription": "x", "SecurityGroupIngress": [
            {"IpProtocol": "tcp", "FromPort": 22, "ToPort": 22, "CidrIp": "0.0.0.0/0"}]}}
        codes = {f["code"] for f in code_rules.evaluate_cfn(doc) if f["severity"] == "critical"}
        self.assertLessEqual({"SEC-S3-PUBLIC", "SEC-RDS-PUBLIC", "SEC-RDS-ENC", "SEC-IAM-ADMIN", "SEC-SG-OPEN"}, codes)

    def test_cdk_detects_syntax_import_and_construct_errors(self):
        stack = self.cdk["lib/syntax-ai-stack.ts"]
        r = validate_cdk({**self.cdk, "lib/syntax-ai-stack.ts": stack + "\n}"}, self.arch)
        self.assertIn("CDK-TS-SYNTAX", self.codes(r))
        r = validate_cdk({**self.cdk, "lib/syntax-ai-stack.ts": stack.replace("import * as rds from 'aws-cdk-lib/aws-rds';\n", "")}, self.arch)
        self.assertIn("CDK-IMPORT-MISSING", self.codes(r))
        r = validate_cdk({**self.cdk, "lib/syntax-ai-stack.ts": stack.replace("new s3.Bucket(", "new s3.Bukcet(")}, self.arch)
        self.assertIn("CDK-CONSTRUCT-INVALID", self.codes(r))
        typo = re.sub(r"(\w+Sg)\.addIngressRule", r"\1x.addIngressRule", stack, count=1)
        r = validate_cdk({**self.cdk, "lib/syntax-ai-stack.ts": typo}, self.arch)
        self.assertIn("CDK-UNDEFINED", self.codes(r))
        r = validate_cdk({k: v for k, v in self.cdk.items() if k != "package.json"}, self.arch)
        self.assertIn("CDK-FILE-MISSING", self.codes(r))
        pkg = self.cdk["package.json"].replace('"aws-cdk-lib"', '"aws-cdk-libx"')
        self.assertIn("CDK-DEP-MISSING", self.codes(validate_cdk({**self.cdk, "package.json": pkg}, self.arch)))

    def test_strip_code_ignores_strings_and_comments(self):
        self.assertEqual(strip_code("a('}}') // )))\n/* { */ b"), "a('') \n b")

    def test_autofix_cfn_repairs_and_revalidates(self):
        doc = validate_cfn(self.cfn)["doc"]
        bucket = next(v for v in doc["Resources"].values() if v["Type"] == "AWS::S3::Bucket")
        del bucket["Properties"]["PublicAccessBlockConfiguration"]
        del bucket["Properties"]["BucketEncryption"]
        db = next(v for v in doc["Resources"].values() if v["Type"] == "AWS::RDS::DBInstance")
        db["Properties"]["PubliclyAccessible"] = True
        db["Properties"]["StorageEncrypted"] = False
        broken = cfn_gen.dump_yaml(doc)
        findings = code_rules.evaluate_cfn(validate_cfn(broken)["doc"])
        self.assertGreaterEqual(len([f for f in findings if f["severity"] == "critical"]), 4)
        fixed, applied = fixer.fix_cfn(broken, findings, set())
        self.assertGreaterEqual(len(applied), 4)
        after = [f for f in code_rules.evaluate_cfn(validate_cfn(fixed)["doc"]) if f["severity"] == "critical"]
        self.assertEqual(after, [])
        # explicit override: the user's choice is respected, not silently "fixed"
        skip = {f["key"] for f in findings if f["code"] == "SEC-RDS-PUBLIC"}
        fixed2, _ = fixer.fix_cfn(broken, findings, skip)
        still = {f["code"] for f in code_rules.evaluate_cfn(validate_cfn(fixed2)["doc"])}
        self.assertIn("SEC-RDS-PUBLIC", still)

    def test_autofix_cdk_adds_missing_import(self):
        stack = self.cdk["lib/syntax-ai-stack.ts"].replace("import * as rds from 'aws-cdk-lib/aws-rds';\n", "")
        files = {**self.cdk, "lib/syntax-ai-stack.ts": stack}
        r = validate_cdk(files, self.arch)
        for f in r["findings"]:
            f["key"] = f"{f['code']}:{f.get('component') or '-'}"
        fixed, applied = fixer.fix_cdk(files, r["findings"], set())
        self.assertTrue(applied)
        self.assertEqual([f for f in validate_cdk(fixed, self.arch)["findings"] if f["severity"] == "critical"], [])


if __name__ == "__main__":
    unittest.main()
