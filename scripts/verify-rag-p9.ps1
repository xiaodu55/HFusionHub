$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
Push-Location $repoRoot
try {
    Write-Host '1/3 Python P9 focused regression'
    Push-Location python-ai
    try {
        py -m pytest -q `
            tests/test_single_agent_workflow.py `
            tests/test_rag_access_contract.py `
            tests/test_query_router.py `
            tests/test_rag_observability.py `
            tests/test_scoped_graph.py `
            tests/test_multimodal_evidence.py

        Write-Host '2/3 Python full regression'
        py -m pytest -q
    }
    finally {
        Pop-Location
    }

    Write-Host '3/3 Java tests and frontend production build'
    Push-Location java-backend
    try { mvn -q test } finally { Pop-Location }

    Push-Location hfusionhub-frontend
    try { npm ci; npm run build } finally { Pop-Location }

    Write-Host 'P9 bounded single-agent verification passed.' -ForegroundColor Green
}
finally {
    Pop-Location
}
