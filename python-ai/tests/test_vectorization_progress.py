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


def test_remaining_seconds_uses_observed_progress_when_initial_estimate_is_overrun():
    now = 1000.0
    status = {
        "status": "PROCESSING",
        "start_time": now - 64,
        "estimated_seconds": 70,
        "progress": 35,
    }

    remaining = _remaining_seconds(status, now=now)

    # 64 seconds at 35% implies about 183 seconds total, so the ETA must not
    # be zero even though the initial 70-second estimate has elapsed.
    assert 100 <= remaining <= 125


def test_remaining_seconds_keeps_at_least_one_second_for_non_terminal_tasks():
    now = 1000.0
    status = {
        "status": "PROCESSING",
        "start_time": now - 60,
        "estimated_seconds": 20,
        "progress": 95,
    }

    assert _remaining_seconds(status, now=now) >= 1
