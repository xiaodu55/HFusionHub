import os
import time

from app.api.vectorization import _estimate_processing_seconds, _remaining_seconds


def test_estimate_processing_seconds_uses_file_size_and_type(tmp_path):
    pdf = tmp_path / "sample.pdf"
    pdf.write_bytes(b"0" * 1024 * 1024)

    estimate = _estimate_processing_seconds(str(pdf), "pdf")

    assert estimate >= 70
    assert estimate <= 900


def test_remaining_seconds_counts_down_for_processing_status():
    status = {
        "status": "PROCESSING",
        "start_time": time.time() - 5,
        "estimated_seconds": 20,
    }

    remaining = _remaining_seconds(status)

    assert 10 <= remaining <= 15


def test_remaining_seconds_is_zero_for_terminal_status():
    status = {
        "status": "COMPLETED",
        "start_time": time.time() - 5,
        "estimated_seconds": 20,
    }

    assert _remaining_seconds(status) == 0
