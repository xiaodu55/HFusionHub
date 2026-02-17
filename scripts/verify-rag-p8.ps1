$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
Push-Location $repoRoot
try {
    Write-Host '1/3 Python P8 targeted regression'
    Push-Location python-ai
    try {
        py -m pytest -q `
            tests/test_multimodal_evidence.py `
            tests/test_query_router.py `
            tests/test_retrieval_evaluator.py `
            tests/test_rag_observability.py `
            tests/test_scoped_graph.py

        Write-Host '2/3 Python full regression'
        py -m pytest -q

        # P8 runs disabled by default.  The unit suite does not need native OCR
        # or pypdf, but report what a production-enabled setup still needs.
        $multimodalEnabled = (py -c "from app.utils.config import config; print(str(config.RAG_MULTIMODAL_ENABLED).lower())").Trim()
        $ocrEnabled = (py -c "from app.utils.config import config; print(str(config.RAG_MULTIMODAL_OCR_ENABLED).lower())").Trim()
        if ($multimodalEnabled -eq 'true' -and $ocrEnabled -eq 'true') {
            py -c "import pypdf"
            $ocrCommand = (py -c "from app.utils.config import config; print(config.RAG_MULTIMODAL_OCR_COMMAND)").Trim()
            if (-not (Get-Command $ocrCommand -ErrorAction SilentlyContinue)) {
                throw "P8 OCR is enabled but '$ocrCommand' is not on PATH. Install Tesseract or set RAG_MULTIMODAL_OCR_COMMAND."
            }
            & $ocrCommand --version
            if ($LASTEXITCODE -ne 0) {
                throw "P8 OCR command '$ocrCommand --version' failed."
            }
        }
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

    Write-Host 'P8 multimodal evidence verification passed.' -ForegroundColor Green
}
finally {
    Pop-Location
}
