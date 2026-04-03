#!/usr/bin/env python3
"""Fixed entry point for pre-built plugin containers.

Plugin images MUST ship this script (or an equivalent at /opt/plugin/run_tool.py)
and copy plugin tool code into /opt/plugin/. The Runner invokes this entry point
with PLUGIN_TOOL_NAME + PLUGIN_TOOL_INPUT environment variables and reads a
single JSON object from stdout.

Design contract:
  - Tool name comes from PLUGIN_TOOL_NAME.
  - Tool JSON input comes from PLUGIN_TOOL_INPUT.
  - Plugin code is loaded from /opt/plugin/ (no stdin, no dynamic exec).
  - Exactly one JSON object is printed to stdout (plus optional marker lines).
"""

import importlib.util
import json
import os
import sys

PLUGIN_DIR = "/opt/plugin"


def _load_module(module_name: str, path: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load plugin module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _discover_plugin_module():
    """Locate plugin tool code under /opt/plugin/.

    Resolution order:
      1. /opt/plugin/__init__.py — package-style plugin
      2. /opt/plugin/main.py
      3. /opt/plugin/plugin.py
      4. /opt/plugin/tools.py
    """
    candidates = ["__init__.py", "main.py", "plugin.py", "tools.py"]
    for name in candidates:
        path = os.path.join(PLUGIN_DIR, name)
        if os.path.isfile(path):
            return _load_module("hfusion_plugin_tools", path)
    raise ImportError(
        f"No plugin module found under {PLUGIN_DIR}. Expected __init__.py, main.py, plugin.py or tools.py"
    )


def main() -> int:
    tool_name = os.environ.get("PLUGIN_TOOL_NAME")
    if not tool_name:
        raise RuntimeError("PLUGIN_TOOL_NAME is not set")
    if not os.path.isdir(PLUGIN_DIR):
        raise RuntimeError(f"Plugin directory {PLUGIN_DIR} does not exist")

    raw_input = os.environ.get("PLUGIN_TOOL_INPUT", "{}")
    try:
        tool_input = json.loads(raw_input)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"invalid PLUGIN_TOOL_INPUT: {e}") from e
    if not isinstance(tool_input, dict):
        raise RuntimeError("PLUGIN_TOOL_INPUT must be a JSON object")

    sys.path.insert(0, PLUGIN_DIR)
    module = _discover_plugin_module()

    func = getattr(module, tool_name, None)
    if func is None:
        raise AttributeError(f"Tool '{tool_name}' not found in plugin module")
    if not callable(func):
        raise TypeError(f"'{tool_name}' is not callable")

    result = func(**tool_input)
    # Print exactly one JSON object as the result payload.
    print(json.dumps({"success": True, "data": result}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # noqa: BLE001 — entry point must always emit JSON
        print(json.dumps({"success": False, "error": str(e)}, ensure_ascii=False))
        sys.exit(1)
