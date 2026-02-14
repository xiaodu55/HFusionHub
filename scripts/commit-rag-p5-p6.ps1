$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

git diff --cached --quiet
if ($LASTEXITCODE -ne 0) {
    throw '暂存区已有改动。请先提交或取消暂存它们，避免本脚本提交无关文件。'
}

& "$PSScriptRoot/verify-rag-p5-p6.ps1"

git add `
  python-ai/.env.example `
  python-ai/app/api/rag.py `
  python-ai/app/api/vectorization.py `
  python-ai/app/core/chunker/quality.py `
  python-ai/app/core/rag/evaluation_runs.py `
  python-ai/app/core/rag/reranker.py `
  python-ai/app/core/rag/retriever.py `
  python-ai/app/utils/config.py `
  python-ai/evaluation/README.md `
  python-ai/requirements-reranker.txt `
  python-ai/tests/test_chunk_quality.py `
  python-ai/tests/test_evaluation_runs.py `
  python-ai/tests/test_rag_observability.py `
  python-ai/tests/test_reranker.py `
  java-backend/src/main/java/com/hfusionhub/controller/RagObservabilityController.java `
  hfusionhub-frontend/src/api/rag.ts `
  hfusionhub-frontend/src/pages/rag/Index.vue `
  scripts/verify-rag-p5-p6.ps1 `
  scripts/commit-rag-p5-p6.ps1

git commit -m 'feat(rag): add evaluation history and optional reranking'
git status
