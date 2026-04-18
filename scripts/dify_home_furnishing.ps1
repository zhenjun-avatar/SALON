# 校验 deploy/dify/home_furnishing_showcase_chatflow.yml 并打印导入说明
# 用法: 在仓库根目录执行  .\scripts\dify_home_furnishing.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Yml = Join-Path $Root "deploy\dify\home_furnishing_showcase_chatflow.yml"

Set-Location $Root

Write-Host "== info ==" -ForegroundColor Cyan
python scripts/dify_workflow_cli.py info $Yml
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "`n== validate (needs: pip install pyyaml) ==" -ForegroundColor Cyan
python scripts/dify_workflow_cli.py validate $Yml
exit $LASTEXITCODE
