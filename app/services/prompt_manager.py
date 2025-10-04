from __future__ import annotations

import os
import shutil
import time
from dataclasses import dataclass
from typing import Dict, Optional

from app.core.settings import get_settings


def _backend_root() -> str:
    here = os.path.dirname(__file__)
    # Return repository root (same base used by legacy prompt loader)
    return os.path.abspath(os.path.join(here, "..", ".."))


@dataclass(frozen=True)
class PromptConfig:
    prompt_id: str
    setting_name: str
    default_path: str
    cache_key: str
    error_token: Optional[str]

    def resolve_path(self) -> str:
        settings = get_settings()
        configured = getattr(settings, self.setting_name, None) or self.default_path
        if not os.path.isabs(configured):
            configured = os.path.join(_backend_root(), configured)
        return os.path.abspath(configured)


_PROMPT_CONFIGS: Dict[str, PromptConfig] = {
    "system": PromptConfig(
        prompt_id="system",
        setting_name="PROMPT_FILE",
        default_path="prompts/prompt.txt",
        cache_key="system_prompt",
        error_token=None,
    ),
    "deck": PromptConfig(
        prompt_id="deck",
        setting_name="DECK_PROMPT_FILE",
        default_path="prompts/prompt_deck.txt",
        cache_key="deck_prompt",
        error_token="prompt_deck.txt",
    ),
    "chat_turn": PromptConfig(
        prompt_id="chat_turn",
        setting_name="CHAT_TURN_PROMPT_FILE",
        default_path="prompts/prompt_chat_turn.txt",
        cache_key="chat_turn_prompt",
        error_token="prompt_chat_turn.txt",
    ),
    "chat_research": PromptConfig(
        prompt_id="chat_research",
        setting_name="CHAT_RESEARCH_PROMPT_FILE",
        default_path="prompts/prompt_chat_research.txt",
        cache_key="chat_research_prompt",
        error_token="prompt_chat_research.txt",
    ),
    "merge": PromptConfig(
        prompt_id="merge",
        setting_name="MERGE_PROMPT_FILE",
        default_path="prompts/prompt_merge.txt",
        cache_key="merge_prompt",
        error_token="prompt_merge.txt",
    ),
    "flashcard_completion": PromptConfig(
        prompt_id="flashcard_completion",
        setting_name="FLASHCARD_COMPLETION_PROMPT_FILE",
        default_path="prompts/prompt_flashcard_completion.txt",
        cache_key="flashcard_completion_prompt",
        error_token="prompt_flashcard_completion.txt",
    ),
    "generate_questions": PromptConfig(
        prompt_id="generate_questions",
        setting_name="QUESTION_PROMPT_FILE",
        default_path="prompts/prompt_generate_questions.txt",
        cache_key="generate_questions_prompt",
        error_token="prompt_generate_questions.txt",
    ),
}


def get_prompt_config(prompt_id: str) -> PromptConfig:
    try:
        return _PROMPT_CONFIGS[prompt_id]
    except KeyError as exc:
        raise ValueError(f"unknown_prompt:{prompt_id}") from exc


def read_prompt(prompt_id: str) -> str:
    config = get_prompt_config(prompt_id)
    path = config.resolve_path()
    try:
        with open(path, "r", encoding="utf-8") as handle:
            content = handle.read().strip()
    except Exception as exc:
        token = config.error_token
        if token is None:
            raise RuntimeError(f"prompt_file_error: {exc}") from exc
        raise RuntimeError(f"prompt_file_error:{token}:{exc}") from exc
    if not content:
        token = config.error_token
        if token is None:
            raise RuntimeError("prompt_file_empty")
        raise RuntimeError(f"prompt_file_empty:{token}")
    return content


def write_prompt(prompt_id: str, content: str) -> Dict[str, Optional[str]]:
    config = get_prompt_config(prompt_id)
    path = config.resolve_path()
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)

    backup_path = None
    if os.path.exists(path):
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        backup_path = f"{path}.backup_{timestamp}"
        shutil.copy2(path, backup_path)

    temp_path = f"{path}.tmp"
    with open(temp_path, "w", encoding="utf-8") as handle:
        handle.write(content.rstrip() + "\n")
    os.replace(temp_path, path)
    return {"path": path, "backup_path": backup_path}


def list_prompts() -> Dict[str, Dict[str, str]]:
    summary: Dict[str, Dict[str, str]] = {}
    for prompt_id, config in _PROMPT_CONFIGS.items():
        summary[prompt_id] = {
            "path": config.resolve_path(),
            "cache_key": config.cache_key,
        }
    return summary
