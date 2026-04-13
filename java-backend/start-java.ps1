$ErrorActionPreference = "Stop"

$required = @(
    "DB_USERNAME",
    "DB_PASSWORD",
    "CALLBACK_SECRET",
    "PYTHON_AI_INTERNAL_TOKEN",
    "ADMIN_PASSWORD"
)
$missing = @($required | Where-Object {
    $value = (Get-Item "Env:$_" -ErrorAction SilentlyContinue).Value
    [string]::IsNullOrWhiteSpace($value)
})
if ($missing.Count -gt 0) {
    throw "Missing required environment variables: $($missing -join ', ')"
}

Set-Location (Join-Path $PSScriptRoot "..")
& mvn -f "java-backend/pom.xml" spring-boot:run
