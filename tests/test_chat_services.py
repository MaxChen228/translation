import os
import tempfile
import time
import unittest

os.environ.setdefault("USAGE_DB_PATH", os.path.join(tempfile.gettempdir(), "usage_test.sqlite"))

from app.schemas import ChatMessage, ChatTurnRequest, ChatResearchRequest, ChatAttachment
from app.services.chat import run_turn, run_research, _serialize_messages
from app.usage import reset_usage
from app.usage.models import LLMUsage


class StubProvider:
    def __init__(self, payload):
        self.payload = payload

    def resolve_model(self, override):
        return override or "stub"

    def generate_json(self, system_prompt, user_content, *, model=None, inline_parts=None, timeout=60):
        usage = LLMUsage(
            timestamp=time.time(),
            provider="stub",
            api_kind="generateContent",
            model=self.resolve_model(model),
            api_endpoint="https://example.com/models/stub:generateContent",
            inline_parts=len(list(inline_parts or [])),
            prompt_chars=len(user_content),
            input_tokens=10,
            output_tokens=5,
            total_tokens=15,
            latency_ms=12.5,
            status_code=200,
        )
        return self.payload, usage


class ChatServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_usage()

    def test_run_turn(self):
        provider = StubProvider({
            "reply": "好的，我會先確認結構。",
            "state": "ready",
            "checklist": ["確認主旨", "擬定摘要"],
        })
        req = ChatTurnRequest(messages=[ChatMessage(role="user", content="請幫我整理研究重點")])
        resp = run_turn(req, provider, device_id="test-device", route="/chat/respond")
        self.assertTrue(resp.reply.startswith("## 回覆摘要"))
        self.assertEqual(resp.state, "ready")
        self.assertEqual(resp.checklist, ["確認主旨", "擬定摘要"])

    def test_run_research(self):
        provider = StubProvider({
            "items": [
                {
                    "term": "broaden my perspective",
                    "explanation": "片語表示拓展視野。",
                    "context": "I want to study abroad to broaden my perspective.",
                    "type": "lexical",
                }
            ]
        })
        req = ChatResearchRequest(messages=[ChatMessage(role="user", content="幫我潤飾這段英文")])
        resp = run_research(req, provider, device_id="test-device", route="/chat/research")
        self.assertEqual(len(resp.items), 1)
        first = resp.items[0]
        self.assertEqual(first.term, "broaden my perspective")
        self.assertEqual(first.type, "lexical")
        self.assertIn("study abroad", first.context)

    def test_serialize_messages_with_image(self):
        attachment = ChatAttachment(type="image", mimeType="image/png", data="ZmFrZV9iYXNlNjQ=")
        msg = ChatMessage(role="user", content="看圖說故事", attachments=[attachment])
        payload, parts = _serialize_messages([msg])
        self.assertIn("attachments", payload)
        self.assertEqual(len(parts), 1)
        self.assertEqual(parts[0]["inline_data"]["mime_type"], "image/png")
        self.assertIn('"index": 1', payload)


if __name__ == "__main__":
    unittest.main()
