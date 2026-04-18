#!/usr/bin/env python3
"""
Dify 工作流 DSL 小工具：校验 YAML、打印导入说明。

依赖（仅 validate 需要）:
  pip install pyyaml

用法:
  python scripts/dify_workflow_cli.py validate deploy/dify/home_furnishing_showcase_chatflow.yml
  python scripts/dify_workflow_cli.py info deploy/dify/home_furnishing_showcase_chatflow.yml
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def cmd_validate(path: Path) -> int:
    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError:
        print("缺少 PyYAML。请执行: pip install pyyaml", file=sys.stderr)
        return 1
    raw = path.read_text(encoding="utf-8")
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as e:
        print(f"YAML 解析失败: {e}", file=sys.stderr)
        return 1
    if not isinstance(data, dict):
        print("根节点应为 mapping", file=sys.stderr)
        return 1
    if data.get("kind") != "app":
        print('期望 kind: app', file=sys.stderr)
        return 1
    wf = data.get("workflow")
    if not isinstance(wf, dict):
        print("缺少 workflow 对象", file=sys.stderr)
        return 1
    graph = wf.get("graph")
    if not isinstance(graph, dict):
        print("缺少 workflow.graph", file=sys.stderr)
        return 1
    nodes = graph.get("nodes")
    edges = graph.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        print("graph.nodes / graph.edges 应为列表", file=sys.stderr)
        return 1
    ids = {n.get("id") for n in nodes if isinstance(n, dict)}
    for e in edges:
        if not isinstance(e, dict):
            continue
        for k in ("source", "target"):
            if e.get(k) and e[k] not in ids:
                print(f"边引用未知节点 id: {e.get('id')} -> {k}={e[k]!r}", file=sys.stderr)
                return 1
    print(f"OK: {path} — {len(nodes)} nodes, {len(edges)} edges")
    return 0


def cmd_info(path: Path) -> int:
    print("文件:", path.resolve())
    print()
    print("导入 Dify（控制台）:")
    print("  1. 登录 Dify 工作室 → 创建空白应用 → 高级对话 / 工作流")
    print("  2. 右上角「...」或设置中找到「导入 DSL / Import DSL」")
    print(f"  3. 选择本文件: {path.name}")
    print("  4. 按 DSL 文件头注释配置模型并发布")
    print()
    print("可选：校验 DSL（需 PyYAML）")
    print(f"  python scripts/dify_workflow_cli.py validate {path.as_posix()}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Dify DSL 校验与说明")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_val = sub.add_parser("validate", help="解析并校验 DSL YAML")
    p_val.add_argument("yml", type=Path, help="DSL 文件路径")

    p_info = sub.add_parser("info", help="打印手动导入步骤")
    p_info.add_argument("yml", type=Path, nargs="?", help="DSL 文件路径")

    args = parser.parse_args()
    _repo_root()  # reserved for future env checks
    if args.cmd == "validate":
        path = args.yml
        if not path.is_file():
            print(f"文件不存在: {path}", file=sys.stderr)
            return 1
        return cmd_validate(path)
    if args.cmd == "info":
        path = args.yml or (_repo_root() / "deploy/dify/home_furnishing_showcase_chatflow.yml")
        if not path.is_file():
            print(f"文件不存在: {path}", file=sys.stderr)
            return 1
        return cmd_info(path)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
