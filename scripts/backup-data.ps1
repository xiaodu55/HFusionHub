#backup-data.ps1
# Backup HFusionHub demo/dev data: local uploaded documents + MySQL dump.
#
# Why: java-backend/uploads/documents/ is plain local files — they are lost if
# the dev machine (or its disk) is reset, and MySQL holds conversation/agent
# data that has no file equivalent.  Container rebuilds already proved how
# easily "demo data" can vanish.  This script makes a point-in-time copy of
# both so a reset is recoverable.
#
# Usage:
#   .\scripts\backup-data.ps1              # uploads + MySQL -> .\backup\
#   .\scripts\backup-data.ps1 -SkipMysql   # uploads only
#   .\scripts\backup-data.ps1 -BackupDir D:\bk -Keep 5
#
# Notes:
#   - MySQL dump runs through the mysql8 compose container; requires Docker up.
#   - The password is read from docker\.env (MYSQL_PASSWORD). If it contains
#     double quotes, dump will fail — keep passwords simple.
#   - Old backups beyond -Keep are pruned (uploads + mysql kept separately).

param(
    [string]$BackupDir,
    [switch]$SkipMysql,
    [int]$Keep = 10
)

$ErrorActionPreference = 'Stop'

$RepoRoot = Split-Path -Parent $PSScriptRoot
if (-not $BackupDir) { $BackupDir = Join-Path $RepoRoot 'backup' }
New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
Write-Host "== 数据备份 $stamp =="

# ── 1. 上传目录（java-backend/uploads/documents）──
$uploads = Join-Path $RepoRoot 'java-backend\uploads\documents'
$uploadZip = Join-Path $BackupDir "uploads-$stamp.zip"
if (Test-Path $uploads) {
    $items = Get-ChildItem -Path $uploads -Force | Where-Object { $_.Name -ne 'temp' }
    if ($items) {
        Compress-Archive -Path ($items.FullName) -DestinationPath $uploadZip -CompressionLevel Optimal
        $sizeMB = [math]::Round((Get-Item $uploadZip).Length / 1MB, 2)
        Write-Host "[ok] 上传目录 -> $uploadZip ($sizeMB MB)"
    } else {
        Write-Host "[skip] 上传目录为空（仅 temp ），跳过打包"
    }
} else {
    Write-Host "[skip] 上传目录不存在: $uploads"
}

# ── 2. MySQL dump（经 compose 的 mysql8 容器）──
if (-not $SkipMysql) {
    $envFile = Join-Path $RepoRoot 'docker\.env'
    $mysqlPwd = ''
    if (Test-Path $envFile) {
        $mysqlPwd = (Get-Content $envFile | Where-Object { $_ -match '^MYSQL_PASSWORD=' }) `
            -replace '^MYSQL_PASSWORD=','' | ForEach-Object { $_.Trim().Trim('"').Trim("'") }
    }
    if (-not $mysqlPwd) {
        Write-Warning "docker\.env 缺少 MYSQL_PASSWORD，跳过 MySQL dump"
    } else {
        $sqlRaw = Join-Path $BackupDir "mysql-$stamp.sql"
        # cmd 重定向保持字节原样（PowerShell 的 > 会重编码为 UTF-16）。
        # mysqldump 的密码警告走 stderr：在 cmd 内层用 2>nul 丢弃，避免
        # PowerShell 的 NativeCommandError 中断脚本。直接保留 .sql 不压缩，
        # 演示/开发数据量小，透明且无 gzip/tar 跨平台依赖。
        Write-Host "[..] mysqldump -> $sqlRaw"
        cmd /c "docker exec mysql8 mysqldump -uhfusionhub -p$mysqlPwd --single-transaction --routines --triggers hfusionhub 2>nul > `"$sqlRaw`""
        $dumpExit = $LASTEXITCODE
        if (($dumpExit -ne 0) -or -not (Test-Path $sqlRaw) -or ((Get-Item $sqlRaw).Length -eq 0)) {
            Write-Warning "mysqldump 失败（容器 mysql8 未运行或密码错误），删除残留文件"
            Remove-Item $sqlRaw -Force -ErrorAction SilentlyContinue
        } else {
            $sizeMB = [math]::Round((Get-Item $sqlRaw).Length / 1MB, 2)
            Write-Host "[ok] MySQL dump -> $sqlRaw ($sizeMB MB)"
        }
    }
}

# ── 3. 清理过期备份（uploads 与 mysql 各自保留最近 $Keep 份）──
foreach ($prefix in @('uploads-', 'mysql-')) {
    Get-ChildItem -Path $BackupDir -Filter "$prefix*" -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        Select-Object -Skip $Keep |
        ForEach-Object {
            Write-Host "[prune] $($_.Name)"
            Remove-Item $_.FullName -Force -ErrorAction SilentlyContinue
        }
}

Write-Host '== 备份完成 =='
Write-Host "备份目录: $BackupDir"
