"""
Mocked tests for the search budget, per-visitor limit, daily cap and own-key box.
No network and no paid API calls: the Anthropic client and the search pipeline
are replaced with fakes. Run with:  python -m unittest test_limits -v
"""

import contextlib
import io
import os
import types
import unittest
from unittest import mock

os.environ["ANTHROPIC_API_KEY"] = "sk-ant-shared-test-key-not-real-000000"
# The tests above this file's RequireOwnKey* classes cover the optional free mode,
# which is now off by default; the RequireOwnKey* classes switch it back on per test.
os.environ["REQUIRE_OWN_KEY"] = "false"

import llm_budget
import usage_limits
from usage_limits import DailyCounter, check_and_consume, SESSION_COUNT_KEY

OWN_KEY = "sk-ant-visitor-secret-key-ABCDEFGHIJKLMNOP"


def fake_response(text="[]"):
    return types.SimpleNamespace(
        content=[types.SimpleNamespace(type="text", text=text)],
        usage=types.SimpleNamespace(input_tokens=10, output_tokens=5),
    )


class FakeAnthropic:
    """Stands in for anthropic.Anthropic; records the key each client was made with."""
    instances = []

    def __init__(self, api_key=None, max_retries=None):
        self.api_key = api_key
        self.max_retries = max_retries
        self.calls = []
        self.messages = self
        FakeAnthropic.instances.append(self)

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return fake_response()


class EnvMixin:
    def setUp(self):
        self._env = mock.patch.dict(os.environ, {"SESSION_SEARCH_LIMIT": "5", "DAILY_SEARCH_LIMIT": "100"})
        self._env.start()

    def tearDown(self):
        self._env.stop()


class PerVisitorLimitTests(EnvMixin, unittest.TestCase):
    def test_five_searches_then_blocked(self):
        state, counter = {}, DailyCounter()
        results = [check_and_consume(state, "", counter)[0] for _ in range(6)]
        self.assertEqual(results, [True] * 5 + [False])
        self.assertEqual(state[SESSION_COUNT_KEY], 5)

    def test_blocked_session_search_does_not_use_daily_quota(self):
        state, counter = {SESSION_COUNT_KEY: 5}, DailyCounter()
        allowed, msg = check_and_consume(state, "", counter)
        self.assertFalse(allowed)
        self.assertIn("5 free searches", msg)
        self.assertEqual(counter.count(), 0)

    def test_sessions_are_independent(self):
        counter = DailyCounter()
        a, b = {}, {}
        for _ in range(5):
            check_and_consume(a, "", counter)
        self.assertTrue(check_and_consume(b, "", counter)[0])


class DailyCapTests(EnvMixin, unittest.TestCase):
    def test_default_is_100(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("DAILY_SEARCH_LIMIT", None)
            self.assertEqual(usage_limits.daily_limit(), 100)

    def test_cap_applies_across_sessions(self):
        os.environ["DAILY_SEARCH_LIMIT"] = "3"
        counter = DailyCounter()
        sessions = [{} for _ in range(4)]
        results = [check_and_consume(s, "", counter)[0] for s in sessions]
        self.assertEqual(results, [True, True, True, False])
        self.assertNotIn(SESSION_COUNT_KEY, sessions[3])  # refused search not charged to visitor

    def test_resets_on_new_utc_day(self):
        os.environ["DAILY_SEARCH_LIMIT"] = "1"
        day = ["2026-11-22"]
        counter = DailyCounter(today_fn=lambda: day[0])
        self.assertTrue(check_and_consume({}, "", counter)[0])
        self.assertFalse(check_and_consume({}, "", counter)[0])
        day[0] = "2026-11-23"
        self.assertTrue(check_and_consume({}, "", counter)[0])

    def test_bad_env_value_falls_back_to_default(self):
        os.environ["DAILY_SEARCH_LIMIT"] = "lots"
        self.assertEqual(usage_limits.daily_limit(), 100)


class OwnKeyTests(EnvMixin, unittest.TestCase):
    def test_own_key_skips_both_caps_and_is_not_counted(self):
        os.environ["DAILY_SEARCH_LIMIT"] = "0"
        state, counter = {SESSION_COUNT_KEY: 5}, DailyCounter()
        for _ in range(10):
            self.assertEqual(check_and_consume(state, OWN_KEY, counter), (True, ""))
        self.assertEqual(state[SESSION_COUNT_KEY], 5)
        self.assertEqual(counter.count(), 0)

    def test_malformed_key_rejected_without_echoing_it(self):
        allowed, msg = check_and_consume({}, "not-a-real-key-12345", DailyCounter())
        self.assertFalse(allowed)
        self.assertNotIn("not-a-real-key-12345", msg)

    def test_redact(self):
        self.assertEqual(usage_limits.redact(f"bad key {OWN_KEY}!", OWN_KEY), "bad key [redacted]!")
        self.assertEqual(usage_limits.redact("text", ""), "text")


class BudgetWithOwnKeyTests(unittest.TestCase):
    def setUp(self):
        FakeAnthropic.instances = []
        self._p = mock.patch.object(llm_budget, "Anthropic", FakeAnthropic)
        self._p.start()
        llm_budget._client = None

    def tearDown(self):
        self._p.stop()
        llm_budget._client = None

    def test_own_key_uses_its_own_client_not_the_shared_one(self):
        b = llm_budget.LLMBudget(api_key=OWN_KEY)
        b.create(model="m", max_tokens=10, messages=[])
        self.assertEqual(len(FakeAnthropic.instances), 1)
        own = FakeAnthropic.instances[0]
        self.assertEqual(own.api_key, OWN_KEY)
        self.assertEqual(own.max_retries, 0)
        self.assertEqual(len(own.calls), 1)
        self.assertIsNone(llm_budget._client)  # shared client never created

    def test_shared_key_search_uses_shared_client(self):
        llm_budget.LLMBudget().create(model="m", max_tokens=10, messages=[])
        self.assertEqual(FakeAnthropic.instances[0].api_key, os.environ["ANTHROPIC_API_KEY"])

    def test_per_search_budget_still_applies_to_own_key(self):
        b = llm_budget.LLMBudget(api_key=OWN_KEY, max_calls=2, max_output_tokens=10**6)
        b.create(model="m", max_tokens=10, messages=[])
        b.create(model="m", max_tokens=10, messages=[])
        with self.assertRaises(llm_budget.BudgetExceeded):
            b.create(model="m", max_tokens=10, messages=[])

    def test_summary_does_not_contain_key(self):
        b = llm_budget.LLMBudget(api_key=OWN_KEY)
        b.create(model="m", max_tokens=10, messages=[])
        self.assertNotIn(OWN_KEY, b.summary())


class PerSearchBudgetTests(unittest.TestCase):
    """Retries and the final-call reserve, using a client that fails on demand."""

    def setUp(self):
        import httpx
        from anthropic import InternalServerError

        class Flaky(FakeAnthropic):
            fails = 0

            def create(self, **kwargs):
                self.calls.append(kwargs)
                if Flaky.fails:
                    Flaky.fails -= 1
                    r = httpx.Response(529, request=httpx.Request("POST", "http://test"))
                    raise InternalServerError("overloaded", response=r, body=None)
                return fake_response()

        self.Flaky = Flaky
        self._p = [mock.patch.object(llm_budget, "Anthropic", Flaky),
                   mock.patch.object(llm_budget.time, "sleep", lambda *_: None)]
        for p in self._p:
            p.start()
        llm_budget._client = None

    def tearDown(self):
        for p in self._p:
            p.stop()
        llm_budget._client = None

    def test_retry_counts_as_a_call(self):
        self.Flaky.fails = 1
        b = llm_budget.LLMBudget(max_calls=5, max_output_tokens=10**6, max_retries=1)
        b.create(model="m", max_tokens=10, messages=[])
        self.assertEqual(b.calls, 2)

    def test_retry_refused_when_budget_spent(self):
        self.Flaky.fails = 5
        b = llm_budget.LLMBudget(max_calls=1, max_output_tokens=10**6, max_retries=3)
        with self.assertRaises(llm_budget.BudgetExceeded):
            b.create(model="m", max_tokens=10, messages=[])
        self.assertEqual(len(llm_budget._client.calls), 1)

    def test_haiku_steps_leave_room_for_final_call(self):
        b = llm_budget.LLMBudget(max_calls=3, max_output_tokens=10**6, max_retries=0)
        for _ in range(5):
            with contextlib.suppress(llm_budget.BudgetExceeded):
                b.create(model="h", max_tokens=10, keep_calls=1, keep_tokens=8000, messages=[])
        self.assertEqual(b.calls, 2)
        b.create(model="s", max_tokens=8000, messages=[])
        self.assertEqual(b.calls, 3)

    def test_sdk_auto_retry_disabled(self):
        self.assertEqual(llm_budget.get_client().max_retries, 0)


class AgentOwnKeyTests(unittest.TestCase):
    def test_key_reaches_client_and_is_never_printed(self):
        import agent
        FakeAnthropic.instances = []
        prof = {"name": "Ada Lovelace", "institution": "Test U", "email": "", "research_description": "x",
                "grant_title": "", "grant_amount": "Unknown", "abstract": "", "recent_papers": []}

        def fake_discover(query, limit, status_callback, budget):
            budget.create(model="claude-haiku-4-5-20251001", max_tokens=50, messages=[])
            return [prof]

        out = io.StringIO()
        with mock.patch.object(llm_budget, "Anthropic", FakeAnthropic), \
             mock.patch.object(agent, "discover_professors", fake_discover), \
             contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            result = agent.run_professor_agent("find robotics professors", api_key=OWN_KEY)

        self.assertEqual(result, "[]")
        self.assertEqual([c.api_key for c in FakeAnthropic.instances], [OWN_KEY])
        self.assertEqual([c["model"] for c in FakeAnthropic.instances[0].calls],
                         ["claude-haiku-4-5-20251001", "claude-sonnet-4-6"])
        self.assertNotIn(OWN_KEY, out.getvalue())


class AppTests(EnvMixin, unittest.TestCase):
    """Runs app.py headless with Streamlit's AppTest; the search pipeline is mocked."""

    def setUp(self):
        super().setUp()
        import agent
        self.agent = agent
        usage_limits.DAILY_COUNTER = DailyCounter()
        self.calls = []

        def fake_run(query, status_callback=None, api_key=None):
            self.calls.append(api_key)
            return "---\n## Prof X\n**Institution:** Test U\n---"

        self._p = mock.patch.object(agent, "run_professor_agent", fake_run)
        self._p.start()

    def tearDown(self):
        self._p.stop()
        super().tearDown()

    def _app(self):
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file("app.py", default_timeout=30)
        at.run()
        return at

    def _search(self, at, q="find robotics professors"):
        at.text_input(key="search_query").set_value(q)
        at.button[0].click()  # "Hunt"
        at.run()

    def _all_text(self, at):
        parts = []
        for kind in ("markdown", "caption", "warning", "error", "success", "info"):
            parts += [str(e.value) for e in getattr(at, kind)]
        return "\n".join(parts)

    def test_sixth_shared_key_search_is_blocked(self):
        at = self._app()
        for _ in range(5):
            self._search(at)
            self.assertFalse(at.exception)
        self.assertEqual(self.calls, [None] * 5)
        self._search(at)
        self.assertEqual(len(self.calls), 5)
        self.assertTrue(any("5 free searches" in w.value for w in at.warning))

    def test_daily_cap_blocks_in_app(self):
        os.environ["DAILY_SEARCH_LIMIT"] = "1"
        self._search(self._app())
        at2 = self._app()  # a second visitor
        self._search(at2)
        self.assertEqual(len(self.calls), 1)
        self.assertTrue(any("daily limit" in w.value for w in at2.warning))

    def _quota_caption(self, at):
        return [c.value for c in at.sidebar.caption if "Free searches left" in c.value]

    def test_sidebar_count_updates_in_the_same_run_as_the_search(self):
        at = self._app()
        self.assertEqual(self._quota_caption(at), ["Free searches left this session: 5"])
        self._search(at)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self._quota_caption(at), ["Free searches left this session: 4"])

    def test_second_search_same_session_and_other_browser_allowed_by_default(self):
        at = self._app()
        self._search(at)
        self._search(at)  # same browser session
        self._search(self._app())  # a different browser, same day
        self.assertEqual(self.calls, [None] * 3)
        self.assertEqual(self._quota_caption(at), ["Free searches left this session: 3"])

    def test_daily_cap_of_one_blocks_second_search_in_same_session(self):
        os.environ["DAILY_SEARCH_LIMIT"] = "1"
        at = self._app()
        self._search(at)
        self._search(at)
        self.assertEqual(len(self.calls), 1)
        self.assertTrue(any("daily limit of 1" in w.value for w in at.warning))
        # the refused search is not charged to the visitor
        self.assertEqual(self._quota_caption(at), ["Free searches left this session: 4"])

    def test_own_key_skips_caps_and_is_never_shown(self):
        os.environ["DAILY_SEARCH_LIMIT"] = "0"
        at = self._app()
        key_box = at.sidebar.text_input[0]
        self.assertEqual(key_box.proto.type, key_box.proto.PASSWORD)
        key_box.set_value(OWN_KEY)
        at.run()
        for _ in range(7):
            self._search(at)
        self.assertEqual(self.calls, [OWN_KEY] * 7)
        self.assertNotIn(OWN_KEY, self._all_text(at))

    def test_errors_are_redacted(self):
        def boom(query, status_callback=None, api_key=None):
            raise RuntimeError(f"auth failed for {api_key}")
        self.agent.run_professor_agent = boom
        at = self._app()
        at.sidebar.text_input[0].set_value(OWN_KEY)
        at.run()
        self._search(at)
        text = self._all_text(at)
        self.assertIn("[redacted]", text)
        self.assertNotIn(OWN_KEY, text)


class SidebarReachableTests(unittest.TestCase):
    """The own-key box lives in the sidebar, so visitors must be able to open it."""

    def setUp(self):
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.py")
        with open(path, encoding="utf-8") as f:
            self.src = f.read()

    def test_sidebar_state_is_auto(self):
        self.assertIn('initial_sidebar_state="auto"', self.src)
        self.assertNotIn('initial_sidebar_state="collapsed"', self.src)
        self.assertNotIn('initial_sidebar_state="expanded"', self.src)

    def test_open_sidebar_button_stays_visible(self):
        self.assertIn('[data-testid="stExpandSidebarButton"] {visibility: visible;}', self.src)


REQUIRED_KEY_MSG = "Add your own Anthropic API key in the sidebar"


class RequireOwnKeyTests(unittest.TestCase):
    """REQUIRE_OWN_KEY (default on): no visitor key means no search and no server key."""

    def setUp(self):
        import agent
        self.agent = agent
        self._env = mock.patch.dict(os.environ, {"SESSION_SEARCH_LIMIT": "5", "DAILY_SEARCH_LIMIT": "100"})
        self._env.start()
        os.environ.pop("REQUIRE_OWN_KEY", None)  # exercise the default
        usage_limits.DAILY_COUNTER = DailyCounter()
        self.calls = []

        def fake_run(query, status_callback=None, api_key=None):
            self.calls.append(api_key)
            return "---\n## Prof X\n**Institution:** Test U\n---"

        self._p = mock.patch.object(agent, "run_professor_agent", fake_run)
        self._p.start()

    def tearDown(self):
        self._p.stop()
        self._env.stop()

    def _app(self):
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file("app.py", default_timeout=30)
        at.run()
        return at

    def _search(self, at, q="find robotics professors"):
        at.text_input(key="search_query").set_value(q)
        at.button[0].click()  # "Hunt"
        at.run()

    def _main_text(self, at):
        parts = []
        for kind in ("markdown", "caption", "warning", "error", "success", "info"):
            parts += [str(e.value) for e in getattr(at.main, kind)]
        return "\n".join(parts)

    def test_setting_defaults_on_and_can_be_turned_off(self):
        self.assertTrue(usage_limits.require_own_key())
        for off in ("false", "0", "no", "off", "FALSE"):
            with mock.patch.dict(os.environ, {"REQUIRE_OWN_KEY": off}):
                self.assertFalse(usage_limits.require_own_key())
        with mock.patch.dict(os.environ, {"REQUIRE_OWN_KEY": "true"}):
            self.assertTrue(usage_limits.require_own_key())

    def test_check_and_consume_refuses_without_key_and_counts_nothing(self):
        state, counter = {}, DailyCounter()
        allowed, msg = check_and_consume(state, "", counter)
        self.assertFalse(allowed)
        self.assertIn(REQUIRED_KEY_MSG, msg)
        self.assertNotIn(SESSION_COUNT_KEY, state)
        self.assertEqual(counter.count(), 0)

    def test_no_key_search_is_refused_in_app(self):
        at = self._app()
        self._search(at)
        self.assertFalse(at.exception)
        self.assertEqual(self.calls, [])  # search function never called
        self.assertNotIn(SESSION_COUNT_KEY, at.session_state)
        self.assertEqual(usage_limits.DAILY_COUNTER.count(), 0)
        self.assertIn(REQUIRED_KEY_MSG, self._main_text(at))

    def test_message_shown_under_hunt_button_before_any_search(self):
        at = self._app()
        self.assertTrue(any(REQUIRED_KEY_MSG in i.value for i in at.main.info))

    def test_sidebar_has_required_label_and_no_free_count(self):
        at = self._app()
        key_box = at.sidebar.text_input[0]
        self.assertEqual(key_box.label, "Anthropic API key (required)")
        self.assertEqual(key_box.proto.type, key_box.proto.PASSWORD)
        self.assertTrue(key_box.help)
        self.assertFalse([c.value for c in at.sidebar.caption if "Free searches left" in c.value])

    def test_with_key_search_runs_and_free_counters_untouched(self):
        at = self._app()
        at.sidebar.text_input[0].set_value(OWN_KEY)
        at.run()
        self._search(at)
        self._search(at)
        self.assertEqual(self.calls, [OWN_KEY, OWN_KEY])
        self.assertNotIn(SESSION_COUNT_KEY, at.session_state)
        self.assertEqual(usage_limits.DAILY_COUNTER.count(), 0)
        self.assertFalse(any(REQUIRED_KEY_MSG in i.value for i in at.main.info))
        self.assertNotIn(OWN_KEY, self._main_text(at))


class RequireOwnKeyServerKeyTests(unittest.TestCase):
    """End to end through the real agent (discovery mocked): the server key is never used."""

    def setUp(self):
        self._env = mock.patch.dict(os.environ, {})
        self._env.start()
        os.environ.pop("REQUIRE_OWN_KEY", None)
        FakeAnthropic.instances = []
        self._p = mock.patch.object(llm_budget, "Anthropic", FakeAnthropic)
        self._p.start()
        llm_budget._client = None
        usage_limits.DAILY_COUNTER = DailyCounter()

    def tearDown(self):
        self._p.stop()
        self._env.stop()
        llm_budget._client = None

    def test_no_key_never_falls_back_to_server_key(self):
        import agent
        from streamlit.testing.v1 import AppTest
        prof = {"name": "Ada Lovelace", "institution": "Test U", "email": "", "research_description": "x",
                "grant_title": "", "grant_amount": "Unknown", "abstract": "", "recent_papers": []}
        discovered = []

        def fake_discover(query, limit, status_callback, budget):
            discovered.append(query)
            budget.create(model="claude-haiku-4-5-20251001", max_tokens=50, messages=[])
            return [prof]

        out = io.StringIO()
        with mock.patch.object(agent, "discover_professors", fake_discover), \
             contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            at = AppTest.from_file("app.py", default_timeout=30)
            at.run()
            at.text_input(key="search_query").set_value("find robotics professors")
            at.button[0].click()
            at.run()
            self.assertFalse(at.exception)
            self.assertEqual(discovered, [])
            self.assertIsNone(llm_budget._client)  # shared (server-key) client never built
            server_key = os.environ["ANTHROPIC_API_KEY"]
            self.assertNotIn(server_key, [c.api_key for c in FakeAnthropic.instances])
            self.assertEqual(FakeAnthropic.instances, [])

            # With a visitor key, only that key reaches a client.
            at.sidebar.text_input[0].set_value(OWN_KEY)
            at.run()
            at.button[0].click()
            at.run()
            self.assertEqual(discovered, ["find robotics professors"])
            self.assertEqual({c.api_key for c in FakeAnthropic.instances}, {OWN_KEY})
            self.assertIsNone(llm_budget._client)

if __name__ == "__main__":
    unittest.main()
