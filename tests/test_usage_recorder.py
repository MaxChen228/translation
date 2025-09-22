import os
import tempfile
import time
import unittest

os.environ.setdefault("USAGE_DB_PATH", os.path.join(tempfile.gettempdir(), "usage_test.sqlite"))

from app.usage import LLMUsage, record_usage, query_usage, summarize_usage, reset_usage


class UsageRecorderTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_usage()

    def _make_usage(self, *, device: str, route: str, tokens: tuple[int, int, int], model: str = "gemini-2.5-flash") -> LLMUsage:
        return LLMUsage(
            timestamp=time.time(),
            provider="gemini",
            api_kind="generateContent",
            model=model,
            api_endpoint="https://example.com",
            device_id=device,
            route=route,
            inline_parts=0,
            prompt_chars=24,
            input_tokens=tokens[0],
            output_tokens=tokens[1],
            total_tokens=tokens[2],
            latency_ms=12.3,
            status_code=200,
        )

    def test_record_and_query_usage(self):
        first = self._make_usage(device="device-a", route="/chat/respond", tokens=(10, 5, 15))
        second = self._make_usage(device="device-b", route="/make_deck", tokens=(20, 10, 30))
        record_usage(first, route=first.route, device_id=first.device_id)
        record_usage(second, route=second.route, device_id=second.device_id)

        all_records = query_usage()
        self.assertEqual(len(all_records), 2)

        filtered = query_usage(device_id="device-a")
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0].route, "/chat/respond")

        summary = summarize_usage(device_id="device-a")
        self.assertEqual(summary.count, 1)
        self.assertEqual(summary.total_tokens, 15)
        self.assertEqual(summary.total_input_tokens, 10)
        self.assertGreater(summary.total_cost_usd, 0)

    def test_limit_and_offset(self):
        for idx in range(5):
            input_tokens = idx + 1
            output_tokens = idx + 2
            usage = self._make_usage(
                device=f"device-{idx%2}",
                route="/chat/respond",
                tokens=(input_tokens, output_tokens, input_tokens + output_tokens),
            )
            record_usage(usage, route=usage.route, device_id=usage.device_id)
        limited = query_usage(limit=2)
        self.assertEqual(len(limited), 2)
        offset_records = query_usage(offset=3, limit=2)
        self.assertLessEqual(len(offset_records), 2)


if __name__ == "__main__":
    unittest.main()
