"""
终端指数盯盘工具
数据源：新浪财经公开接口
零额外依赖（仅需 rich，urllib 内置）
5 秒自动刷新，Ctrl+C 退出
"""

import urllib.request
import time
from datetime import datetime

from rich.live import Live
from rich.layout import Layout
from rich.table import Table
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich import box

# ─── 指数配置 ────────────────────────────────────────────────────
# (标签, 新浪代码, 所属市场)
INDEX_LIST = [
    ("上证指数", "s_sh000001", "A股"),
    ("深证成指", "s_sz399001", "A股"),
    ("沪深300", "s_sh000300", "A股"),
    ("中证500", "s_sh000905", "A股"),
    ("标普500", "gb_$inx", "美股"),
    ("纳斯达克100", "gb_$ndx", "美股"),
    ("纳斯达克综指", "gb_$ixic", "美股"),
    ("道琼斯", "gb_$dji", "美股"),
]

SINA_API = "http://hq.sinajs.cn/list={codes}"


def fetch_all():
    """
    拉取所有指数数据。
    新浪 A 股指数格式:  名称, 当前价, 涨跌额, 涨跌幅%, 成交量, 成交额
    新浪美股指数格式:    名称, 当前价, 涨跌幅%, 时间, 涨跌额, ...
    """
    codes = ",".join(c for _, c, _ in INDEX_LIST)
    url = SINA_API.format(codes=codes)
    req = urllib.request.Request(url, headers={"Referer": "https://finance.sina.com.cn"})

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("gbk")
    except Exception as e:
        return {"error": f"网络请求失败: {e}"}

    results = {}
    for line in raw.strip().split("\n"):
        if "=" not in line:
            continue
        code_part, values_part = line.split('="', 1)
        code = code_part.split("hq_str_")[-1]
        values = values_part.rstrip('";').split(",")
        if len(values) < 4:
            continue

        name = values[0]
        if code.startswith("gb_"):
            # 美股格式: 名称, 当前价, 涨跌幅%, 时间, 涨跌额
            try:
                price = float(values[1])
                change_pct = float(values[2])
                change = float(values[4])
            except (ValueError, IndexError):
                continue
        else:
            # A 股格式: 名称, 当前价, 涨跌额, 涨跌幅%
            try:
                price = float(values[1])
                change = float(values[2])
                change_pct = float(values[3])
            except (ValueError, IndexError):
                continue

        results[code] = {
            "name": name,
            "price": price,
            "change": change,
            "change_pct": change_pct,
        }

    return results


def build_layout(data):
    """根据数据构建 Rich 布局"""
    now = datetime.now()

    # 判断交易状态
    h, m = now.hour, now.minute
    a_stock_open = (9 <= h < 15) or (h == 9 and m >= 15)
    us_open = (h >= 21 or h < 5)

    a_tag = "[green]● 交易中[/green]" if a_stock_open else "[dim]○ 未开盘[/dim]"
    us_tag = "[green]● 交易中[/green]" if us_open else "[dim]○ 未开盘[/dim]"

    # ── 标题栏 ──
    header = Panel(
        Text.from_markup(
            f"[bold white]指数盯盘[/bold white]  {now.strftime('%H:%M:%S')}  "
            f"| 5s刷新  |  A股 {a_tag}  |  美股 {us_tag}"
        ),
        box=box.ROUNDED,
    )

    # ── 数据表格 ──
    if isinstance(data, dict) and "error" in data:
        body = Panel(f"[red]获取数据失败: {data['error']}[/red]",
                     title="错误", border_style="red")
        return _make_root(header, body, Panel(""))

    table = Table(box=box.SIMPLE_HEAVY, expand=True, padding=(0, 2))
    table.add_column("指数", style="bold cyan", width=12)
    table.add_column("最新价", justify="right", width=14)
    table.add_column("涨跌额", justify="right", width=14)
    table.add_column("涨跌幅", justify="right", width=14)

    # 按市场分组显示
    for market, _ in [("A股", ""), ("美股", "")]:
        for label, code, mkt in INDEX_LIST:
            if mkt != market:
                continue
            info = data.get(code)
            if info is None:
                table.add_row(label, "—", "—", "—")
                continue
            price = info["price"]
            change = info["change"]
            change_pct = info["change_pct"]
            color = "red" if change_pct < 0 else "green" if change_pct > 0 else "white"
            arrow = "▲" if change_pct > 0 else "▼" if change_pct < 0 else "—"
            table.add_row(
                label,
                f"{price:,.2f}",
                f"[{color}]{change:+,.2f}[/{color}]",
                f"[{color}]{arrow} {change_pct:+,.2f}%[/{color}]",
            )
        # 市场间加空行
        if market == "A股":
            table.add_row("", "", "", "")

    body = Panel(table, title="实时指数", border_style="blue")

    # ── 底部 ──
    footer = Panel(
        Text.from_markup(
            "数据源: 新浪财经  |  [dim]Ctrl+C 退出[/dim]  |  "
            f"更新于 {now.strftime('%H:%M:%S')}"
        ),
        box=box.ROUNDED,
    )

    return _make_root(header, body, footer)


def _make_root(header, body, footer):
    """组装三个区域的 Layout"""
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="body"),
        Layout(name="footer", size=3),
    )
    layout["header"].update(header)
    layout["body"].update(body)
    layout["footer"].update(footer)
    return layout


def main():
    console = Console()
    console.clear()

    # 首次加载
    data = fetch_all()
    layout = build_layout(data)

    with Live(layout, console=console, refresh_per_second=4, screen=True) as live:
        while True:
            try:
                time.sleep(5)
                data = fetch_all()
                live.update(build_layout(data))
            except KeyboardInterrupt:
                console.print("\n[dim]已退出盯盘。[/dim]")
                break
            except Exception as e:
                live.update(build_layout({"error": str(e)}))


if __name__ == "__main__":
    main()
