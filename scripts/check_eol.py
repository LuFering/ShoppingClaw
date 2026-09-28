#!/usr/bin/env python3
"""行尾守卫 —— 检查工作区有没有**无意**改掉行尾的文件。

═══════════════════════════════════════════════════════════════════
它解决什么
═══════════════════════════════════════════════════════════════════
本仓库行尾不统一（src/ 356/443 是 CRLF），且没有 .gitattributes。
用 `open(p,'w')` 打补丁会把 CRLF 写成 LF，`git diff` 就变成整文件重写：

    SchedulerView.vue   | 1242 ++++-----   ← 真实改动 3 行
    coupon_executor.py  |  193 ++++-----   ← 真实改动 75 行

已踩两次。`scripts/patchlib.py` 解决「怎么改」，这个守卫解决
「怎么知道有没有改坏」—— 靠人记得检查是不可靠的（第一次就忘了）。

═══════════════════════════════════════════════════════════════════
判据
═══════════════════════════════════════════════════════════════════
对一个**已修改**的文件，比较 HEAD 版本与工作区的行尾：
  · HEAD 是 CRLF、工作区变 LF  → **可疑**（很可能被脚本剥掉了）
  · HEAD 是 LF、工作区变 CRLF  → **可疑**（反向污染）
  · 两边一致                    → 正常

只报「变了」的，不报「本来就这样」的 —— 后者是仓库现状，不是问题。

用法：
    python scripts/check_eol.py                  # 检查已修改的文件（提交前跑）
    python scripts/check_eol.py --all            # 连未修改的一起统计
    python scripts/check_eol.py check <file>...  # 只看这几个文件当前的行尾
退出码：发现可疑返回 1（可用于 CI / 提交前钩子）。
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# 只看这些目录（其余是备份/第三方，不关心）
WATCH = ('src/', 'server/', 'web-v2/src/')


def _git(*args) -> str:
    return subprocess.run(['git', *args], capture_output=True, text=True).stdout


def _eol_of_bytes(data: bytes) -> str:
    return 'CRLF' if b'\r\n' in data else 'LF'


def changed_files() -> list[str]:
    """工作区相对 HEAD 有改动的文件（不含未跟踪）。"""
    out = _git('diff', '--name-only', 'HEAD')
    return [f for f in out.splitlines() if f and f.startswith(WATCH)]


def head_bytes(path: str) -> bytes | None:
    r = subprocess.run(['git', 'show', f'HEAD:{path}'],
                       capture_output=True)
    return r.stdout if r.returncode == 0 else None


def main(argv) -> int:
    # 子命令：check <file>... —— 只看这几个文件当前的行尾
    if argv and argv[0] == 'check':
        rest = [a for a in argv[1:] if not a.startswith('-')]
        if not rest:
            print('用法: python scripts/check_eol.py check <file> [...]')
            return 1
        for f in rest:
            p = Path(f)
            if not p.exists():
                print(f'{"缺失":5s} {f}')
                continue
            print(f'{_eol_of_bytes(p.read_bytes()):5s} {f}')
        return 0

    show_all = '--all' in argv
    files = changed_files()
    if not files and not show_all:
        # ⚠️ 措辞要准：WATCH 只覆盖 src/ server/ web-v2/src，
        # 其它目录（文档、脚本、备份）的改动被刻意排除。
        # 原先这里说「工作区干净」—— 实测 AGENTS.md 明明改了却这么报，
        # 会让人以为没改动而不去查。
        other = [f for f in _git('diff', '--name-only', 'HEAD').splitlines()
                 if f and not f.startswith(WATCH)]
        print(f'受关注目录（{", ".join(WATCH)}）内没有改动，无需检查')
        if other:
            print(f'（另有 {len(other)} 个其它目录的改动被跳过：'
                  f'{", ".join(other[:3])}{"…" if len(other) > 3 else ""}）')
        return 0

    suspects = []
    checked = 0
    for f in files:
        head = head_bytes(f)
        if head is None:
            continue
        p = Path(f)
        if not p.exists():
            continue                      # 删掉的文件不算
        checked += 1
        h, w = _eol_of_bytes(head), _eol_of_bytes(p.read_bytes())
        if h != w:
            suspects.append((f, h, w))

    if show_all:
        total = crlf = 0
        for d in WATCH:
            for f in _git('ls-files', d).splitlines():
                if not f:
                    continue
                total += 1
                hb = head_bytes(f)
                if hb is not None and _eol_of_bytes(hb) == 'CRLF':
                    crlf += 1
        print(f'仓库现状：{crlf}/{total} 个受关注文件是 CRLF（这是既有事实，不是问题）')
        print()

    if not suspects:
        print(f'✓ 检查了 {checked} 个已修改文件，行尾都保持一致')
        return 0

    print(f'✗ {len(suspects)} 个文件的行尾被改了：')
    for f, h, w in suspects:
        print(f'    {f}   HEAD={h} → 工作区={w}')
    print()
    print('这通常意味着用 `open(p, "w")` 打补丁把行尾剥掉了 ——')
    print('`git diff` 会显示整个文件重写，review 与 blame 都会被污染。')
    print('修法：git checkout -- <file> 后改用 scripts/patchlib.py 重做，')
    print('     或按原行尾写回（见 scripts/patchlib.py 的 write_text）。')
    return 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
