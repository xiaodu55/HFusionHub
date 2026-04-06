#!/usr/bin/env python3
"""Fixed entry point used by the acceptance plugin image."""

import importlib.util
import json
import os
import sys


def main() -> int:
    tool_name = os.environ["PLUGIN_TOOL_NAME"]
    tool_input = json.loads(os.environ.get("PLUGIN_TOOL_INPUT", "{}"))
    path = "/opt/plugin/plugin.py"
    spec = importlib.util.spec_from_file_location("acceptance_plugin", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("plugin module could not be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    tool = getattr(module, tool_name)
    print(json.dumps({"success": True, "data": tool(**tool_input)}))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001 - preserve runner's JSON contract
        print(json.dumps({"success": False, "error": str(exc)}))
        raise SystemExit(1)
