#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""抓取纳指100/标普500 全部日K数据，输出 kline_data.js（供 kline.html 加载）。

用法：python kline_data.py
数据源：雅虎财经 chart API（^NDX / ^GSPC）
字段：输出 [日期, 开盘, 收盘, 最高, 最低, 成交量] 对应的 dict 序列，与 kline.html 兼容。
说明：雅虎可回溯到指数发布之初——纳指100 自 1985-10-01 起，标普500 自 1970-01-02 起。
      （旧方案用腾讯 us.NDX 只能回溯到 2000 年，故换用雅虎补齐历史。）
"""
import urllib.request
import json
import time
import os
import datetime

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
# 雅虎代码：^NDX=纳斯达克100，^GSPC=标普500
SYMBOLS = {"纳指100": "%5ENDX", "标普500": "%5EGSPC"}
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kline_data.js")


def fetch_yahoo_kline(symbol_code):
    """从雅虎 chart API 抓取全部日K（自发布以来），返回按日期升序的 rows 列表。"""
    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/"
        f"{symbol_code}?period1=0&period2=9999999999&interval=1d"
    )
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for attempt in range(3):
        try:
            data = json.loads(urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace"))
            break
        except Exception as e:  # noqa
            if attempt == 2:
                print(f"  [警告] {symbol_code} 抓取失败: {e}")
                return []
            time.sleep(1)

    result = (data.get("chart") or {}).get("result") or []
    if not result:
        return []
    r = result[0]
    ts = r.get("timestamp") or []
    quote = (r.get("indicators") or {}).get("quote") or [{}]
    q = quote[0]
    o = q.get("open") or []
    c = q.get("close") or []
    h = q.get("high") or []
    l = q.get("low") or []
    v = q.get("volume") or []

    rows = []
    for i, t in enumerate(ts):
        # 跳过停牌/无成交的无效日（收盘为 None）
        if c[i] is None:
            continue
        d = datetime.datetime.fromtimestamp(t, datetime.timezone.utc).strftime("%Y-%m-%d")
        rows.append({
            "d": d,
            "o": round(float(o[i]), 2) if o[i] is not None else None,
            "c": round(float(c[i]), 2),
            "h": round(float(h[i]), 2) if h[i] is not None else None,
            "l": round(float(l[i]), 2) if l[i] is not None else None,
            "v": float(v[i]) if v[i] is not None else 0.0,
        })
    return rows


def main():
    out = {}
    for name, sym in SYMBOLS.items():
        rows = fetch_yahoo_kline(sym)
        out[name] = rows
        if rows:
            print(f"{name} ({sym}): {len(rows)} 根日K，{rows[0]['d']} ~ {rows[-1]['d']}")
        time.sleep(0.5)

    payload = json.dumps(out, ensure_ascii=False, separators=(",", ":"))
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("window.KLINE_DATA = " + payload + ";\n")
    print("已写入", OUT)


if __name__ == "__main__":
    main()
