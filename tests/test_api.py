import json
import os
import unittest
from unittest import mock

from tests import helpers as h
from app import bedrock_client, pipeline
from app.handler import lambda_handler


def call(method, path, body=None):
    ev = {"requestContext": {"http": {"method": method}}, "rawPath": path, "body": json.dumps(body) if body is not None else ""}
    res = lambda_handler(ev, None)
    return res["statusCode"], json.loads(res["body"]) if res["body"] else None


class ApiFlowTests(unittest.TestCase):
    def setUp(self):
        os.environ["ANALYSIS_FIXTURE"] = str(h.FIXTURE)

    def tearDown(self):
        os.environ.pop("ANALYSIS_FIXTURE", None)

    def test_full_workflow_end_to_end(self):
        # 1. analyze (image is sent once)
        st, a = call("POST", "/analyze", {"image_base64": h.png_b64()})
        self.assertEqual(st, 200)
        self.assertEqual(a["source"], "fixture")
        arch, issues = a["architecture"], a["issues"]
        self.assertIn("RDS-PUBLIC:orders_db", a["blocking"])
        self.assertLessEqual({"image_analysis_ms", "architecture_validation_ms", "total_ms"}, set(a["timings"]))

        # 2. generation is refused while criticals are open
        st, err = call("POST", "/generate", {"architecture": arch, "options": {"formats": ["cloudformation"]}})
        self.assertEqual(st, 409)
        self.assertEqual(err["error"]["code"], "ARCH_BLOCKED")

        # 3. Apply Correction for every blocking issue -> server returns updated arch + re-validated issues
        for issue_id in list(a["blocking"]):
            issue = next(i for i in issues if i["id"] == issue_id)
            st, p = call("POST", "/patch", {"architecture": arch, "ops": issue["fixes"]})
            self.assertEqual(st, 200)
            arch, issues = p["architecture"], p["issues"]
        self.assertEqual(p["blocking"], [])
        self.assertNotIn("RDS-PUBLIC:orders_db", h.ids(issues))

        # 4. refinement: checkboxes + free text (rule interpreter, Bedrock is disabled in tests)
        st, r = call("POST", "/refine", {"architecture": arch, "options": ["encryption", "backups", "https_tls"],
                                         "text": "use two availability zones and remove the mystery component"})
        self.assertEqual(st, 200)
        self.assertEqual(r["interpreter"], "rules")
        arch = r["architecture"]
        self.assertEqual(arch["network"]["availability_zones"], 2)
        self.assertFalse(any(s["id"] == "mystery" for s in arch["services"]))
        self.assertTrue(arch["requirements"]["https_tls"])

        # 5. code-generation requirements -> generate
        st, g = call("POST", "/generate", {"architecture": arch, "options": {
            "formats": ["cloudformation", "cdk"], "region": "ap-south-1", "environment": "production",
            "security": ["cloudwatch_logging", "monitoring"], "extra": "enable multi-az"}})
        self.assertEqual(st, 200, g)
        self.assertEqual(set(g["outputs"]), {"cloudformation", "cdk"})
        self.assertTrue(g["architecture"]["requirements"]["multi_az"])
        self.assertIn("code_generation_ms", g["timings"])

        # 6. verify (validation, auto-fix, security report)
        st, v = call("POST", "/verify", {"architecture": g["architecture"], "outputs": g["outputs"], "options": g["options"]})
        self.assertEqual(st, 200)
        self.assertTrue(v["verified"], v["outputs"]["cloudformation"]["blocking"])
        for fmt in ("cloudformation", "cdk"):
            o = v["outputs"][fmt]
            self.assertTrue(o["verified"])
            self.assertTrue(all(c["status"] != "fail" for c in o["checks"]))
            self.assertIn("steps", o["meta"])
        cfn_files = v["outputs"]["cloudformation"]["files"]
        self.assertEqual(cfn_files[0]["path"], "template.yaml")
        self.assertIn("--region ap-south-1", v["outputs"]["cloudformation"]["meta"]["deployment_command"])
        self.assertIn("cdk deploy", v["outputs"]["cdk"]["meta"]["deployment_command"])
        sr = v["security_report"]
        self.assertTrue(sr["deterministic"] and sr["disclaimer"] and sr["ai_advisory"])
        self.assertIn("multi_az", sr["user_requirements"])
        # the generated code refers to the detected components
        self.assertIn("OrdersDbDb", cfn_files[0]["content"])
        self.assertIn("orders_db", cfn_files[0]["content"])
        # real, measured timings
        total = sum(t["timings"]["total_ms"] for t in (a, r, g, v))
        self.assertGreaterEqual(total, 0)
        print(f"\n  measured backend pipeline (fixture analysis): analyze={a['timings']['total_ms']}ms refine={r['timings']['total_ms']}ms "
              f"generate={g['timings']['total_ms']}ms verify={v['timings']['total_ms']}ms")

    def test_override_allows_generation_and_is_recorded(self):
        st, a = call("POST", "/analyze", {"image_base64": h.png_b64()})
        blocking = a["blocking"]
        st, g = call("POST", "/generate", {"architecture": a["architecture"], "overrides": blocking,
                                           "options": {"formats": ["cloudformation"], "environment": "development"}})
        self.assertEqual(st, 200, g)
        # the RDS is really generated public (user explicitly overrode) and verify marks it overridden, not silently fixed
        st, v = call("POST", "/verify", {"architecture": g["architecture"], "outputs": g["outputs"], "options": g["options"],
                                         "overrides": blocking + ["SEC-RDS-PUBLIC:orders_db"]})
        self.assertEqual(st, 200)
        # overriding the architecture issue alone also covers the matching code finding
        st, v_arch_only = call("POST", "/verify", {"architecture": g["architecture"], "outputs": g["outputs"], "options": g["options"], "overrides": blocking})
        self.assertFalse(v_arch_only["outputs"]["cloudformation"]["fix_log"])
        f = [x for x in v["outputs"]["cloudformation"]["findings"] if x["code"] == "SEC-RDS-PUBLIC"]
        self.assertTrue(f and f[0]["overridden"])
        # without the override the verifier auto-fixes it
        st, v2 = call("POST", "/verify", {"architecture": g["architecture"], "outputs": g["outputs"], "options": g["options"],
                                          "overrides": [b for b in blocking if not b.startswith("RDS-PUBLIC")]})
        fixed = v2["outputs"]["cloudformation"]
        self.assertTrue(fixed["fix_log"])
        self.assertIn("PubliclyAccessible: false", fixed["files"][0]["content"])

    def test_edited_code_is_revalidated_and_errors_are_reported(self):
        arch = h.clean_arch()
        st, g = call("POST", "/generate", {"architecture": arch, "options": {"formats": ["cloudformation"]}})
        files = g["outputs"]["cloudformation"]["files"]
        files[0]["content"] = files[0]["content"].replace("Ref: Vpc\n", "Ref: NotThere\n", 1)
        st, v = call("POST", "/verify", {"architecture": g["architecture"], "outputs": {"cloudformation": {"files": files}}, "options": g["options"]})
        self.assertEqual(st, 200)
        self.assertFalse(v["verified"])
        self.assertTrue(any(f["code"] == "CFN-REF-MISSING" for f in v["outputs"]["cloudformation"]["findings"]))

    def test_error_handling(self):
        self.assertEqual(call("POST", "/analyze", {})[1]["error"]["code"], "NO_IMAGE")
        self.assertEqual(call("POST", "/analyze", {"image_base64": "aGVsbG8gd29ybGQ="})[1]["error"]["code"], "BAD_IMAGE")
        big = h.make_png() + b"0" * 4_000_000
        import base64
        st, e = call("POST", "/analyze", {"image_base64": base64.b64encode(big).decode()})
        self.assertEqual((st, e["error"]["code"]), (413, "IMAGE_TOO_LARGE"))
        self.assertEqual(call("POST", "/generate", {"architecture": {"nope": 1}})[1]["error"]["code"], "BAD_ARCHITECTURE")
        self.assertEqual(call("GET", "/nothing")[0], 404)
        ev = {"requestContext": {"http": {"method": "POST"}}, "rawPath": "/analyze", "body": "{not json"}
        self.assertEqual(json.loads(lambda_handler(ev)["body"])["error"]["code"], "BAD_JSON")
        st, e = call("POST", "/generate", {"architecture": h.clean_arch(), "options": {"formats": []}})
        self.assertEqual(e["error"]["code"], "NO_FORMAT")
        st, e = call("POST", "/generate", {"architecture": h.clean_arch(), "options": {"region": "mars-1"}})
        self.assertEqual(e["error"]["code"], "BAD_REGION")
        os.environ.pop("ANALYSIS_FIXTURE")
        st, e = call("POST", "/analyze", {"image_base64": h.png_b64()})
        self.assertEqual((st, e["error"]["code"]), (503, "BEDROCK_NOT_CONFIGURED"))
        self.assertEqual(call("OPTIONS", "/analyze")[0], 204)
        self.assertEqual(call("GET", "/health")[1]["ok"], True)

    def test_no_components_detected(self):
        with mock.patch.dict(os.environ, {"ANALYSIS_FIXTURE": ""}):
            os.environ.pop("ANALYSIS_FIXTURE")
            with mock.patch.dict(os.environ, {"BEDROCK_MODEL_ID": "test-model", "BEDROCK_DISABLED": "0"}), \
                    mock.patch.object(bedrock_client, "analyze_image", return_value={"services": [], "image_quality": "poor", "image_quality_notes": "blank"}):
                st, e = call("POST", "/analyze", {"image_base64": h.png_b64(), "force": True})
        self.assertEqual((st, e["error"]["code"]), (422, "NO_COMPONENTS"))
        self.assertEqual(e["error"]["details"]["image_quality"], "poor")


class BedrockPathTests(unittest.TestCase):
    """Bedrock behaviour with a stubbed runtime client (no AWS access needed)."""

    def setUp(self):
        self.env = mock.patch.dict(os.environ, {"BEDROCK_MODEL_ID": "test-model", "BEDROCK_DISABLED": "0"})
        self.env.start()
        os.environ.pop("ANALYSIS_FIXTURE", None)

    def tearDown(self):
        self.env.stop()

    def converse_returning(self, *texts):
        it = iter(texts)

        def converse(**kw):
            self.last = kw
            t = next(it)
            if isinstance(t, Exception):
                raise t
            return {"output": {"message": {"content": [{"text": t}]}}, "stopReason": "end_turn"}
        client = mock.Mock()
        client.converse.side_effect = converse
        return mock.patch.object(bedrock_client, "_get_client", return_value=client), client

    def test_analyze_sends_image_once_and_caches(self):
        payload = json.dumps(h.raw_analysis())
        p, client = self.converse_returning("```json\n" + payload + "\n```")
        from app import store
        store._mem.clear()
        with p:
            r1 = call("POST", "/analyze", {"image_base64": h.png_b64()})[1]
            r2 = call("POST", "/analyze", {"image_base64": h.png_b64()})[1]
        self.assertEqual((r1["source"], r2["source"]), ("bedrock", "cache"))
        self.assertEqual(client.converse.call_count, 1)  # second analysis served from cache, no second Bedrock call
        blocks = self.last["messages"][0]["content"]
        self.assertIn("image", blocks[0])
        self.assertEqual(self.last["inferenceConfig"]["temperature"], 0)
        self.assertIn("NEVER guess", self.last["system"][0]["text"])
        self.assertLess(r2["timings"]["total_ms"], 1000)

    def test_malformed_json_is_repaired_without_resending_image(self):
        payload = json.dumps(h.raw_analysis())
        p, client = self.converse_returning('{"services": [ {"id": "a", "type": ', payload)
        from app import store
        store._mem.clear()
        with p:
            st, r = call("POST", "/analyze", {"image_base64": h.png_b64(), "force": True})
        self.assertEqual(st, 200)
        self.assertEqual(client.converse.call_count, 2)
        second = client.converse.call_args.kwargs["messages"][0]["content"]
        self.assertTrue(all("image" not in b for b in second))

    def test_unrecoverable_malformed_response_is_a_clean_retryable_error(self):
        p, client = self.converse_returning("no json here", "still not json")
        with p:
            st, e = call("POST", "/analyze", {"image_base64": h.png_b64(), "force": True})
        self.assertEqual((st, e["error"]["code"], e["error"]["retryable"]), (502, "BEDROCK_MALFORMED", True))

    def test_throttling_is_reported_retryable(self):
        class Throttle(Exception):
            response = {"Error": {"Code": "ThrottlingException"}}
        p, _ = self.converse_returning(Throttle("slow down"))
        with p:
            st, e = call("POST", "/analyze", {"image_base64": h.png_b64(), "force": True})
        self.assertEqual((st, e["error"]["code"], e["error"]["retryable"]), (502, "BEDROCK_ERROR", True))

    def test_refinement_uses_bedrock_ops_but_whitelists_them(self):
        ops = {"ops": [{"op": "set_property", "target": "orders_db", "key": "public", "value": False},
                       {"op": "set_tier", "target": "orders_db", "tier": "private"},
                       {"op": "delete_everything"}], "unmapped": ["use my company tagging standard"]}
        p, client = self.converse_returning(json.dumps(ops))
        with p:
            st, r = call("POST", "/refine", {"architecture": h.sample_arch(), "text": "make the db private and use our tagging standard"})
        self.assertEqual((st, r["interpreter"]), (200, "bedrock"))
        db = next(s for s in r["architecture"]["services"] if s["id"] == "orders_db")
        self.assertEqual(db["tier"], "private")
        self.assertEqual(len(r["rejected"]), 1)
        self.assertEqual(r["unmapped"], ["use my company tagging standard"])
        self.assertNotIn("RDS-PUBLIC:orders_db", h.ids(r["issues"]))

    def test_refinement_falls_back_to_rules_when_bedrock_fails(self):
        p, _ = self.converse_returning(RuntimeError("boom"))
        with p:
            st, r = call("POST", "/refine", {"architecture": h.sample_arch(), "text": "enable encryption"})
        self.assertEqual((st, r["interpreter"]), (200, "rules"))
        self.assertTrue(r["warnings"])

    def test_ai_fix_is_used_only_for_what_rules_cannot_fix(self):
        arch = h.clean_arch()
        st, g = call("POST", "/generate", {"architecture": arch, "options": {"formats": ["cloudformation"]}})
        files = g["outputs"]["cloudformation"]["files"]
        broken = files[0]["content"].replace("Ref: Vpc\n", "Ref: NotThere\n", 1)
        files[0]["content"] = broken
        p, client = self.converse_returning(json.dumps({"files": {"template.yaml": g["outputs"]["cloudformation"]["files"][0]["content"].replace("NotThere", "Vpc")}, "explanation": "fixed the Ref"}))
        with p:
            st, v = call("POST", "/verify", {"architecture": g["architecture"], "outputs": {"cloudformation": {"files": files}}, "options": g["options"]})
        out = v["outputs"]["cloudformation"]
        self.assertTrue(v["verified"])
        self.assertEqual(out["fix_log"][0]["how"], "ai")
        self.assertEqual(client.converse.call_count, 1)


if __name__ == "__main__":
    unittest.main()
