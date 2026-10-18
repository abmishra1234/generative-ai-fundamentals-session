import httpx
import pytest
from openai import APIConnectionError, APIStatusError, APITimeoutError

from app.image_service import AdComposeError
from app.quote_service import refine_quote
from app.schemas import QuoteRefineRequest


def test_refine_uses_chat_and_parses_suggestions(fake_client, app_config):
    result = refine_quote(QuoteRefineRequest(quote="our cream is good", mood="playful", brand_name="Lumina"))
    assert result == ["Glow all day", "Your skin, upgraded"]
    call = fake_client.chat.completions.calls[0]
    assert call["messages"][0]["role"] == "developer"
    content = call["messages"][1]["content"]
    assert all(value in content for value in ("our cream is good", "playful", "Lumina"))
    assert call["timeout"] > 0


@pytest.mark.parametrize("brand", [None, "Lumina"])
def test_refine_offline(fake_client, app_config, brand):
    app_config(dry_run=True)
    result = refine_quote(QuoteRefineRequest(quote="  Glow   all day  ", brand_name=brand))
    expected = ["Glow all day", "Glow all day !"]
    if brand:
        expected.append("Lumina: Glow all day")
    assert result == expected
    assert fake_client.chat.completions.calls == []


def test_refine_empty_answer(fake_client, app_config):
    fake_client.chat.completions.content = ""
    with pytest.raises(AdComposeError) as exc:
        refine_quote(QuoteRefineRequest(quote="Glow"))
    assert exc.value.status_code == 502


@pytest.mark.parametrize("kind, status", [(APITimeoutError, 504), (APIConnectionError, 502), (APIStatusError, 502)])
def test_refine_sdk_errors(fake_client, app_config, kind, status):
    request = httpx.Request("POST", "https://example.test/chat/completions")
    error = (kind("unavailable", response=httpx.Response(503, request=request), body=None)
             if kind is APIStatusError else kind(request=request))
    fake_client.chat.completions.raise_exc = error
    with pytest.raises(AdComposeError) as exc:
        refine_quote(QuoteRefineRequest(quote="Glow"))
    assert exc.value.status_code == status
    assert exc.value.__cause__ is error
