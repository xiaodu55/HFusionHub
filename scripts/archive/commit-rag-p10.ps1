$ErrorActionPreference = 'Stop'

if (-not (git diff --cached --quiet)) {
  throw '暂存区已有内容；为防止混入无关改动，P10 提交已停止。'
}

& "$PSScriptRoot/verify-rag-p10.ps1"

$files = @(
  'python-ai/.env.example',
  'python-ai/app/core/agent/__init__.py',
  'python-ai/app/core/agent/multi_agent_runtime.py',
  'python-ai/app/utils/config.py',
  'python-ai/tests/test_multi_agent_workflow.py',
  'scripts/verify-rag-p10.ps1',
  'scripts/commit-rag-p10.ps1'
)

git add -- $files
git commit -m 'feat(rag): add evidence-reviewed multi-agent workflow'
