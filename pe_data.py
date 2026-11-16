#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""抓取指数估值（PE / PB / PE 历史分位），输出 pe_data.js（供 index.html 估值风险条加载）。

用法：python pe_data.py   （scrape.py 每日运行时也会自动调用本模块）
数据源：蛋卷基金指数估值 API（danjuanfunds.com/djapi/index_eva/dj），国内直连、
无需鉴权，一次返回全部指数的估值快照。口径（蛋卷说明）：
  pe / pb = 指数成分股整体市盈率 / 市净率（TTM，市值加权）；
  pe_percentile = 当前 PE 在历史数据中的百分位（0~1，蛋卷按近 10 年口径统计）。
已收录纳指100（NDX）与标普500（SP500）。展示层用「分位」而非 PE 绝对值定风险档，
因为不同指数的盈利结构不同，PE 绝对值之间不可直接比较。

抓取失败时回退复用旧的 pe_data.js，保证页面有数可显。
"""
import urllib.request
import json
import re
import time
import datetime
import os

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
API = "https://danjuanfunds.com/djapi/index_eva/dj"
# 蛋卷 index_code → 主页指数键（与行情卡、K线块的 index 键一致）
INDEXES = {"NDX": "纳指100", "SP500": "标普500"}
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pe_data.js")
BJT = datetime.timezone(datetime.timedelta(hours=8))


def fetch():
    """请求蛋卷指数估值。返回 items 列表；失败返回 []。"""
    req = urllib.request.Request(
        API, headers={"User-Agent": UA, "Referer": "https://danjuanfunds.com/"}
    )
    data = None
    for attempt in range(3):
        try:
            data = json.loads(urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace"))
            break
        except Exception as e:  # noqa
            if attempt == 2:
                print(f"  [警告] 指数估值抓取失败: {e}")
                return []
            time.sleep(1)
    return (data.get("data") or {}).get("items") or []


def load_old():
    """读取旧的 pe_data.js。返回旧 PE_DATA dict，缺失/损坏为 None。"""
    if not os.path.exists(OUT):
        return None
    try:
        with open(OUT, encoding="utf-8") as f:
            src = f.read()
        m = re.search(r"window\.PE_DATA\s*=\s*(\{.*\})\s*;", src)
        return json.loads(m.group(1)) if m else None
    except Exception:
        return None


def _num(v):
    try:
        f = float(v)
        return f
    except (TypeError, ValueError):
        return None


def main():
    items = fetch()
    old = load_old()
    today = datetime.datetime.now(BJT).strftime("%Y-%m-%d")

    out = {}
    by_code = {it.get("index_code"): it for it in items if it.get("index_code")}
    for code, name in INDEXES.items():
        it = by_code.get(code) or {}
        pe = _num(it.get("pe"))
        if pe is None:
            continue
        ts = it.get("ts")
        try:
            updated = datetime.datetime.fromtimestamp(ts / 1000, BJT).strftime("%Y-%m-%d") if ts else today
        except Exception:
            updated = today
        pct = _num(it.get("pe_percentile"))
        out[name] = {
            "name": name,
            "pe": round(pe, 2),
            "pb": round(_num(it.get("pb")), 2) if _num(it.get("pb")) is not None else None,
            "pct": round(pct * 100, 1) if pct is not None else None,  # 近10年PE分位 %
            "updated": updated,
        }
        time.sleep(0.2)

    # 兜底：当日缺失的指数沿用旧 pe_data.js 的数值，避免卡片消失
    for name in INDEXES.values():
        if name not in out and old and name in old:
            out[name] = old[name]
            print(f"  [兜底] {name} 估值抓取失败，沿用旧数据（{old[name].get('updated')}）")

    if not out:
        print("  [警告] 指数估值全部抓取失败且无旧数据，保留旧的 pe_data.js")
        return

    payload = json.dumps(out, ensure_ascii=False, separators=(",", ":"))
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("window.PE_DATA = " + payload + ";\n")
    for name, v in out.items():
        p = v["pct"]
        tail = f"近10年 PE 分位 {p}%" if p is not None else "分位暂无"
        print(f"  {name}: PE {v['pe']} · {tail} · {v['updated']}")
    print("已写入", OUT)


if __name__ == "__main__":
    main()
