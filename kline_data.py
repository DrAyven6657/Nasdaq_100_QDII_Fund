#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""抓取纳指100/标普500 全部日K数据，输出 kline_data.js（供 kline.html 加载）。

用法：python kline_data.py
数据源：东方财富 push2his（100.NDX100 / 100.SPX），国内直连，一次请求返回全部历史日K。
注意：东财的 100.NDX 是纳斯达克综合指数（COMP），不是纳指100，点位和涨跌都不同。
字段：输出 [日期, 开盘, 收盘, 最高, 最低, 成交量] 对应的 dict 序列，与 kline.html 兼容。
"""
import urllib.request
import json
import time
import os

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
# 东财 secid：100.NDX100=纳斯达克100，100.SPX=标普500
SYMBOLS = {"纳指100": "100.NDX100", "标普500": "100.SPX"}
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kline_data.js")


def fetch_kline(secid):
    """从东财 K 线接口抓取全部日K，返回按日期升序的 rows 列表。"""
    url = (
        "https://push2his.eastmoney.com/api/qt/stock/kline/get"
        f"?secid={secid}&fields1=f1,f2,f3,f4,f5,f6"
        "&fields2=f51,f52,f53,f54,f55,f56&klt=101&fqt=1&beg=0&end=20500101"
    )
    req = urllib.request.Request(
        url, headers={"User-Agent": UA, "Referer": "https://quote.eastmoney.com/"}
    )
    data = None
    for attempt in range(3):
        try:
            data = json.loads(urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace"))
            break
        except Exception as e:  # noqa
            if attempt == 2:
                print(f"  [警告] {secid} 抓取失败: {e}")
                return []
            time.sleep(1)

    rows = []
    for line in (data.get("data") or {}).get("klines") or []:
        f = line.split(",")
        if len(f) < 6:
            continue
        try:
            rows.append({
                "d": f[0],
                "o": round(float(f[1]), 2),
                "c": round(float(f[2]), 2),
                "h": round(float(f[3]), 2),
                "l": round(float(f[4]), 2),
                "v": float(f[5]),
            })
        except ValueError:
            continue
    return rows


def main():
    out = {}
    for name, secid in SYMBOLS.items():
        rows = fetch_kline(secid)
        out[name] = rows
        if rows:
            print(f"{name} ({secid}): {len(rows)} 根日K，{rows[0]['d']} ~ {rows[-1]['d']}")
        time.sleep(0.3)

    payload = json.dumps(out, ensure_ascii=False, separators=(",", ":"))
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("window.KLINE_DATA = " + payload + ";\n")
    print("已写入", OUT)


if __name__ == "__main__":
    main()