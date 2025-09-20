import unittest

from app.schemas import ChatMessage, ChatTurnRequest, ChatResearchRequest, ChatAttachment
from app.services.chat import run_turn, run_research, _serialize_messages


class StubProvider:
    def __init__(self, payload):
        self.payload = payload

    def resolve_model(self, override):
        return override or "stub"

    def generate_json(self, system_prompt, user_content, *, model=None, inline_parts=None, timeout=60):
        return self.payload


class ChatServiceTests(unittest.TestCase):
    def test_run_turn(self):
        provider = StubProvider({
            "reply": "好的，我會先確認結構。",
            "state": "ready",
            "checklist": ["確認主旨", "擬定摘要"],
        })
        req = ChatTurnRequest(messages=[ChatMessage(role="user", content="請幫我整理研究重點")])
        resp = run_turn(req, provider)
        self.assertEqual(resp.reply, "好的，我會先確認結構。")
        self.assertEqual(resp.state, "ready")
        self.assertEqual(resp.checklist, ["確認主旨", "擬定摘要"])

    def test_run_research(self):
        provider = StubProvider({
            "title": "留學動機整理",
            "summary": "整理使用者提供的草稿並提出修正建議。",
            "sourceZh": "申請內容",
            "attemptEn": "I want study abroad.",
            "correctedEn": "I want to study abroad to broaden my perspective.",
            "errors": [
                {
                    "span": "want study",
                    "type": "morphological",
                    "explainZh": "缺少 to 不定詞",
                    "suggestion": "want to study",
                }
            ],
        })
        req = ChatResearchRequest(messages=[ChatMessage(role="user", content="幫我潤飾這段英文")])
        resp = run_research(req, provider)
        self.assertEqual(resp.title, "留學動機整理")
        self.assertEqual(resp.summary, "整理使用者提供的草稿並提出修正建議。")
        self.assertEqual(resp.correctedEn, "I want to study abroad to broaden my perspective.")
        self.assertEqual(len(resp.errors), 1)
        self.assertEqual(resp.errors[0].type, "morphological")

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
