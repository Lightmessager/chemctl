"""CLI banner and hidden commands. Nothing here touches the API, files or any scientific data."""
import random
import time
from datetime import datetime

import typer
from rich.console import Console
from rich.text import Text

from . import __version__

console = Console()

LOGO = r"""
      _______
     /       \
    /  .---.  \      chemctl {version}
    \  `---'  /      local computational chemistry workbench
     \_______/
"""

HINTS = ["coffee", "cat", "scf", "mole", "fortune", "42"]

FORTUNES = [
    "只有一个虚频，不代表你找对了过渡态。",
    "先看最后一行有没有 TERMINATED NORMALLY，再看能量。",
    "基组越大，头发越少。",
    "B3LYP 不是答案，但它常常是问题。",
    "周五下午不要提交任务。",
    "收敛的才叫结果，其余都是日志。",
    "不同方法 / 基组的能量不能比，就像不能拿 Eh 和工资比。",
    "把 Eh 换成 kcal/mol 之前，先确认符号没错。",
    "初始结构是你给的，锅也是。",
    "SCF 不收敛的时候，深呼吸，然后加 SlowConv。",
    "partial 不是 failed，但也别当成 parsed。",
    "调度器还没确认之前，qsub 只是一个五个字母的单词。",
]


def gradient(text, start=(45, 212, 191), end=(139, 92, 246)):
    lines, out = text.strip("\n").split("\n"), Text()
    for index, line in enumerate(lines):
        mix = index / max(1, len(lines) - 1)
        color = "#%02x%02x%02x" % tuple(round(a + (b - a) * mix) for a, b in zip(start, end))
        out.append(line + "\n", style=f"bold {color}")
    return out


def banner():
    now = datetime.now()
    console.print(gradient(LOGO.format(version=__version__)))
    if (now.month, now.day) == (10, 23):
        console.print("  6.02214076 x 10^23 —— Mole Day 快乐。", style="bold yellow")
    elif now.weekday() == 4 and now.hour >= 14:
        console.print("  今天是周五下午：提交任务前三思。", style="yellow")
    elif now.hour < 5:
        console.print("  这个点还在算？去睡吧，任务不会跑掉（本版本它根本不会跑）。", style="yellow")
    if random.random() < 0.34:
        console.print(f"  psst… 试试 chemctl {random.choice(HINTS)}", style="dim")


def register(app):
    @app.command(hidden=True)
    def coffee():
        """C8H10N4O2."""
        console.print(gradient(r"""
         ) )  )
        ( (  (
      .---------.
      |         |=.
      |  C8H10  | |
      |   N4O2  |='
       \_______/
""", (240, 179, 84), (244, 124, 124)))
        console.print("  咖啡因 · C8H10N4O2 · 194.19 g/mol", style="bold")
        console.print("  计算化学里最重要的试剂。提交任务前，请确认体内浓度已收敛。", style="dim")

    @app.command(hidden=True)
    def cat():
        """Open the box."""
        alive = random.random() < 0.5
        console.print(gradient(r"""
      /\_/\
     ( %s )
      > ^ <
""" % ("o.o" if alive else "x.x")))
        console.print(f"  波函数已坍缩：{'|alive>' if alive else '|dead>'}。观测者：你。", style="bold green" if alive else "bold red")
        console.print("  再运行一次会得到另一个宇宙。", style="dim")

    @app.command(hidden=True)
    def scf():
        """Pretend to converge."""
        console.print("  [彩蛋] 假装收敛：以下数字全部随机生成，没有执行任何量子化学计算。\n", style="bold yellow")
        console.print(f"  {'ITER':>4}   {'Energy (not real)':>18}   {'Delta-E':>12}   {'DIIS':>10}", style="bold", highlight=False)
        energy, delta = -random.uniform(70, 400), random.uniform(0.5, 2)
        doomed = random.random() < 0.08
        for cycle in range(1, 13):
            delta *= random.uniform(0.9, 1.6) if doomed else random.uniform(0.08, 0.3)
            energy -= delta
            style = "red" if doomed else "green" if delta < 1e-6 else "cyan"
            console.print(f"  {cycle:4d}   {energy:18.10f}   {delta:12.3e}   {delta * 3.7:10.3e}", style=style, highlight=False)
            time.sleep(0.12)
        if doomed:
            console.print("\n  SCF NOT CONVERGED AFTER 12 CYCLES —— 经典。试试 SlowConv，或者咖啡（chemctl coffee）。", style="bold red")
        else:
            console.print("\n  **** SCF CONVERGED (in spirit) ****   没有电子在本次演示中受到伤害。", style="bold green")

    @app.command(hidden=True)
    def mole():
        """N_A."""
        console.print(gradient(r"""
        .-''''-.
       /  o  o  \
      |    __    |
       \  `--'  /
     ,-'`------'`-.
""", (139, 92, 246), (56, 189, 248)))
        console.print("  1 mol = 6.02214076 x 10^23 个。这只鼹鼠只算 1 个。", style="bold")
        console.print("  每年 10 月 23 日 6:02 是 Mole Day。", style="dim")

    @app.command(hidden=True)
    def fortune():
        """A proverb."""
        console.print("\n  " + random.choice(FORTUNES) + "\n", style="italic cyan")

    @app.command("42", hidden=True)
    def answer():
        """The answer."""
        console.print("\n  42", style="bold magenta")
        console.print("  单位未注明，方法 / 基组未知，来源行号缺失 —— 因此不可与任何结果比较。\n", style="dim")
