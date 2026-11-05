import hashlib
import json
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bootstrap  # noqa: E402
from _bootstrap import Clock, load_contract  # noqa: E402
import genlayer_stub as stub  # noqa: E402
from genlayer_stub import Address, u256, gl, call  # noqa: E402

GEN = 10 ** 18
REPO = "acme/tuned-llama"
REV = "a" * 40
BASE = "meta-llama/Llama-3-8B"
LICENSE = "apache-2.0"
SHA = "ab" * 32
README = "This model is fine-tuned for support ticket classification and evaluated on a held-out set."
SPEC = "Fine-tune Llama-3-8B for support ticket classification and publish the weights."


def A(n):
    return Address("0x" + format(n, "040x"))


OWNER, BUYER, TRAINER, STRANGER = A(1), A(2), A(3), A(4)
JURORS = [A(100 + i) for i in range(10)]


def api_json(**over):
    data = {
        "id": REPO,
        "sha": REV,
        "cardData": {"base_model": BASE, "license": LICENSE},
        "tags": [],
        "siblings": [
            {"rfilename": "model.safetensors", "size": 5_000_000_000, "lfs": {"sha256": SHA, "size": 5_000_000_000}},
            {"rfilename": "README.md", "size": 100},
        ],
    }
    data.update(over)
    return json.dumps(data)


class Base:
    FILE = "tunepact.py"

    def setUp(self):
        self.m = load_contract(self.FILE)
        Clock.now_ts = 1_800_000_000
        stub._Web.routes = {}
        stub._Web.fetched = []
        stub._Nondet.prompts = []
        stub._Vm.before_validator = None
        self.verdict = "DELIVERED"
        stub._Nondet.llm = lambda prompt: {"verdict": self.verdict, "quoted_evidence": README[:40]}
        gl.message.sender_address = OWNER
        self.c = self.m.TunePact()
        self.set_hf()

    def tx(self, method, sender, value=0, **kw):
        for k, v in list(kw.items()):
            if k in ("deal_id", "round_no", "payment_amount", "expected_min_total_size_bytes") and not isinstance(v, u256):
                kw[k] = u256(v)
        return call(self.c, method, sender, value, **kw)

    def j(self, method, sender=STRANGER, **kw):
        return json.loads(self.tx(method, sender, **kw))

    def set_hf(self, api=None, readme=README):
        urls = self.m.hf_urls(REPO, REV)
        stub._Web.routes[urls[0]] = (200, (api if api is not None else api_json()).encode())
        if readme is None:
            stub._Web.routes.pop(urls[1], None)
        else:
            stub._Web.routes[urls[1]] = (200, readme.encode())

    def make_deal(self, fund=True, payment=10 * GEN, **over):
        args = dict(trainer=TRAINER.as_hex, payment_amount=payment, task_spec=SPEC, expected_repo_id=REPO,
                    expected_weights_prefix="model", expected_min_total_size_bytes=1_000_000_000,
                    expected_base_model=BASE, required_license=LICENSE, expected_sha256="")
        args.update(over)
        res = self.tx("create_deal", BUYER, value=payment if fund else 0, **args)
        self.assertTrue(res.startswith("OK:"), res)
        return int(res.split(":")[1])

    def submitted(self, **over):
        did = self.make_deal(**over)
        self.assertEqual(self.tx("submit_delivery", TRAINER, deal_id=did, delivered_revision=REV), "OK")
        return did

    def to_tier1(self, verdict="DELIVERED", **over):
        self.verdict = verdict
        did = self.submitted(**over)
        res = self.tx("run_tier1_verdict", STRANGER, deal_id=did)
        self.assertTrue(res.startswith("OK:"), res)
        return did

    def register_jurors(self, n=9):
        for a in JURORS[:n]:
            r = self.tx("register_as_juror", a, value=self.m.JUROR_BOND_AMOUNT + self.m.JUROR_REGISTRATION_FEE)
            self.assertEqual(r, "OK")
        Clock.advance(10)

    def deal(self, did):
        return self.j("get_deal", deal_id=did)

    def acct(self):
        return self.j("get_accounting")

    def assertBalanced(self):
        a = self.acct()
        self.assertTrue(a["balanced"], a)

    def withdrawable(self, who):
        return int(self.tx("get_withdrawable", STRANGER, addr=who.as_hex))

    def selected(self, did, rnd):
        return [Address(x) for x in self.j("get_jury_round", deal_id=did, round_no=rnd)["selected"]]

    @staticmethod
    def commit_hash(vote, salt, who):
        return hashlib.sha256((vote + ":" + salt + ":" + who.as_hex.lower()).encode()).hexdigest()

    def run_round(self, did, rnd, votes):
        sel = self.selected(did, rnd)
        for who, vote in zip(sel, votes):
            if vote is None:
                continue
            self.assertEqual(self.tx("commit_jury_vote", who, deal_id=did, commit_hash=self.commit_hash(vote, "s", who)), "OK")
        for who, vote in zip(sel, votes):
            if vote is None:
                continue
            if self.j("get_jury_round", deal_id=did, round_no=rnd)["phase"] != "REVEAL":
                break
            self.assertEqual(self.tx("reveal_jury_vote", who, deal_id=did, vote=vote, salt="s"), "OK")
        return sel

    def appeal(self, did, who=TRAINER):
        d = self.deal(did)
        res = self.tx("escalate_to_jury", who, value=int(d["payment_amount"]) * 0 + max(self.m.MIN_APPEAL_BOND, int(d["payment_amount"]) * self.m.APPEAL_BOND_BPS // 10000), deal_id=did)
        return res

    # ---------------- creation ----------------
    def test_create_unfunded_and_fund(self):
        did = self.make_deal(fund=False)
        self.assertEqual(self.deal(did)["status"], "CREATED")
        self.assertEqual(self.tx("fund_deal", BUYER, value=10 * GEN, deal_id=did), "OK")
        self.assertEqual(self.deal(did)["status"], "FUNDED")
        self.assertEqual(self.acct()["total_escrow_held"], str(10 * GEN))
        self.assertBalanced()

    def test_create_funded(self):
        did = self.make_deal()
        self.assertEqual(self.deal(did)["status"], "FUNDED")
        self.assertBalanced()
        self.assertEqual(len(self.j("list_deals")), 1)

    def test_invalid_create_refunds_value(self):
        res = self.tx("create_deal", BUYER, value=10 * GEN, trainer=BUYER.as_hex, payment_amount=10 * GEN, task_spec=SPEC,
                      expected_repo_id=REPO, expected_weights_prefix="model", expected_min_total_size_bytes=1,
                      expected_base_model=BASE, required_license=LICENSE, expected_sha256="")
        self.assertEqual(res, "ERR_BAD_TRAINER")
        self.assertEqual(self.withdrawable(BUYER), 10 * GEN)
        self.assertBalanced()
        self.assertEqual(len(self.j("list_deals")), 0)

    def test_value_mismatch_refunds(self):
        res = self.tx("create_deal", BUYER, value=3 * GEN, trainer=TRAINER.as_hex, payment_amount=10 * GEN, task_spec=SPEC,
                      expected_repo_id=REPO, expected_weights_prefix="model", expected_min_total_size_bytes=1,
                      expected_base_model=BASE, required_license=LICENSE, expected_sha256="")
        self.assertEqual(res, "ERR_VALUE_MISMATCH")
        self.assertEqual(self.withdrawable(BUYER), 3 * GEN)
        self.assertBalanced()

    def test_input_validation_errors(self):
        cases = [
            (dict(payment=200 * GEN), "ERR_PAYMENT_RANGE"),
            (dict(task_spec="short"), "ERR_TASK_SPEC"),
            (dict(expected_repo_id="no-slash"), "ERR_REPO_ID"),
            (dict(expected_weights_prefix=""), "ERR_WEIGHTS_PREFIX"),
            (dict(expected_min_total_size_bytes=0), "ERR_MIN_SIZE"),
            (dict(expected_base_model=""), "ERR_BASE_MODEL"),
            (dict(required_license=""), "ERR_LICENSE"),
            (dict(expected_sha256="xyz"), "ERR_SHA256"),
            (dict(trainer="0x123"), "ERR_BAD_TRAINER"),
        ]
        for over, err in cases:
            payment = over.pop("payment", 10 * GEN)
            args = dict(trainer=TRAINER.as_hex, payment_amount=payment, task_spec=SPEC, expected_repo_id=REPO,
                        expected_weights_prefix="model", expected_min_total_size_bytes=1000,
                        expected_base_model=BASE, required_license=LICENSE, expected_sha256="")
            args.update(over)
            self.assertEqual(self.tx("create_deal", BUYER, value=0, **args), err, over)

    def test_fund_wrong_value_and_wrong_sender_refunded(self):
        did = self.make_deal(fund=False)
        self.assertEqual(self.tx("fund_deal", BUYER, value=GEN, deal_id=did), "ERR_VALUE_MISMATCH")
        self.assertEqual(self.tx("fund_deal", STRANGER, value=10 * GEN, deal_id=did), "ERR_NOT_BUYER")
        self.assertEqual(self.withdrawable(BUYER), GEN)
        self.assertEqual(self.withdrawable(STRANGER), 10 * GEN)
        self.assertBalanced()

    def test_cancel_unfunded(self):
        did = self.make_deal(fund=False)
        self.assertEqual(self.tx("cancel_unfunded", STRANGER, deal_id=did), "ERR_NOT_BUYER")
        self.assertEqual(self.tx("cancel_unfunded", BUYER, deal_id=did), "OK")
        self.assertEqual(self.deal(did)["status"], "CANCELLED")

    def test_non_payable_rejects_value(self):
        did = self.make_deal()
        with self.assertRaises(AssertionError):
            self.tx("submit_delivery", TRAINER, value=GEN, deal_id=did, delivered_revision=REV)

    # ---------------- delivery ----------------
    def test_submit_delivery_rules(self):
        did = self.make_deal()
        self.assertEqual(self.tx("submit_delivery", STRANGER, deal_id=did, delivered_revision=REV), "ERR_NOT_TRAINER")
        self.assertEqual(self.tx("submit_delivery", TRAINER, deal_id=did, delivered_revision="main"), "ERR_BAD_REVISION")
        Clock.advance(self.m.DELIVERY_DEADLINE_SEC + 1)
        self.assertEqual(self.tx("submit_delivery", TRAINER, deal_id=did, delivered_revision=REV), "ERR_DEADLINE_PASSED")

    def test_delivery_timeout_refunds_buyer(self):
        did = self.make_deal()
        self.assertEqual(self.tx("claim_delivery_timeout", STRANGER, deal_id=did), "ERR_NOT_EXPIRED")
        Clock.advance(self.m.DELIVERY_DEADLINE_SEC + 1)
        self.assertEqual(self.tx("claim_delivery_timeout", STRANGER, deal_id=did), "OK")
        self.assertEqual(self.deal(did)["status"], "REFUNDED")
        self.assertEqual(self.withdrawable(BUYER), 10 * GEN)
        self.assertBalanced()

    # ---------------- tier 1 ----------------
    def test_delivered_unappealed_pays_trainer_minus_fee(self):
        did = self.to_tier1("DELIVERED")
        self.assertEqual(self.deal(did)["status"], "TIER1_VERDICT")
        self.assertEqual(self.tx("finalize_unappealed", STRANGER, deal_id=did), "ERR_WINDOW_OPEN")
        Clock.advance(self.m.CHALLENGE_WINDOW_SEC + 1)
        self.assertEqual(self.tx("finalize_unappealed", STRANGER, deal_id=did), "OK:DELIVERED")
        self.assertEqual(self.withdrawable(TRAINER), 10 * GEN - GEN // 10)
        self.assertEqual(self.acct()["treasury_balance"], str(GEN // 10))
        self.assertBalanced()

    def test_partial_split(self):
        did = self.to_tier1("PARTIALLY_DELIVERED")
        Clock.advance(self.m.CHALLENGE_WINDOW_SEC + 1)
        self.tx("finalize_unappealed", STRANGER, deal_id=did)
        self.assertEqual(self.withdrawable(BUYER), 5 * GEN)
        self.assertEqual(self.withdrawable(TRAINER), 5 * GEN - GEN // 20)
        self.assertBalanced()

    def test_not_delivered_refunds(self):
        did = self.to_tier1("NOT_DELIVERED")
        Clock.advance(self.m.CHALLENGE_WINDOW_SEC + 1)
        self.tx("finalize_unappealed", STRANGER, deal_id=did)
        self.assertEqual(self.deal(did)["status"], "REFUNDED")
        self.assertEqual(self.withdrawable(BUYER), 10 * GEN)
        self.assertBalanced()

    def test_anchor_mismatch_forces_undetermined_without_llm(self):
        self.set_hf(api_json(cardData={"base_model": "other/model", "license": LICENSE}))
        did = self.to_tier1("DELIVERED")
        d = self.deal(did)
        self.assertEqual(d["tier1_verdict"], "UNDETERMINED")
        self.assertEqual(stub._Nondet.prompts, [])
        self.assertIn("Base model", self.j("get_deal_for_jury", deal_id=did)["reason"])

    def test_revision_mismatch_forces_undetermined(self):
        self.set_hf(api_json(sha="b" * 40))
        did = self.to_tier1("DELIVERED")
        self.assertEqual(self.deal(did)["tier1_verdict"], "UNDETERMINED")

    def test_small_weights_forces_undetermined(self):
        did = self.to_tier1("DELIVERED", expected_min_total_size_bytes=9_000_000_000)
        self.assertEqual(self.deal(did)["tier1_verdict"], "UNDETERMINED")

    def test_sha256_anchor(self):
        did = self.to_tier1("DELIVERED", expected_sha256=SHA)
        self.assertEqual(self.deal(did)["tier1_verdict"], "DELIVERED")
        did2 = self.to_tier1("DELIVERED", expected_sha256="cd" * 32)
        self.assertEqual(self.deal(did2)["tier1_verdict"], "UNDETERMINED")

    def test_fabricated_quote_forced_undetermined(self):
        stub._Nondet.llm = lambda p: {"verdict": "DELIVERED", "quoted_evidence": "this text is not in the readme at all"}
        did = self.submitted()
        self.tx("run_tier1_verdict", STRANGER, deal_id=did)
        self.assertEqual(self.deal(did)["tier1_verdict"], "UNDETERMINED")

    def test_missing_readme_is_undetermined(self):
        self.set_hf(readme=None)
        did = self.to_tier1("DELIVERED")
        self.assertEqual(self.deal(did)["tier1_verdict"], "UNDETERMINED")
        self.assertIn("README", self.j("get_deal_for_jury", deal_id=did)["reason"])

    def test_repo_not_found_is_undetermined(self):
        stub._Web.routes[self.m.hf_urls(REPO, REV)[0]] = (404, b"")
        did = self.to_tier1("DELIVERED")
        self.assertEqual(self.deal(did)["tier1_verdict"], "UNDETERMINED")

    def test_fetch_error_consumes_attempt_and_caps(self):
        stub._Web.routes[self.m.hf_urls(REPO, REV)[0]] = (500, b"")
        did = self.submitted()
        for _ in range(self.m.MAX_TIER1_ATTEMPTS):
            self.assertEqual(self.tx("run_tier1_verdict", STRANGER, deal_id=did), "ERR_FETCH_RETRY")
        self.assertEqual(self.tx("run_tier1_verdict", STRANGER, deal_id=did), "ERR_MAX_ATTEMPTS")
        self.assertEqual(self.deal(did)["status"], "SUBMITTED")
        Clock.advance(self.m.STUCK_TIMEOUT_SEC + 1)
        self.assertEqual(self.tx("recover_stuck_deal", STRANGER, deal_id=did), "OK")
        self.assertEqual(self.deal(did)["status"], "REFUNDED")
        self.assertBalanced()

    def test_validator_disagreement_rolls_back(self):
        did = self.submitted()
        urls = self.m.hf_urls(REPO, REV)

        def swap():
            stub._Web.routes[urls[0]] = (200, api_json(cardData={"base_model": "x/y", "license": LICENSE}).encode())

        stub._Vm.before_validator = swap
        with self.assertRaises(RuntimeError):
            self.tx("run_tier1_verdict", STRANGER, deal_id=did)
        self.assertEqual(self.deal(did)["status"], "SUBMITTED")
        self.assertEqual(self.deal(did)["tier1_attempts"], 0)

    def test_snapshot_stores_observed_values(self):
        did = self.to_tier1("DELIVERED", expected_sha256=SHA)
        s = self.j("get_deal_for_jury", deal_id=did)
        self.assertEqual(s["base_model"], BASE.lower())
        self.assertEqual(s["license"], LICENSE)
        self.assertEqual(s["sha256"], SHA)
        self.assertEqual(s["repo_commit_sha"], REV)
        self.assertEqual(s["weights_total_bytes"], "5000000000")
        self.assertTrue(s["anchor_match"])

    def test_prompt_is_bounded_and_marks_untrusted_text(self):
        long_readme = README + " " + "x" * 10000
        self.set_hf(readme=long_readme)
        self.to_tier1("DELIVERED")
        p = stub._Nondet.prompts[-1]
        self.assertIn("UNTRUSTED", p)
        self.assertLess(len(p), self.m.README_PROMPT_CHARS + 2000)

    def test_tier1_only_in_submitted_state(self):
        did = self.make_deal()
        self.assertEqual(self.tx("run_tier1_verdict", STRANGER, deal_id=did), "ERR_INVALID_STATUS")

    # ---------------- parse helper ----------------
    def test_parse_uses_tags_and_oid_fallback(self):
        data = json.loads(api_json(cardData={}, tags=["base_model:" + BASE, "license:apache-2.0"]))
        data["siblings"][0]["lfs"] = {"oid": "sha256:" + SHA}
        anchors = dict(expected_repo_id=REPO, delivered_revision=REV, expected_weights_prefix="model",
                       expected_min_total_size_bytes=1, expected_base_model=BASE, required_license=LICENSE,
                       expected_sha256=SHA)
        out = self.m.parse_hf_evidence(json.dumps(data), README, anchors)
        self.assertTrue(out["anchor_match"], out)

    def test_parse_rejects_non_json(self):
        out = self.m.parse_hf_evidence("<html>", "", dict(expected_repo_id=REPO))
        self.assertFalse(out["anchor_match"])

    def test_parse_sha_needs_single_file(self):
        data = json.loads(api_json())
        data["siblings"].append({"rfilename": "model-2.safetensors", "size": 10, "lfs": {"sha256": "cd" * 32}})
        anchors = dict(expected_repo_id=REPO, delivered_revision=REV, expected_weights_prefix="model",
                       expected_min_total_size_bytes=1, expected_base_model=BASE, required_license=LICENSE,
                       expected_sha256=SHA)
        self.assertFalse(self.m.parse_hf_evidence(json.dumps(data), README, anchors)["anchor_match"])

    # ---------------- jurors ----------------
    def test_register_and_validation(self):
        val = self.m.JUROR_BOND_AMOUNT + self.m.JUROR_REGISTRATION_FEE
        self.assertEqual(self.tx("register_as_juror", JURORS[0], value=GEN), "ERR_VALUE_MISMATCH")
        self.assertEqual(self.withdrawable(JURORS[0]), GEN)
        self.assertEqual(self.tx("register_as_juror", JURORS[0], value=val), "OK")
        self.assertEqual(self.tx("register_as_juror", JURORS[0], value=val), "ERR_ALREADY_REGISTERED")
        self.assertEqual(self.acct()["treasury_balance"], str(self.m.JUROR_REGISTRATION_FEE))
        self.assertBalanced()

    def test_deregister_and_reactivate_with_fresh_timestamp(self):
        self.register_jurors(1)
        old = self.j("get_juror", addr=JURORS[0].as_hex)["registered_at"]
        self.assertEqual(self.tx("deregister_juror", JURORS[0]), "OK")
        self.assertEqual(self.withdrawable(JURORS[0]), self.m.JUROR_BOND_AMOUNT)
        self.assertEqual(self.tx("deregister_juror", JURORS[0]), "ERR_NO_BOND")
        Clock.advance(100)
        self.assertEqual(self.tx("top_up_juror_bond", JURORS[0], value=self.m.JUROR_BOND_AMOUNT), "OK")
        info = self.j("get_juror", addr=JURORS[0].as_hex)
        self.assertTrue(info["is_active"])
        self.assertGreater(info["registered_at"], old)
        self.assertBalanced()

    def test_top_up_errors(self):
        self.assertEqual(self.tx("top_up_juror_bond", STRANGER, value=GEN), "ERR_NOT_REGISTERED")
        self.register_jurors(1)
        self.assertEqual(self.tx("top_up_juror_bond", JURORS[0], value=GEN), "ERR_BOND_FULL")
        self.assertBalanced()

    # ---------------- escalation / jury ----------------
    def test_escalate_guards(self):
        did = self.to_tier1("NOT_DELIVERED")
        bond = self.m.MIN_APPEAL_BOND
        self.assertEqual(self.tx("escalate_to_jury", TRAINER, value=bond, deal_id=did), "ERR_JURY_POOL_TOO_SMALL")
        self.register_jurors(9)
        self.assertEqual(self.tx("escalate_to_jury", STRANGER, value=bond, deal_id=did), "ERR_NOT_PARTY")
        self.assertEqual(self.tx("escalate_to_jury", TRAINER, value=bond - 1, deal_id=did), "ERR_VALUE_MISMATCH")
        Clock.advance(self.m.CHALLENGE_WINDOW_SEC + 1)
        self.assertEqual(self.tx("escalate_to_jury", TRAINER, value=bond, deal_id=did), "ERR_WINDOW_CLOSED")
        self.assertBalanced()

    def test_late_registered_jurors_not_eligible(self):
        did = self.to_tier1("NOT_DELIVERED")
        self.register_jurors(9)
        self.assertEqual(self.tx("escalate_to_jury", TRAINER, value=self.m.MIN_APPEAL_BOND, deal_id=did), "ERR_JURY_POOL_TOO_SMALL")

    def test_jury_overturns_tier1(self):
        self.register_jurors(9)
        did = self.to_tier1("NOT_DELIVERED")
        self.assertEqual(self.appeal(did), "OK")
        self.assertEqual(self.deal(did)["status"], "DISPUTED")
        n = self.m.ROUND1_JURY_SIZE
        sel = self.run_round(did, 1, ["DELIVERED"] * n)
        d = self.deal(did)
        self.assertEqual(d["status"], "FINALIZED")
        self.assertEqual(d["verdict"], "DELIVERED")
        self.assertEqual(self.withdrawable(TRAINER), 10 * GEN - GEN // 10)
        share = self.m.MIN_APPEAL_BOND // n
        for a in sel:
            self.assertEqual(self.withdrawable(a), share)
            self.assertEqual(self.j("get_juror", addr=a.as_hex)["active_case_count"], 0)
        self.assertBalanced()

    def test_jury_upholds_tier1_and_bond_goes_to_winners(self):
        self.register_jurors(9)
        did = self.to_tier1("NOT_DELIVERED")
        self.appeal(did)
        self.run_round(did, 1, ["NOT_DELIVERED"] * self.m.ROUND1_JURY_SIZE)
        self.assertEqual(self.deal(did)["status"], "REFUNDED")
        self.assertEqual(self.withdrawable(BUYER), 10 * GEN)
        self.assertBalanced()

    def test_commit_reveal_guards(self):
        if self.m.ROUND1_JURY_SIZE < 3:
            self.skipTest("needs a 3-juror round")
        self.register_jurors(9)
        did = self.to_tier1("NOT_DELIVERED")
        self.appeal(did)
        sel = self.selected(did, 1)
        outsider = [a for a in JURORS if a not in sel][0]
        h = self.commit_hash("DELIVERED", "s", sel[0])
        self.assertEqual(self.tx("commit_jury_vote", outsider, deal_id=did, commit_hash=h), "ERR_NOT_SELECTED")
        self.assertEqual(self.tx("commit_jury_vote", sel[0], deal_id=did, commit_hash="zz"), "ERR_BAD_COMMIT")
        self.assertEqual(self.tx("commit_jury_vote", sel[0], deal_id=did, commit_hash=h), "OK")
        self.assertEqual(self.tx("commit_jury_vote", sel[0], deal_id=did, commit_hash=h), "ERR_ALREADY_COMMITTED")
        self.assertEqual(self.tx("reveal_jury_vote", sel[0], deal_id=did, vote="DELIVERED", salt="s"), "ERR_WRONG_PHASE")
        for a in sel[1:]:
            self.tx("commit_jury_vote", a, deal_id=did, commit_hash=self.commit_hash("DELIVERED", "s", a))
        self.assertEqual(self.tx("reveal_jury_vote", sel[0], deal_id=did, vote="NOT_DELIVERED", salt="s"), "ERR_COMMIT_MISMATCH")
        self.assertEqual(self.tx("reveal_jury_vote", sel[0], deal_id=did, vote="MAYBE", salt="s"), "ERR_BAD_VOTE")
        self.assertEqual(self.tx("reveal_jury_vote", sel[0], deal_id=did, vote="DELIVERED", salt="s"), "OK")
        self.assertEqual(self.tx("reveal_jury_vote", sel[0], deal_id=did, vote="DELIVERED", salt="s"), "ERR_ALREADY_REVEALED")

    def test_no_reveal_is_slashed_and_deadlock_resolved(self):
        if self.m.ROUND1_JURY_SIZE < 3:
            self.skipTest("needs a 3-juror round")
        self.register_jurors(9)
        did = self.to_tier1("NOT_DELIVERED")
        self.appeal(did)
        sel = self.run_round(did, 1, ["DELIVERED", "DELIVERED", None])
        self.assertEqual(self.tx("resolve_jury_deadlock", STRANGER, deal_id=did), "ERR_NOT_EXPIRED")
        Clock.advance(self.m.JURY_COMMIT_WINDOW_SEC + 1)
        self.assertEqual(self.tx("resolve_jury_deadlock", STRANGER, deal_id=did), "OK:REVEAL")
        for a in sel[:2]:
            self.assertEqual(self.tx("reveal_jury_vote", a, deal_id=did, vote="DELIVERED", salt="s"), "OK")
        self.assertEqual(self.deal(did)["status"], "FINALIZED")
        slashed = self.j("get_juror", addr=sel[2].as_hex)
        self.assertEqual(slashed["staked_bond"], str(self.m.JUROR_BOND_AMOUNT - self.m.JUROR_SLASH_AMOUNT))
        self.assertFalse(slashed["is_active"])
        self.assertEqual(slashed["active_case_count"], 0)
        self.assertBalanced()

    def test_split_vote_escalates_then_fallback_to_tier1(self):
        if self.m.ROUND1_JURY_SIZE < 3:
            self.skipTest("needs a 3-juror round")
        self.register_jurors(9)
        did = self.to_tier1("NOT_DELIVERED")
        self.appeal(did)
        self.run_round(did, 1, ["DELIVERED", "PARTIALLY_DELIVERED", "NOT_DELIVERED"])
        d = self.deal(did)
        self.assertEqual(d["current_round"], 2)
        self.assertEqual(d["status"], "DISPUTED")
        r1 = set(a.as_hex for a in self.selected(did, 1))
        r2 = set(a.as_hex for a in self.selected(did, 2))
        self.assertEqual(len(r2), self.m.ROUND2_JURY_SIZE)
        self.assertFalse(r1 & r2)
        self.run_round(did, 2, ["DELIVERED", "DELIVERED", "PARTIALLY_DELIVERED", "PARTIALLY_DELIVERED", "NOT_DELIVERED"])
        d = self.deal(did)
        self.assertEqual(d["status"], "REFUNDED")
        self.assertEqual(self.acct()["treasury_balance"], str(self.m.JUROR_REGISTRATION_FEE * 9 + self.m.MIN_APPEAL_BOND))
        self.assertBalanced()

    def test_split_then_majority_in_round_two(self):
        if self.m.ROUND1_JURY_SIZE < 3:
            self.skipTest("needs a 3-juror round")
        self.register_jurors(9)
        did = self.to_tier1("NOT_DELIVERED")
        self.appeal(did, BUYER)
        self.run_round(did, 1, ["DELIVERED", "PARTIALLY_DELIVERED", "NOT_DELIVERED"])
        self.run_round(did, 2, ["PARTIALLY_DELIVERED"] * 3 + ["DELIVERED", "NOT_DELIVERED"])
        self.assertEqual(self.deal(did)["verdict"], "PARTIALLY_DELIVERED")
        self.assertBalanced()

    def test_total_no_show_falls_back(self):
        self.register_jurors(9)
        did = self.to_tier1("NOT_DELIVERED")
        self.appeal(did)
        for _ in range(2):
            Clock.advance(self.m.JURY_COMMIT_WINDOW_SEC + 1)
            self.tx("resolve_jury_deadlock", STRANGER, deal_id=did)
            if self.deal(did)["status"] != "DISPUTED":
                break
        self.assertIn(self.deal(did)["status"], ["REFUNDED", "DISPUTED"])
        if self.deal(did)["status"] == "DISPUTED":
            Clock.advance(self.m.JURY_COMMIT_WINDOW_SEC + 1)
            self.tx("resolve_jury_deadlock", STRANGER, deal_id=did)
        self.assertEqual(self.deal(did)["status"], "REFUNDED")
        self.assertBalanced()

    def test_recover_stuck_disputed_refunds_appeal_bond(self):
        self.register_jurors(9)
        did = self.to_tier1("NOT_DELIVERED")
        self.appeal(did, TRAINER)
        self.assertEqual(self.tx("recover_stuck_deal", STRANGER, deal_id=did), "ERR_NOT_STUCK")
        Clock.advance(self.m.STUCK_TIMEOUT_SEC + 1)
        self.assertEqual(self.tx("recover_stuck_deal", STRANGER, deal_id=did), "OK")
        self.assertEqual(self.withdrawable(TRAINER), self.m.MIN_APPEAL_BOND)
        self.assertEqual(self.withdrawable(BUYER), 10 * GEN)
        for a in JURORS[:9]:
            self.assertEqual(self.j("get_juror", addr=a.as_hex)["active_case_count"], 0)
        self.assertBalanced()

    def test_recover_created_deal_cancels(self):
        did = self.make_deal(fund=False)
        Clock.advance(self.m.STUCK_TIMEOUT_SEC + 1)
        self.assertEqual(self.tx("recover_stuck_deal", STRANGER, deal_id=did), "OK")
        self.assertEqual(self.deal(did)["status"], "CANCELLED")

    def test_recover_terminal_rejected(self):
        did = self.make_deal(fund=False)
        self.tx("cancel_unfunded", BUYER, deal_id=did)
        Clock.advance(self.m.STUCK_TIMEOUT_SEC + 1)
        self.assertEqual(self.tx("recover_stuck_deal", STRANGER, deal_id=did), "ERR_INVALID_STATUS")

    # ---------------- withdrawals ----------------
    def test_withdraw_transfers_and_zeroes(self):
        did = self.to_tier1("NOT_DELIVERED")
        Clock.advance(self.m.CHALLENGE_WINDOW_SEC + 1)
        self.tx("finalize_unappealed", STRANGER, deal_id=did)
        self.assertEqual(self.tx("withdraw", STRANGER), "ERR_NOTHING_TO_WITHDRAW")
        self.assertEqual(self.tx("withdraw", BUYER), "OK:" + str(10 * GEN))
        self.assertEqual(self.c._transfers, [(BUYER.as_hex, 10 * GEN)])
        self.assertEqual(self.tx("withdraw", BUYER), "ERR_NOTHING_TO_WITHDRAW")
        self.assertEqual(self.acct()["contract_balance"], "0")
        self.assertBalanced()

    def test_treasury_withdraw_owner_only(self):
        did = self.to_tier1("DELIVERED")
        Clock.advance(self.m.CHALLENGE_WINDOW_SEC + 1)
        self.tx("finalize_unappealed", STRANGER, deal_id=did)
        self.assertEqual(self.tx("withdraw_treasury", STRANGER), "ERR_NOT_OWNER")
        self.assertEqual(self.tx("withdraw_treasury", OWNER), "OK:" + str(GEN // 10))
        self.assertBalanced()

    def test_full_lifecycle_drains_contract(self):
        self.register_jurors(9)
        did = self.to_tier1("NOT_DELIVERED")
        self.appeal(did)
        sel = self.run_round(did, 1, ["DELIVERED"] * self.m.ROUND1_JURY_SIZE)
        for who in [TRAINER, BUYER, OWNER] + sel:
            self.tx("withdraw", who)
        self.tx("withdraw_treasury", OWNER)
        for a in JURORS[:9]:
            self.tx("withdraw", a)
            self.tx("deregister_juror", a)
            self.tx("withdraw", a)
        self.assertEqual(self.acct()["contract_balance"], "0")
        self.assertBalanced()

    # ---------------- regressions / environment ----------------
    def test_stub_treemap_has_no_set_or_contains(self):
        self.assertFalse(hasattr(stub.TreeMap(), "set"))
        self.assertFalse(hasattr(stub.TreeMap(), "contains"))

    def test_assigning_dict_to_treemap_is_caught(self):
        class Bad(gl.Contract):
            m: stub.TreeMap[str, u256]

            def __init__(self):
                self.m = {}

        with self.assertRaises(TypeError):
            Bad()

    def test_storage_cannot_be_touched_inside_nondet(self):
        with self.assertRaises(RuntimeError):
            gl.vm.run_nondet_unsafe(lambda: self.c.deals.get(u256(1)), lambda r: True)

    def test_views_return_json(self):
        self.assertIn("platform_fee_bps", self.j("get_config"))
        self.assertEqual(self.j("get_deal", deal_id=99), {})
        self.assertEqual(self.j("list_jurors"), [])
        self.assertEqual(self.tx("get_withdrawable", STRANGER, addr="bad"), "0")


class DocumentedTests(Base, unittest.TestCase):
    FILE = "tunepact.py"


class DeployTests(Base, unittest.TestCase):
    FILE = "tunepact_deploy.py"


class TestnetTests(Base, unittest.TestCase):
    FILE = "tunepact_testnet.py"


class FormatTests(unittest.TestCase):
    ROOT = Path(__file__).resolve().parent.parent / "contracts"

    def test_deploy_has_headers_and_no_comments(self):
        text = (self.ROOT / "tunepact_deploy.py").read_text().splitlines()
        self.assertEqual(text[0], "# v0.2.16")
        self.assertTrue(text[1].startswith('# { "Depends": "py-genlayer:'))
        self.assertFalse([l for l in text[2:] if l.strip().startswith("#")])
        self.assertNotIn('"""', "\n".join(text))

    def test_deploy_is_in_sync_with_documented(self):
        sys.path.insert(0, str(self.ROOT.parent / "tools"))
        import build_deploy
        src = (self.ROOT / "tunepact.py").read_text()
        self.assertEqual(build_deploy.strip_source(src), (self.ROOT / "tunepact_deploy.py").read_text())
        self.assertEqual(build_deploy.strip_source(build_deploy.apply_testnet(src)), (self.ROOT / "tunepact_testnet.py").read_text())

    def test_testnet_differs_only_in_tunable_constants(self):
        a = (self.ROOT / "tunepact_deploy.py").read_text().splitlines()
        b = (self.ROOT / "tunepact_testnet.py").read_text().splitlines()
        self.assertEqual(len(a), len(b))
        diff = [x for x, y in zip(a, b) if x != y]
        self.assertEqual(len(diff), 7)
        for line in diff:
            self.assertRegex(line, r"^[A-Z0-9_]+: int = ")

    def test_no_invalid_treemap_api_in_sources(self):
        for name in ["tunepact.py", "tunepact_deploy.py"]:
            text = (self.ROOT / name).read_text()
            self.assertIsNone(re.search(r"\.(set|contains)\(", text), name)
            self.assertNotIn("gl.get_contract_at", text)


if __name__ == "__main__":
    unittest.main()
