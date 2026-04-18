#!/usr/bin/env bash
# 校验家居 DSL 并打印导入说明。在仓库根目录执行: bash scripts/dify_home_furnishing.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
YML="$ROOT/deploy/dify/home_furnishing_showcase_chatflow.yml"
cd "$ROOT"
echo "== info =="
python scripts/dify_workflow_cli.py info "$YML"
echo ""
echo "== validate (needs: pip install pyyaml) =="
python scripts/dify_workflow_cli.py validate "$YML"
