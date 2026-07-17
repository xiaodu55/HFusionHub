"""Sensitive field masking tests."""

from app.core.policy.masking import (
    MASKED,
    build_arguments_summary,
    mask_sensitive_fields,
)


def test_masks_common_sensitive_keys():
    data = {"password": "hunter2", "content": "public note"}
    out = mask_sensitive_fields(data)
    assert out["password"] == MASKED
    assert out["content"] == "public note"


def test_masks_nested_dict_and_list():
    data = {
        "login": {
            "token": "abc123",
            "username": "alice",
        },
        "items": [{"api_key": "k1"}, {"secret": "s1"}],
    }
    out = mask_sensitive_fields(data)
    assert out["login"]["token"] == MASKED
    assert out["login"]["username"] == "alice"
    assert out["items"][0]["api_key"] == MASKED
    assert out["items"][1]["secret"] == MASKED


def test_key_match_case_insensitive_and_suffix():
    data = {"Business_Password": "x", "client_secret": "y", "username": "z"}
    out = mask_sensitive_fields(data)
    assert out["Business_Password"] == MASKED
    assert out["client_secret"] == MASKED
    assert out["username"] == "z"


def test_build_arguments_summary_is_masked():
    data = {
        "content": "meeting notes",
        "tool_input": {"password": "pwd", "note": "ok"},
    }
    summary = build_arguments_summary(data)
    assert "pwd" not in summary
    assert MASKED in summary
    assert "meeting notes" in summary


def test_build_arguments_summary_truncates():
    data = {"content": "x" * 500}
    summary = build_arguments_summary(data, max_chars=80)
    assert len(summary) <= 80
