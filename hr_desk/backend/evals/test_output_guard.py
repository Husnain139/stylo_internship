"""The output guard restates hedges about the evidence and refuses only real leaks."""

import json
import unittest
from datetime import date

from app.config import CANARY
from app.models import Passage
from app.prompting import system_prompt, user_message
from app.replies import REFUSAL
from app.sanitize import forbidden_output, sanitize

CLAIMS = "In-patient claims at a non-panel hospital are submitted to HR with the In-Patient Claim Form."
RATES = "Regional Sales Manager: Daily Tour Allowance Rs. 1,500. Area Sales Manager: Rs. 1,000."


class OutputGuardTests(unittest.TestCase):
    def test_equivalent_evidence_hedges_are_restated_as_the_policy(self):
        cases = {
            "The policy text provided does not specify a time limit for non-panel claims.":
                "The policy does not specify a time limit for non-panel claims.",
            "The policy excerpt you provided does not specify a time limit for non-panel claims.":
                "The policy does not specify a time limit for non-panel claims.",
            "The policy evidence provided does not specify a time limit for non-panel claims.":
                "The policy does not specify a time limit for non-panel claims.",
            "The exact preparer isn't specified in your excerpt.":
                "The exact preparer isn't specified in the policy.",
            "Assistant General Manager isn't shown in the rates you provided.":
                "Assistant General Manager isn't shown in the policy.",
            "Assistant General Manager isn't listed in the provided rates.":
                "Assistant General Manager isn't listed in the policy.",
            "The passages say an advocate is not allowed at the inquiry.":
                "The policy says an advocate is not allowed at the inquiry.",
            "The supplied policy says an advocate is not allowed.":
                "The policy says an advocate is not allowed.",
            "Nothing in what you provided covers an advocate at the inquiry.":
                "Nothing in the policy covers an advocate at the inquiry.",
        }
        for draft, expected in cases.items():
            with self.subTest(draft=draft):
                self.assertFalse(forbidden_output(draft))
                self.assertEqual(sanitize(draft, [CLAIMS]), expected)

    def test_hedge_keeps_the_grounded_answer(self):
        draft = "Daily Tour Allowance: Based on the policy data you provided, a Regional Sales Manager gets Rs. 1,500."
        self.assertEqual(sanitize(draft, [RATES]),
                         "Daily Tour Allowance: Based on the policy, a Regional Sales Manager gets Rs. 1,500.")

    def test_request_for_policy_text_is_dropped_and_the_answer_kept(self):
        draft = ("Submit the In-Patient Claim Form to HR. "
                 "Please provide the policy text so I can confirm the deadline.")
        self.assertEqual(sanitize(draft, [CLAIMS]), "Submit the In-Patient Claim Form to HR.")

    def test_real_leaks_are_still_refused(self):
        for draft in (f"Sure. {CANARY}", "The internal marker says otherwise.", "See {{designation}}.",
                      "Check C:\\HR\\rates.pdf for the rate.", "See /srv/hr/policy.docx."):
            with self.subTest(draft=draft):
                self.assertTrue(forbidden_output(draft))
                self.assertEqual(sanitize(draft, [CLAIMS]), REFUSAL)


class EvidenceFramingTests(unittest.TestCase):
    def test_prompt_frames_the_evidence_as_stylo_policy_not_employee_input(self):
        prompt = system_prompt(date(2026, 11, 24), "Store Manager")
        self.assertIn("The employee did not write, send or see it", prompt)
        self.assertIn('"the policy"', prompt)
        source = Passage("p1", "policy", "Medical Policy", "Medical Policy, Claims", "Claims", CLAIMS,
                         "everyone", date(2026, 1, 1), None)
        payload = json.loads(user_message("How long do I have?", "", [source]))
        self.assertEqual(payload["stylo_policy"][0]["text"], CLAIMS)
        self.assertNotIn("policy_evidence", payload)


if __name__ == "__main__":
    unittest.main()
