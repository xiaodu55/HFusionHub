$ErrorActionPreference = 'Stop'

if (git diff --cached --quiet) {
  # Safe: the verification command must not silently include unrelated staged files.
} else {
  throw '暂存区已有内容；请先提交或取消暂存后再运行 P10 验证。'
}

Push-Location python-ai
try {
  py -m pytest tests/test_multi_agent_workflow.py tests/test_single_agent_workflow.py -q
  py -m pytest -q
}
finally {
  Pop-Location
}

Push-Location java-backend
try {
  mvn test
}
finally {
  Pop-Location
}

Push-Location hfusionhub-frontend
try {
  npm run build
}
finally {
  Pop-Location
}
