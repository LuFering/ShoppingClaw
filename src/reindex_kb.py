#!/usr/bin/env python3
"""
知识库索引重建脚本

═══════════════════════════════════════════════════════════════════
为什么需要它
═══════════════════════════════════════════════════════════════════
KnowledgeManager.initialize() 发现 Chroma 集合非空时会**直接复用**，
不会重新读取 docs/knowledge/ —— 这是刻意的（避免每次启动重灌）。

后果：往 docs/knowledge/ 加了新文档后，**不重建索引就检索不到**。
这个脚本负责重建。

═══════════════════════════════════════════════════════════════════
用法（在容器内跑，因为 Chroma 和 embedding 都在容器里）
═══════════════════════════════════════════════════════════════════
    # 重建全部
    sudo docker exec shoppingclaw-api python /app/scripts/reindex_kb.py

    # 只看当前状态，不改
    sudo docker exec shoppingclaw-api python /app/scripts/reindex_kb.py --check

    # 只灌某一个文件
    sudo docker exec shoppingclaw-api python /app/scripts/reindex_kb.py --file docs/knowledge/category/phone.md

⚠️ 重建会**清空整个集合再重灌**。如果只想加一个文件，用 --file
   （但 --file 是追加，同一文件重复跑会产生重复数据）。
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, "/app")

DOCS_DIR = Path("/app/docs/knowledge")


async def main():
    ap = argparse.ArgumentParser(description="重建知识库索引")
    ap.add_argument("--check", action="store_true", help="只查看状态")
    ap.add_argument("--file", type=str, help="只灌入指定文件（追加模式）")
    ap.add_argument("--docs-dir", type=str, default=str(DOCS_DIR))
    args = ap.parse_args()

    from src.knowledge.manager import knowledge_manager as km
    from src.knowledge.llama.loader import load_markdown_documents

    docs_dir = Path(args.docs_dir)

    # ── 状态报告 ──
    count_before = km._indexer._vector_store_count()
    md_files = sorted(docs_dir.rglob("*.md")) if docs_dir.exists() else []
    print(f"  文档目录   {docs_dir}")
    print(f"  磁盘上 md  {len(md_files)} 个")
    print(f"  索引条目   {count_before}")

    if args.check:
        print()
        by_type = {}
        for p in md_files:
            text = p.read_text(encoding="utf-8", errors="ignore")
            st = "?"
            for line in text.splitlines()[:12]:
                if line.startswith("source_type:"):
                    st = line.split(":", 1)[1].strip()
                    break
            by_type.setdefault(st, []).append(p.name)
        for st, files in sorted(by_type.items()):
            print(f"    {st:14s} {len(files)} 篇  {', '.join(files[:3])}"
                  + (f" … 共{len(files)}" if len(files) > 3 else ""))
        return

    # ── 单文件追加 ──
    if args.file:
        target = Path(args.file)
        if not target.is_absolute():
            target = Path("/app") / target
        if not target.exists():
            print(f"  ✗ 文件不存在: {target}")
            sys.exit(1)
        n = await asyncio.to_thread(km._indexer.ingest_file, target)
        print(f"\n  ✓ 追加 {target.name}，新增 {n} 个 node")
        print(f"  ⚠️ 追加模式不清理旧数据 —— 同一文件重复跑会产生重复")
        return

    # ── 全量重建 ──
    if not md_files:
        print(f"\n  ✗ {docs_dir} 下没有 md 文件")
        sys.exit(1)

    print("\n  重建中…")
    n = await asyncio.to_thread(km._indexer.ingest_directory, str(docs_dir))

    km._initialized = False
    await km.initialize(str(docs_dir))
    count_after = km._indexer._vector_store_count()

    print(f"\n  ✓ 重建完成")
    print(f"    清空 {count_before} 条 → 灌入 {count_after} 条")


if __name__ == "__main__":
    asyncio.run(main())
