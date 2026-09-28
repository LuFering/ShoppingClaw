#!/usr/bin/env python3
"""二进制安全的补丁工具 —— 给「批量改文件」的脚本用。

═══════════════════════════════════════════════════════════════════
为什么需要它（这个仓库踩过两次的真问题）
═══════════════════════════════════════════════════════════════════
本仓库**行尾不统一**，实测：

    src/         356 / 443 个文件是 CRLF
    web-v2/src    62 / 182
    server        11 /  22
    且**没有** .gitattributes、也没设 core.autocrlf

Python 的 `open(p, 'w')` 是文本模式：读进来把 `\\r\\n` 归一成 `\\n`，
写回去就再也回不来了。后果是 `git diff` 显示**整个文件重写**：

    SchedulerView.vue   | 1242 ++++-----   ← 真实改动只有 3 行
    coupon_executor.py  |  193 ++++-----   ← 真实改动 75 行

不只难看：review 没法做、`git blame` 被污染、部署对比失去意义。
已踩两次（第二次是主动查出来的）。

═══════════════════════════════════════════════════════════════════
顺带解决第二个反复出现的 bug：锚点匹配数
═══════════════════════════════════════════════════════════════════
`str.replace(old, new)` 默认替换**所有**匹配。锚点在同一文件里出现两次时
（如 `PlanningRun` 与 `GiftRun` 有结构相同的字段声明），会一次改两处 ——
本项目曾因此把 `delivered_at` 误加到 GiftRun 上，导致入口页 500。

`patch()` 强制断言「每对锚点恰好匹配 N 次」，不符就抛错 ——
不给静默改错的机会。

用法：
    from scripts.patchlib import patch
    patch('src/foo.py', [('旧片段', '新片段')])       # 必须恰好 1 次
    patch('src/bar.py', [('x', 'y')], count=2)        # 明确要 2 次

命令行自查（改完文件后跑一眼，diff 行数异常大就是行尾被动了）：
    python scripts/patchlib.py check <file> [...]
    python scripts/patchlib.py selftest
"""
from __future__ import annotations

import sys
from pathlib import Path


def read_text(path) -> tuple[str, str]:
    """读文件 → (文本, 原始行尾)。文本归一到 \\n 便于处理。"""
    data = Path(path).read_bytes()
    eol = '\r\n' if b'\r\n' in data else '\n'
    return data.decode('utf-8').replace('\r\n', '\n'), eol


def write_text(path, text: str, eol: str) -> None:
    """按**原始行尾**写回（二进制模式，绕开文本模式的转换）。"""
    out = text.replace('\n', eol) if eol != '\n' else text
    Path(path).write_bytes(out.encode('utf-8'))


def patch(path, pairs, count: int = 1) -> None:
    """逐对替换 (旧, 新)，**断言每对恰好匹配 count 次**。

    ⚠️ 匹配数不符就抛错 —— 不静默跳过、也不静默全替换。
    这是刻意的：宁可脚本失败重写，也不要「以为改了其实没改」
    或「只想改一处结果改了两处」。

    `pairs` 可以是单个 (旧, 新) 元组，也可以是列表。
    """
    if isinstance(pairs, tuple) and len(pairs) == 2 and isinstance(pairs[0], str):
        pairs = [pairs]

    text, eol = read_text(path)
    for old, new in pairs:
        n = text.count(old)
        if n != count:
            raise AssertionError(
                f'{path}: 锚点匹配 {n} 次（期望 {count} 次）\n'
                f'--- 锚点片段 ---\n{old[:400]}\n---'
            )
        text = text.replace(old, new, count)
    write_text(path, text, eol)


def check_eol(path) -> str:
    """看文件当前行尾 —— 打补丁**前后**各查一次。"""
    return 'CRLF' if b'\r\n' in Path(path).read_bytes() else 'LF'


def _selftest() -> int:
    """自测：覆盖踩过的两个真实场景 + 边界。"""
    import tempfile
    fails = []

    def check(name, cond, detail=''):
        print(f"  {'✓' if cond else '✗'} {name}" + (f"  {detail}" if detail else ''))
        if not cond:
            fails.append(name)

    with tempfile.TemporaryDirectory() as td:
        d = Path(td)

        # ① CRLF 文件改完仍是 CRLF（核心）
        f = d / 'a.py'; f.write_bytes(b'l1\r\nl2\r\nl3\r\n')
        patch(str(f), ('l2', 'L2'))
        check('CRLF 保持', f.read_bytes() == b'l1\r\nL2\r\nl3\r\n', repr(f.read_bytes()))

        # ② LF 文件别被反向污染
        f = d / 'b.py'; f.write_bytes(b'a\nb\n')
        patch(str(f), ('b', 'B'))
        check('LF 保持', f.read_bytes() == b'a\nB\n', repr(f.read_bytes()))

        # ③ 锚点 0 次 → 抛错（不许静默不改）
        f = d / 'c.py'; f.write_bytes(b'x\n')
        try:
            patch(str(f), ('NOT_THERE', 'y')); check('0 次抛错', False)
        except AssertionError as e:
            check('0 次抛错', '匹配 0 次' in str(e))

        # ④ 锚点 2 次但期望 1 次 → 抛错（delivered_at 那个事故）
        f = d / 'e.py'; f.write_bytes(b'col = C()\nz\ncol = C()\n')
        try:
            patch(str(f), ('col = C()', 'col = C(1)')); check('重复锚点抛错', False)
        except AssertionError as e:
            check('重复锚点抛错', '匹配 2 次' in str(e))

        # ⑤ 明确 count=2 则通过
        patch(str(f), ('col = C()', 'col = C(1)'), count=2)
        check('count=2 通过', f.read_bytes().count(b'C(1)') == 2)

        # ⑥ 多对锚点
        f = d / 'f.py'; f.write_bytes(b'a\r\nb\r\nc\r\n')
        patch(str(f), [('a', 'A'), ('c', 'C')])
        check('多对替换', f.read_bytes() == b'A\r\nb\r\nC\r\n')

        # ⑦ 单对元组写法
        f = d / 'g.py'; f.write_bytes(b'x\n')
        patch(str(f), ('x', 'y'))
        check('单对元组', f.read_bytes() == b'y\n')

        # ⑧ 中文不乱码
        f = d / 'h.py'; f.write_bytes('礼物 · ¥800\n'.encode())
        patch(str(f), ('礼物', '礼品'))
        check('中文正常', '礼品 · ¥800' in f.read_text(encoding='utf-8'))

        # ⑨ check_eol
        f = d / 'i.py'; f.write_bytes(b'x\r\n')
        check('check_eol 识别 CRLF', check_eol(str(f)) == 'CRLF')

    print()
    if fails:
        print('失败:', fails)
        return 1
    print('全部通过')
    return 0


def main(argv) -> int:
    if argv and argv[0] == 'check':
        if len(argv) < 2:
            print('用法: python scripts/patchlib.py check <file> [...]'); return 1
        for f in argv[1:]:
            print(f'{check_eol(f):5s} {f}')
        return 0
    if argv and argv[0] == 'selftest':
        return _selftest()
    print(__doc__)
    return 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
