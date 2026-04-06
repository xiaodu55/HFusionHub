"""Minimal deterministic tools for the isolated-engine acceptance test."""

import urllib.request


def echo_tool(text: str = "") -> dict:
    return {"echo": text, "tool": "echo_tool", "source": "acceptance"}


def network_probe_tool(url: str = "") -> dict:
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            return {"ok": True, "status": response.status}
    except Exception as exc:  # noqa: BLE001 - the test needs the failed probe
        return {"ok": False, "error": str(exc)}


def resource_report_tool() -> dict:
    return {"tool": "resource_report_tool"}
