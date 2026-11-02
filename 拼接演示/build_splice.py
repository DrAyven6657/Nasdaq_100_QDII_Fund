#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成「纳指100 拼接历史」演示数据。

东财对纳指100 指数（100.NDX100）仅收录 2019-04-08 之后的行情；本脚本把
Invesco QQQ 纳指100ETF（105.QQQ，东财收录自 2001-01-02，前复权）2019-04-08
之前的日线按接缝比例归一，拼接到指数序列前面，形成 2001 年起的长期趋势序列。

- 拼接在构建时一次性完成：前段历史是静态数据，日常更新仍只追加纳指100 新K线。
- 输出：拼接演示/kline_splice_data.js（window.KLINE_DATA + 拼接元信息）
用法：python build_splice.py
"""
import urllib.request
import json
import os

BASE = os.path.dirname(os.path.abspath(__file__))          # 拼接演示/
ROOT = os.path.dirname(BASE)                                # 仓库根
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"


def fetch(url, referer):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": referer})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("utf-8", "replace")


def em_klines(secid):
    url = ("https://push2his.eastmoney.com/api/qt/stock/kline/get"
           f"?secid={secid}&fields1=f1,f2,f3,f4,f5,f6"
           "&fields2=f51,f52,f53,f54,f55,f56&klt=101&fqt=1&beg=0&end=20500101")
    d = json.loads(fetch(url, "https://quote.eastmoney.com/"))
    rows = []
    for line in (d.get("data") or {}).get("klines") or []:
        f = line.split(",")
        if len(f) < 6:
            continue
        rows.append({
            "d": f[0],
            "o": round(float(f[1]), 2),
            "c": round(float(f[2]), 2),
            "h": round(float(f[3]), 2),
            "l": round(float(f[4]), 2),
            "v": float(f[5]),
        })
    return rows


def main():
    # 1) 官方基准：直接读现有 kline_data.js，保证与正式页面数据完全同源
    src = open(os.path.join(ROOT, "kline_data.js"), encoding="utf-8").read()
    base = json.loads(src.split("=", 1)[1].strip().rstrip(";"))
    ndx = base["纳指100"]
    spx = base["标普500"]

    # 2) QQQ 前复权全历史（东财，一次请求全量）
    qqq = em_klines("105.QQQ")
    seam_d = ndx[0]["d"]                       # 2019-04-08
    prefix = [r for r in qqq if r["d"] < seam_d]
    if not prefix:
        raise SystemExit("QQQ 前段数据为空，无法拼接")

    # 3) 比例归一：前段整体乘 scale，使左端最后一日收盘 = 指数首日开盘（接缝无跳变）
    scale = ndx[0]["o"] / prefix[-1]["c"]
    scaled = [{
        "d": r["d"],
        "o": round(r["o"] * scale, 2),
        "c": round(r["c"] * scale, 2),
        "h": round(r["h"] * scale, 2),
        "l": round(r["l"] * scale, 2),
        "v": r["v"],
    } for r in prefix]
    spliced = scaled + ndx

    # 4) 接缝±30 根内相邻日最大波动（数值上验证拼接处不产生异常跳变）
    i = len(scaled)
    span = spliced[max(1, i - 30): min(len(spliced), i + 30)]
    max_jump = max(abs(span[j]["c"] / span[j - 1]["c"] - 1) * 100 for j in range(1, len(span)))

    out = {"纳指100拼接": spliced, "纳指100原始": ndx, "标普500": spx}
    with open(os.path.join(BASE, "kline_splice_data.js"), "w", encoding="utf-8") as f:
        f.write("window.KLINE_DATA = " + json.dumps(out, ensure_ascii=False, separators=(",", ":")) + ";\n")
        f.write("window.KLINE_SPLICE_META = " + json.dumps({
            "seam": seam_d,
            "scale": scale,
            "prefix": {"count": len(scaled), "start": scaled[0]["d"], "end": scaled[-1]["d"]},
            "max_jump_pct": round(max_jump, 2),
        }, ensure_ascii=False) + ";\n")

    print(f"折算比例 scale = {scale:.6f}（QQQ 末日收盘 {prefix[-1]['c']} × scale = 指数首日开盘 {ndx[0]['o']}）")
    print(f"拼接序列：{len(scaled)} 根 QQQ [{scaled[0]['d']} ~ {scaled[-1]['d']}] + {len(ndx)} 根指数 [{ndx[0]['d']} ~ {ndx[-1]['d']}] = 共 {len(spliced)} 根")
    print(f"接缝检查：{seam_d} 左端收盘 {scaled[-1]['c']} = 右端开盘 {ndx[0]['o']}，无跳变；±30 根内最大相邻日波动 {max_jump:.2f}%")
    print("已写入", os.path.join(BASE, "kline_splice_data.js"))


if __name__ == "__main__":
    main()
