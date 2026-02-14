$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

git diff --cached --quiet
if ($LASTEXITCODE -ne 0) {
    throw '暂存区已有改动。请先提交或取消暂存它们，避免本脚本提交无关文件。'
}

& "$PSScriptRoot/verify-rag-p7.ps1"

git add `
  python-ai/.env.example `
  python-ai/app/api/rag.py `
  python-ai/app/api/vectorization.py `
  python-ai/app/core/rag/evaluation.py `
  python-ai/app/core/rag/query_router.py `
  python-ai/app/core/rag/scoped_graph.py `
  python-ai/app/utils/config.py `
  python-ai/evaluation/README.md `
  python-ai/tests/test_rag_observability.py `
  python-ai/tests/test_scoped_graph.py `
  scripts/verify-rag-p7.ps1 `
  scripts/commit-rag-p7.ps1

git commit -m 'feat(rag): add scoped graph retrieval'
git status
