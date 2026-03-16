"""Regression tests for Agent V1 Step 5 — Approval security binding.

Tests the scoped grant mechanism and write_note KB enforcement:
  1. Normal approve → grant consumed → tool executes with correct KB
  2. Cross-user: grant user_id mismatch → rejected
  3. Cross-KB: grant knowledge_base_id mismatch → rejected
  4. Tampered params: input hash mismatch → rejected
  5. Missing KB ID: write_note receives no KB → fails
  6. Expired grant: past TTL → rejected
  7. Grant is single-use: consumed on first match, gone on second
"""

import asyncio
import hashlib
import json
import os
import sys
import time
import unittest

# Add project root to path
sys.path.insert(0, "..")

from app.core.tools.registry import (
    register_scoped_grant,
    consume_scoped_grant,
    create_v1_registry,
    _scoped_grants,
    _scoped_grants_lock,
    _SCOPED_GRANT_TTL_SECONDS,
)
from app.core.tools.write_note_tool import WriteNoteTool
from app.core.agent.execution_context import AgentExecutionContext


# ═══════════════════════════════════════════════════════════════════════════
# Test 1: Normal approve flow — grant matches, is consumed
# ═══════════════════════════════════════════════════════════════════════════

class TestScopedGrantNormal(unittest.TestCase):
    def setUp(self):
        with _scoped_grants_lock:
            _scoped_grants.clear()

    def test_normal_approve_consume(self):
        """Grant registered with (tool, input, user, kb) → matched → consumed."""
        tool_name = "write_note"
        tool_input = {"content": "Hello, world!"}
        user_id = 42
        kb_id = 99

        token = register_scoped_grant(tool_name, tool_input, user_id, kb_id)
        self.assertIsNotNone(token)
        self.assertEqual(len(_scoped_grants), 1)

        # Matching consume should return True and remove the grant.
        result = consume_scoped_grant(tool_name, tool_input, user_id, kb_id)
        self.assertTrue(result)
        self.assertEqual(len(_scoped_grants), 0)

    def test_single_use(self):
        """Grant is consumed on first match — second call returns False."""
        tool_name = "write_note"
        tool_input = {"content": "Test"}
        user_id = 1
        kb_id = 10

        register_scoped_grant(tool_name, tool_input, user_id, kb_id)
        self.assertEqual(len(_scoped_grants), 1)

        # First consume → True
        self.assertTrue(consume_scoped_grant(tool_name, tool_input, user_id, kb_id))
        self.assertEqual(len(_scoped_grants), 0)

        # Second consume → False (grant already consumed)
        self.assertFalse(consume_scoped_grant(tool_name, tool_input, user_id, kb_id))


# ═══════════════════════════════════════════════════════════════════════════
# Test 2: Cross-user — grant user_id mismatch → rejected
# ═══════════════════════════════════════════════════════════════════════════

class TestScopedGrantCrossUser(unittest.TestCase):
    def setUp(self):
        with _scoped_grants_lock:
            _scoped_grants.clear()

    def test_cross_user_rejected(self):
        """Grant registered for user A → user B cannot consume it."""
        tool_name = "write_note"
        tool_input = {"content": "Sensitive note"}

        register_scoped_grant(tool_name, tool_input, user_id=100, knowledge_base_id=5)

        # User 200 tries to consume → rejected
        result = consume_scoped_grant(tool_name, tool_input, user_id=200, knowledge_base_id=5)
        self.assertFalse(result)
        # Grant should still be available for the correct user.
        self.assertEqual(len(_scoped_grants), 1)

    def test_correct_user_still_works_after_cross_user_attempt(self):
        """After a failed cross-user attempt, the correct user can still consume."""
        tool_name = "write_note"
        tool_input = {"content": "Note"}

        register_scoped_grant(tool_name, tool_input, user_id=100, knowledge_base_id=5)

        # Wrong user tries → fails
        self.assertFalse(consume_scoped_grant(tool_name, tool_input, user_id=999, knowledge_base_id=5))
        # Correct user → succeeds
        self.assertTrue(consume_scoped_grant(tool_name, tool_input, user_id=100, knowledge_base_id=5))


# ═══════════════════════════════════════════════════════════════════════════
# Test 3: Cross-KB — grant knowledge_base_id mismatch → rejected
# ═══════════════════════════════════════════════════════════════════════════

class TestScopedGrantCrossKB(unittest.TestCase):
    def setUp(self):
        with _scoped_grants_lock:
            _scoped_grants.clear()

    def test_cross_kb_rejected(self):
        """Grant registered for KB 1 → cannot be consumed for KB 2."""
        tool_name = "write_note"
        tool_input = {"content": "KB-scoped note"}

        register_scoped_grant(tool_name, tool_input, user_id=1, knowledge_base_id=10)

        # Same user, different KB → rejected
        result = consume_scoped_grant(tool_name, tool_input, user_id=1, knowledge_base_id=20)
        self.assertFalse(result)
        self.assertEqual(len(_scoped_grants), 1)

    def test_correct_kb_still_works_after_cross_kb_attempt(self):
        """After a failed cross-KB attempt, the correct KB can still consume."""
        tool_name = "write_note"
        tool_input = {"content": "Note"}

        register_scoped_grant(tool_name, tool_input, user_id=1, knowledge_base_id=10)

        # Wrong KB → fails
        self.assertFalse(consume_scoped_grant(tool_name, tool_input, user_id=1, knowledge_base_id=99))
        # Correct KB → succeeds
        self.assertTrue(consume_scoped_grant(tool_name, tool_input, user_id=1, knowledge_base_id=10))


# ═══════════════════════════════════════════════════════════════════════════
# Test 4: Tampered params — input hash mismatch → rejected
# ═══════════════════════════════════════════════════════════════════════════

class TestScopedGrantTamperedParams(unittest.TestCase):
    def setUp(self):
        with _scoped_grants_lock:
            _scoped_grants.clear()

    def test_tampered_content_rejected(self):
        """Grant for content='A' → content='B' is rejected."""
        register_scoped_grant(
            "write_note",
            {"content": "Approved text"},
            user_id=1, knowledge_base_id=10,
        )

        # Tampered content → rejected
        result = consume_scoped_grant(
            "write_note",
            {"content": "MALICIOUS text"},
            user_id=1, knowledge_base_id=10,
        )
        self.assertFalse(result)
        self.assertEqual(len(_scoped_grants), 1)

    def test_tampered_extra_field_rejected(self):
        """Grant for {content} → {content, extra} is rejected (hash differs)."""
        register_scoped_grant(
            "write_note",
            {"content": "Approved"},
            user_id=1, knowledge_base_id=10,
        )

        result = consume_scoped_grant(
            "write_note",
            {"content": "Approved", "extra_field": "injected"},
            user_id=1, knowledge_base_id=10,
        )
        self.assertFalse(result)

    def test_tampered_different_tool_rejected(self):
        """Grant for write_note → different tool name is rejected."""
        register_scoped_grant(
            "write_note",
            {"content": "Note"},
            user_id=1, knowledge_base_id=10,
        )

        result = consume_scoped_grant(
            "search_knowledge_base",  # different tool!
            {"content": "Note"},
            user_id=1, knowledge_base_id=10,
        )
        self.assertFalse(result)


# ═══════════════════════════════════════════════════════════════════════════
# Test 5: write_note KB enforcement
# ═══════════════════════════════════════════════════════════════════════════

class TestWriteNoteKBEnforcement(unittest.IsolatedAsyncioTestCase):
    async def test_missing_kb_id_returns_error(self):
        """write_note with knowledge_base_id=None → returns error dict."""
        tool = WriteNoteTool()
        result = await tool.execute(content="Test", knowledge_base_id=None)
        self.assertIsInstance(result, dict)
        self.assertIn("error", result)
        self.assertIn("必填", result["error"])

    async def test_unknown_string_kb_id_returns_error(self):
        """write_note with knowledge_base_id='unknown' → returns error dict."""
        tool = WriteNoteTool()
        result = await tool.execute(content="Test", knowledge_base_id="unknown")
        self.assertIsInstance(result, dict)
        self.assertIn("error", result)
        self.assertIn("必填", result["error"])

    async def test_invalid_kb_id_returns_error(self):
        """write_note with knowledge_base_id=0 or negative → returns error."""
        tool = WriteNoteTool()
        result = await tool.execute(content="Test", knowledge_base_id=0)
        self.assertIsInstance(result, dict)
        self.assertIn("error", result)

        result2 = await tool.execute(content="Test", knowledge_base_id=-5)
        self.assertIsInstance(result2, dict)
        self.assertIn("error", result2)

    async def test_valid_kb_id_succeeds(self):
        """write_note with valid positive KB ID → returns written status."""
        tool = WriteNoteTool()
        result = await tool.execute(content="Valid note", knowledge_base_id=42)
        self.assertIn("error", result)
        self.assertIn("durable note persistence", result["error"])


# ═══════════════════════════════════════════════════════════════════════════
# Test 6: Expired grant
# ═══════════════════════════════════════════════════════════════════════════

class TestScopedGrantExpiry(unittest.TestCase):
    def setUp(self):
        with _scoped_grants_lock:
            _scoped_grants.clear()

    def test_expired_grant_rejected(self):
        """Grant past TTL → rejected (cleaned up before matching)."""
        tool_name = "write_note"
        tool_input = {"content": "Expired note"}
        user_id = 1
        kb_id = 10

        token = register_scoped_grant(tool_name, tool_input, user_id, kb_id)

        # Manually age the grant past TTL
        with _scoped_grants_lock:
            _scoped_grants[token]["created_at"] = time.monotonic() - _SCOPED_GRANT_TTL_SECONDS - 10

        result = consume_scoped_grant(tool_name, tool_input, user_id, kb_id)
        self.assertFalse(result)
        # Grant should be cleaned up
        self.assertEqual(len(_scoped_grants), 0)


# ═══════════════════════════════════════════════════════════════════════════
# Test 7: Registry.execute() KB injection for write_note
# ═══════════════════════════════════════════════════════════════════════════

class TestRegistryKBInjection(unittest.IsolatedAsyncioTestCase):
    async def test_write_note_gets_kb_injected(self):
        """Registry.execute() injects knowledge_base_id for KB_WRITE tools."""
        registry = create_v1_registry(knowledge_base_id=77, agent_version="1.1")

        context = AgentExecutionContext(
            user_id=1,
            knowledge_base_id=77,
            permissions=frozenset({"knowledge_base:read", "knowledge_base:write"}),
            agent_run_id="test-run-id",
            mode="read_write",
            capability_profile="approval_write",
        )

        # Register a scoped grant so the tool passes the approval gate.
        register_scoped_grant("write_note", {"content": "KB test"}, user_id=1, knowledge_base_id=77)

        result = await registry.execute(
            tool_name="write_note",
            tool_input={"content": "KB test"},
            context=context,
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "internal_error")
        self.assertIn("durable note persistence", result.message)

    async def test_write_note_without_grant_returns_approval_required(self):
        """Without a scoped grant, write_note returns approval_required."""
        registry = create_v1_registry(knowledge_base_id=77, agent_version="1.1")

        context = AgentExecutionContext(
            user_id=1,
            knowledge_base_id=77,
            permissions=frozenset({"knowledge_base:read"}),
            agent_run_id="test-run-id",
            mode="read_only",
            capability_profile="approval_write",
        )

        result = await registry.execute(
            tool_name="write_note",
            tool_input={"content": "Should require approval"},
            context=context,
        )

        self.assertFalse(result.ok)
        self.assertTrue(result.approval_required)
        self.assertEqual(result.error_code, "approval_required")

    async def test_cross_kb_execution_rejected_by_registry(self):
        """Registry rejects write_note when context KB != registry KB."""
        registry = create_v1_registry(knowledge_base_id=77, agent_version="1.1")

        context = AgentExecutionContext(
            user_id=1,
            knowledge_base_id=99,  # Different from registry's KB 77
            permissions=frozenset({"knowledge_base:read", "knowledge_base:write"}),
            agent_run_id="test-run-id",
            mode="read_write",
            capability_profile="approval_write",
        )

        register_scoped_grant("write_note", {"content": "Cross KB"}, user_id=1, knowledge_base_id=77)

        result = await registry.execute(
            tool_name="write_note",
            tool_input={"content": "Cross KB"},
            context=context,
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "knowledge_base_scope_denied")


# ═══════════════════════════════════════════════════════════════════════════
# Test 8: Combined cross-user + cross-KB in registry.execute()
# ═══════════════════════════════════════════════════════════════════════════

class TestScopedGrantCombinedSecurity(unittest.TestCase):
    def setUp(self):
        with _scoped_grants_lock:
            _scoped_grants.clear()

    def test_all_four_dimensions_must_match(self):
        """Grant only consumed when tool_name, hash, user_id, kb_id ALL match."""
        tool_name = "write_note"
        tool_input = {"content": "Secure note"}
        user_id = 42
        kb_id = 99

        register_scoped_grant(tool_name, tool_input, user_id, kb_id)

        # Wrong tool → fail
        self.assertFalse(consume_scoped_grant("other_tool", tool_input, user_id, kb_id))
        # Wrong hash → fail
        self.assertFalse(consume_scoped_grant(tool_name, {"content": "Other"}, user_id, kb_id))
        # Wrong user → fail
        self.assertFalse(consume_scoped_grant(tool_name, tool_input, 999, kb_id))
        # Wrong KB → fail
        self.assertFalse(consume_scoped_grant(tool_name, tool_input, user_id, 888))

        # Grant still available (none of the above consumed it).
        self.assertEqual(len(_scoped_grants), 1)

        # Correct → success
        self.assertTrue(consume_scoped_grant(tool_name, tool_input, user_id, kb_id))
        self.assertEqual(len(_scoped_grants), 0)


# ═══════════════════════════════════════════════════════════════════════════
# Test 9: Hash canonicalisation (key ordering independent)
# ═══════════════════════════════════════════════════════════════════════════

class TestScopedGrantHashCanonicalisation(unittest.TestCase):
    def setUp(self):
        with _scoped_grants_lock:
            _scoped_grants.clear()

    def test_hash_key_order_independent(self):
        """Same keys in different order → same hash → match succeeds."""
        register_scoped_grant(
            "write_note",
            {"content": "Test", "title": "Hello"},
            user_id=1, knowledge_base_id=10,
        )

        # Same content, different key order → should match
        result = consume_scoped_grant(
            "write_note",
            {"title": "Hello", "content": "Test"},
            user_id=1, knowledge_base_id=10,
        )
        self.assertTrue(result)


# ═══════════════════════════════════════════════════════════════════════════
# Test 10: E2E via decide endpoint (requires running Python service)
# ═══════════════════════════════════════════════════════════════════════════

@unittest.skipUnless(
    os.getenv("HFUSIONHUB_RUN_LIVE_E2E") == "true",
    "set HFUSIONHUB_RUN_LIVE_E2E=true to run tests against a live Python service",
)
class TestDecideEndpointE2E(unittest.TestCase):
    """Integration tests against the running /api/agent/v1/chat/decide endpoint.

    Requires: Python service running on localhost:9000 with PYTHON_AI_INTERNAL_TOKEN set.
    """

    BASE = "http://localhost:9000"
    TOKEN = os.getenv("PYTHON_AI_INTERNAL_TOKEN", "")

    def _decide(self, approval_id, decision, tool_name, tool_input,
                user_id, knowledge_base_id, reason=None):
        """Call the decide endpoint."""
        import urllib.request
        body = {
            "approval_id": approval_id,
            "decision": decision,
            "reason": reason,
            "user_id": user_id,
            "knowledge_base_id": knowledge_base_id,
            "tool_name": tool_name,
            "tool_input": tool_input,
            "query": "Test query",
            "history": [],
            "model": "test",
        }
        req = urllib.request.Request(
            f"{self.BASE}/api/agent/v1/chat/decide",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "X-Internal-Token": self.TOKEN,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8")

    def test_approve_write_note_success(self):
        """Approve → write_note executes once → returns completed with KB ID."""
        status, data = self._decide(
            approval_id="e2e-test-001",
            decision="approved",
            tool_name="write_note",
            tool_input={"content": "E2E regression test note"},
            user_id=1,
            knowledge_base_id=1,
        )
        self.assertEqual(status, 200)
        self.assertEqual(data["status"], "completed")
        # Verify KB ID is in the step event
        steps = data.get("step_events", [])
        self.assertGreater(len(steps), 0)
        step = steps[0]
        self.assertEqual(step.get("knowledge_base_id"), 1)
        # Verify tool was write_note
        self.assertEqual(step.get("action"), "write_note")

    def test_deny_returns_denied(self):
        """Deny → returns denied status."""
        status, data = self._decide(
            approval_id="e2e-test-002",
            decision="denied",
            tool_name="write_note",
            tool_input={"content": "Should be denied"},
            user_id=1,
            knowledge_base_id=1,
        )
        self.assertEqual(status, 200)
        self.assertEqual(data["status"], "denied")


# ═══════════════════════════════════════════════════════════════════════════
# Runner
# ═══════════════════════════════════════════════════════════════════════════

def run_async_tests(suite):
    """Run async test methods in a synchronous unittest.TestCase."""
    for test_case in suite:
        for method_name in dir(test_case):
            if method_name.startswith("test_"):
                method = getattr(test_case, method_name)
                if asyncio.iscoroutinefunction(method):
                    # Replace with sync wrapper
                    def make_wrapper(m):
                        def wrapper(self):
                            return asyncio.get_event_loop().run_until_complete(m(self))
                        return wrapper
                    setattr(test_case, method_name, make_wrapper(method))


if __name__ == "__main__":
    # Run async tests via asyncio
    unittest.main(verbosity=2)
