#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""抓取纳指100/标普500 全部日K数据，输出 kline_data.js（供 kline.html 加载）。

用法：python kline_data.py
数据源：腾讯行情 web.ifzq.gtimg.cn（us.NDX / us.INX）
字段：腾讯日K顺序为 [日期, 开盘, 收盘, 最高, 最低, 成交量]
说明：单次最多返回约 2000 根，故按日期倒序分页抓取，拼成「自成立以来」的完整序列。
"""
import urllib.request
import json
import time
import os

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
SYMBOLS = {"纳指100": "us.NDX", "标普500": "us.INX"}
CHUNK = 2000  # 单次抓取根数（接口上限约 2000）
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kline_data.js")


def fetch_all_kline(symbol):
    """分页抓取全部日K（自上市以来），返回按日期升序的 rows 列表。"""
    batches = []
    end = "2050-01-01"
    while True:
        url = (
            "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
            f"?param={symbol},day,1970-01-01,{end},{CHUNK},qfq"
        )
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": "https://gu.qq.com/"})
        try:
            data = json.loads(urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace"))
        except Exception as e:  # noqa
            print(f"  [警告] {symbol} 分页失败: {e}")
            break
        day = (data.get("data") or {}).get(symbol, {}).get("day") or []
        if not day:
            break
        batches.append(day)
        if len(day) < CHUNK:
            break  # 已到最早
        end = day[0][0]  # 下一批往前翻
        time.sleep(0.3)

    # 最老批次在前，合并并按日期去重（分页边界会重叠一天）
    rows = []
    seen = set()
    for batch in reversed(batches):
        for r in batch:
            if len(r) < 6 or r[0] in seen:
                continue
            seen.add(r[0])
            try:
                rows.append({
                    "d": r[0],
                    "o": float(r[1]),
                    "c": float(r[2]),
                    "h": float(r[3]),
                    "l": float(r[4]),
                    "v": float(r[5]),
                })
            except (ValueError, TypeError):
                continue
    return rows


def main():
    out = {}
    for name, sym in SYMBOLS.items():
        rows = fetch_all_kline(sym)
        out[name] = rows
        if rows:
            print(f"{name} ({sym}): {len(rows)} 根日K，{rows[0]['d']} ~ {rows[-1]['d']}")

    payload = json.dumps(out, ensure_ascii=False, separators=(",", ":"))
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("window.KLINE_DATA = " + payload + ";\n")
    print("已写入", OUT)


if __name__ == "__main__":
    main()
