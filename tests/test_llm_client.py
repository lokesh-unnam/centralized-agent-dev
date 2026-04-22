"""
Tests for llm_client — OpenAI strict version.
All tests use mocks — no real API calls.
"""
import os
import sys
from unittest.mock import MagicMock, patch
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("OPENAI_API_KEY", "sk-test")
os.environ.setdefault("MODEL_STRONG", "gpt-4o")
os.environ.setdefault("MODEL_FAST", "gpt-4o-mini")

def _make_openai_response(text: str) -> MagicMock:
    msg = MagicMock()
    msg.choices = [MagicMock(message=MagicMock(content=text))]
    return msg

class TestLLMClientOpenAI:
    def test_missing_openai_key_raises(self):
        import importlib
        import llm_client
        importlib.reload(llm_client)

        with patch("llm_client.settings") as mock_settings:
            mock_settings.openai_api_key = ""  # missing
            with pytest.raises(ValueError, match="OPENAI_API_KEY"):
                llm_client._make_openai_client()

    def test_openai_call_returns_text(self):
        import importlib
        import llm_client
        importlib.reload(llm_client)

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = \
            _make_openai_response("hello from gpt")

        with patch("llm_client._client", mock_client), \
             patch("llm_client.settings") as mock_settings:
            mock_settings.openai_api_key = "sk-test"
            mock_settings.model_strong = "gpt-4o"
            mock_settings.model_fast = "gpt-4o-mini"
            result = llm_client.call(system="sys", user_message="msg")

        assert result == "hello from gpt"

    def test_openai_multi_turn_prepends_system(self):
        import importlib
        import llm_client
        importlib.reload(llm_client)

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_openai_response("ok")

        messages = [{"role": "user", "content": "hello"}]

        with patch("llm_client._client", mock_client), \
             patch("llm_client.settings") as mock_settings:
            mock_settings.openai_api_key = "sk-test"
            mock_settings.model_strong = "gpt-4o"
            mock_settings.model_fast = "gpt-4o-mini"
            llm_client.call_with_messages(system="be helpful", messages=messages)

        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        sent_messages = call_kwargs["messages"]
        # System message must be prepended as first message
        assert sent_messages[0]["role"] == "system"
        assert sent_messages[0]["content"] == "be helpful"
        assert sent_messages[1] == messages[0]

class TestGetProviderInfo:
    def test_returns_provider_and_models(self):
        import importlib
        import llm_client
        importlib.reload(llm_client)

        with patch("llm_client.settings") as mock_settings:
            mock_settings.llm_provider = "openai"
            mock_settings.model_strong = "gpt-4o"
            mock_settings.model_fast = "gpt-4o-mini"
            info = llm_client.get_provider_info()

        assert info["provider"] == "openai"
        assert info["model_strong"] == "gpt-4o"
        assert info["model_fast"] == "gpt-4o-mini"
