from pathlib import Path

import moderation_bot as mod


def source_post(**extra):
    message = {
        "message_id": 42,
        "chat": {"id": -100123, "username": "approved_source"},
        "text": "A useful update",
    }
    message.update(extra)
    return message


def configure(monkeypatch, tmp_path, *, live):
    monkeypatch.setattr(mod, "SOURCE_CHANNELS", {"approved_source"})
    monkeypatch.setattr(mod, "RELAY_TARGETS", ["@klaus_test"])
    monkeypatch.setattr(mod, "BRAND_TAG", "@KLAUS")
    dry_run = tmp_path / "DRY_RUN"
    dry_run.write_text("false" if live else "true", encoding="utf-8")
    monkeypatch.setattr(mod, "DRY_RUN_FILE", Path(dry_run))
    calls = []

    def fake_api(method, payload, timeout=40):
        calls.append((method, payload))
        return {}

    monkeypatch.setattr(mod, "api", fake_api)
    return calls


def test_dry_run_does_not_send(monkeypatch, tmp_path):
    calls = configure(monkeypatch, tmp_path, live=False)
    mod.relay_channel_post(source_post())
    assert calls == []


def test_text_post_is_branded_and_source_link_retained(monkeypatch, tmp_path):
    calls = configure(monkeypatch, tmp_path, live=True)
    mod.relay_channel_post(source_post())
    assert len(calls) == 1
    method, payload = calls[0]
    assert method == "sendMessage"
    assert payload["chat_id"] == "@klaus_test"
    assert "A useful update" in payload["text"]
    assert "@KLAUS" in payload["text"]
    assert "https://t.me/approved_source/42" in payload["text"]


def test_video_is_copied_without_forward_header_and_with_source_caption(monkeypatch, tmp_path):
    calls = configure(monkeypatch, tmp_path, live=True)
    mod.relay_channel_post(source_post(text=None, video=[{"file_id": "abc"}], caption="Video caption"))
    assert len(calls) == 1
    method, payload = calls[0]
    assert method == "copyMessage"
    assert payload["chat_id"] == "@klaus_test"
    assert payload["caption"].startswith("Video caption")
    assert "https://t.me/approved_source/42" in payload["caption"]


def test_voice_post_gets_separate_brand_source_message(monkeypatch, tmp_path):
    calls = configure(monkeypatch, tmp_path, live=True)
    mod.relay_channel_post(source_post(text=None, voice={"file_id": "voice-id"}, caption=""))
    assert [method for method, _ in calls] == ["copyMessage", "sendMessage"]
    assert "https://t.me/approved_source/42" in calls[1][1]["text"]
