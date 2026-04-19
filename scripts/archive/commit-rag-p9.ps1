$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

git diff --cached --quiet
if ($LASTEXITCODE -ne 0) {
    throw '暂存区已有改动。请先提交或取消暂存它们，避免本脚本提交无关文件。'
}

& "$PSScriptRoot/verify-rag-p9.ps1"

git add `
  python-ai/.env.example `
  python-ai/app/api/chat.py `
  python-ai/app/core/agent/__init__.py `
  python-ai/app/core/agent/agent.py `
  python-ai/app/core/agent/react.py `
  python-ai/app/core/agent/workflow_runtime.py `
  python-ai/app/core/tools/__init__.py `
  python-ai/app/utils/config.py `
  python-ai/tests/test_single_agent_workflow.py `
  scripts/verify-rag-p9.ps1 `
  scripts/commit-rag-p9.ps1

git commit -m 'feat(agent): add bounded single-agent workflow runtime'
git status
