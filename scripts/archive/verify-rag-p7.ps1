$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
Push-Location $repoRoot
try {
    Write-Host '1/3 Python P7 targeted regression'
    Push-Location python-ai
    try {
        py -m pytest -q `
            tests/test_scoped_graph.py `
            tests/test_query_router.py `
            tests/test_retrieval_evaluator.py `
            tests/test_rag_observability.py

        Write-Host '2/3 Python full regression'
        py -m pytest -q
    }
    finally {
        Pop-Location
    }

    Write-Host '3/3 Java tests and frontend production build'
    Push-Location java-backend
    try {
        mvn -q test
    }
    finally {
        Pop-Location
    }

    Push-Location hfusionhub-frontend
    try {
        npm ci
        npm run build
    }
    finally {
        Pop-Location
    }

    Write-Host 'P7 GraphRAG verification passed.' -ForegroundColor Green
}
finally {
    Pop-Location
}
