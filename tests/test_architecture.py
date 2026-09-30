import copy
import unittest

from tests import helpers as h  # noqa: F401  (sets up sys.path / env)
from app.architecture import apply_ops, normalize_architecture, options_to_ops
from app.policy_engine import blocking_issues, evaluate_architecture
from app.text_rules import interpret


class ArchitectureTests(unittest.TestCase):
    def setUp(self):
        self.arch = h.sample_arch()

    def test_normalize_maps_types_and_flags_unknown(self):
        types = {s["id"]: s["type"] for s in self.arch["services"]}
        self.assertEqual((types["web_alb"], types["orders_db"], types["mystery"]), ("alb", "rds", "other"))
        bad = [c for c in self.arch["connections"] if c["unresolved"]]
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]["to"], "ghost_component")

    def test_normalize_survives_garbage(self):
        for junk in (None, [], "x", {"services": "nope"}, {"services": [None, 3, {}], "connections": [1, {"from": 1}]}):
            self.assertIsInstance(normalize_architecture(junk)["services"], list)

    def test_normalize_folds_network_items_and_aliases(self):
        a = normalize_architecture({"services": [
            {"id": "v", "type": "VPC", "label": "VPC"}, {"id": "s1", "type": "Subnet", "label": "Public Subnet"},
            {"id": "lb", "type": "Elastic Load Balancer", "label": "ELB"}, {"id": "db", "type": "Amazon Aurora MySQL", "label": "db"}]})
        self.assertTrue(a["network"]["vpc"])
        self.assertEqual(a["network"]["subnets"][0]["tier"], "public")
        self.assertEqual([s["type"] for s in a["services"]], ["alb", "rds"])

    def test_rules_find_expected_issues(self):
        issues = evaluate_architecture(self.arch)
        got = h.ids(issues)
        self.assertIn("RDS-PUBLIC:orders_db", h.ids(issues, "critical"))
        for expected in ("CONN-INVALID:mystery->ghost_component", "AMBIG-COMPONENT:mystery", "ENC-UNSPECIFIED:assets",
                         "RDS-BACKUP:orders_db", "NET-AZ:-", "EC2-PUBLIC-BEHIND-ALB:app_server"):
            self.assertIn(expected, got)
        self.assertTrue(any(i["source"] == "ai" for i in issues))
        self.assertTrue(any(i["severity"] == "valid" for i in issues))
        for i in issues:
            self.assertLessEqual({"problem", "reason", "suggestion", "fixes", "severity", "source"}, set(i))

    def test_critical_blocks_until_fixed_or_overridden(self):
        issues = evaluate_architecture(self.arch)
        blocking = {i["id"] for i in blocking_issues(issues)}
        self.assertIn("RDS-PUBLIC:orders_db", blocking)
        self.assertIn("CONN-INVALID:mystery->ghost_component", blocking)
        self.assertFalse(blocking_issues(issues, overrides=list(blocking)))
        self.assertTrue(all(i["source"] == "deterministic" for i in blocking_issues(issues)))  # AI advisories never block

    def test_apply_correction_updates_architecture_and_clears_issue(self):
        issue = next(i for i in evaluate_architecture(self.arch) if i["id"] == "RDS-PUBLIC:orders_db")
        new, applied, rejected = apply_ops(self.arch, issue["fixes"])
        db = next(s for s in new["services"] if s["id"] == "orders_db")
        self.assertEqual((db["tier"], db["properties"]["public"]), ("private", False))
        self.assertTrue(applied)
        self.assertFalse(rejected)
        self.assertNotIn("RDS-PUBLIC:orders_db", h.ids(evaluate_architecture(new)))
        self.assertEqual(next(s for s in self.arch["services"] if s["id"] == "orders_db")["tier"], "public")  # original untouched

    def test_ops_are_whitelisted_and_validated(self):
        _, applied, rejected = apply_ops(self.arch, [
            {"op": "drop_database"}, {"op": "set_property", "target": "nope", "key": "public", "value": True},
            {"op": "set_property", "target": "orders_db", "key": "iam_admin", "value": True},
            {"op": "set_property", "target": "orders_db", "key": "backup_retention", "value": 999},
            {"op": "set_azs", "value": 9}, "junk"])
        self.assertFalse(applied)
        self.assertEqual(len(rejected), 6)

    def test_direct_internet_to_ec2_fix_adds_alb(self):
        a = normalize_architecture({"services": [
            {"id": "internet", "type": "internet", "label": "Users"}, {"id": "web", "type": "ec2", "label": "Web", "tier": "public"}],
            "connections": [{"from": "internet", "to": "web"}]})
        issue = next(i for i in evaluate_architecture(a) if i["code"] == "EC2-DIRECT-INTERNET")
        new, applied, rejected = apply_ops(a, issue["fixes"])
        self.assertFalse(rejected)
        conns = {(c["from"], c["to"]) for c in new["connections"]}
        self.assertIn(("internet", "alb"), conns)
        self.assertIn(("alb", "web"), conns)
        self.assertNotIn(("internet", "web"), conns)

    def test_options_map_to_real_changes(self):
        ops = options_to_ops(self.arch, ["encryption", "private_subnets", "multi_az", "backups", "bogus"])
        new, _, rej = apply_ops(self.arch, ops)
        db = next(s for s in new["services"] if s["id"] == "orders_db")
        self.assertFalse(rej)
        self.assertTrue(db["properties"]["encrypted"] and db["properties"]["multi_az"])
        self.assertEqual(db["properties"]["backup_retention"], 7)
        self.assertEqual(new["network"]["availability_zones"], 2)
        self.assertEqual(next(s for s in new["services"] if s["id"] == "app_server")["tier"], "private")
        self.assertTrue(new["requirements"]["encryption"] and new["requirements"]["multi_az"])

    def test_text_interpreter_rules(self):
        ops, unmapped = interpret(self.arch, "Make RDS private, enable encryption, use least-privilege IAM, enable backups and deploy across two Availability Zones. Paint it blue.")
        new, applied, rejected = apply_ops(self.arch, ops)
        db = next(s for s in new["services"] if s["id"] == "orders_db")
        self.assertEqual((db["tier"], db["properties"]["public"], db["properties"]["encrypted"]), ("private", False, True))
        self.assertEqual(new["network"]["availability_zones"], 2)
        self.assertTrue(new["requirements"]["iam_least_privilege"])
        self.assertTrue(any("blue" in u for u in unmapped))
        self.assertFalse(rejected)

    def test_text_interpreter_add_alb_and_connect(self):
        a = normalize_architecture({"services": [{"id": "internet", "type": "internet"}, {"id": "web", "type": "ec2", "label": "Web", "tier": "private"}]})
        ops, _ = interpret(a, "add an application load balancer")
        new, _, _ = apply_ops(a, ops)
        self.assertTrue(any(s["type"] == "alb" for s in new["services"]))
        self.assertIn(("alb", "web"), {(c["from"], c["to"]) for c in new["connections"]})


if __name__ == "__main__":
    unittest.main()
