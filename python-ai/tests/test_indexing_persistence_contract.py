"""Regression checks for the durable Java/Python indexing callback contract."""

from app.models.document import ParseRequest


def test_parse_request_requires_java_index_version():
    request = ParseRequest(
        document_id="42",
        file_path="/tmp/example.md",
        file_type="md",
        index_version="version-42",
    )

    assert request.index_version == "version-42"


def test_parse_request_rejects_callback_without_index_version():
    try:
        ParseRequest(
            document_id="42",
            file_path="/tmp/example.md",
            file_type="md",
        )
    except ValueError:
        return

    raise AssertionError("index_version must be mandatory to reject stale callbacks")
