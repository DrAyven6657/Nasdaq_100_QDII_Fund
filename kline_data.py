#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""抓取纳指100/标普500 全部日K数据，输出 kline_data.js（供 index.html / kline.html 加载）。

用法：python kline_data.py   （scrape.py 每日运行时也会自动调用本模块）
数据源：东方财富 push2his（100.NDX100 / 100.SPX / 105.QQQ），国内直连，一次请求返回全部历史日K。
注意：东财的 100.NDX 是纳斯达克综合指数（COMP），不是纳指100，点位和涨跌都不同。

纳指100 历史拼接说明：
  东财的纳斯达克100 指数（100.NDX100）只收录 2019-04-08 之后的行情，更早的真实指数
  日线在国内免费直连源中拿不到。因此用 Invesco QQQ（跟踪纳指100 的旗舰 ETF，
  secid=105.QQQ，东财 2001-01-02 起）的前复权日K，按「接缝比例折算」拼接到指数序列
  前面，把趋势图回溯到 2001 年：
    scale = 指数首日开盘价 / QQQ 前末日收盘价，前段开高低收同乘 scale，
    接缝处「QQQ 末日折算收盘 == 指数首日开盘」，序列连续无跳变；
    成交量沿用 QQQ 原始值（口径不同，仅作趋势参考）。
  前缀是静态历史，拼接每天全量重建（仅多一次 QQQ 请求）；若 QQQ 抓取失败，
  回退用旧文件中的拼接前缀衔接当天新抓的指数段，保证日常更新不中断。
"""
import urllib.request
import json
import re
import time
import os

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
# 东财 secid：100.NDX100=纳斯达克100，100.SPX=标普500，105.QQQ=Invesco 纳指100 ETF（拼接用）
SYMBOLS = {"纳指100": "100.NDX100", "标普500": "100.SPX"}
QQQ_SECID = "105.QQQ"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kline_data.js")


def fetch_kline(secid):
    """从东财 K 线接口抓取全部日K，返回按日期升序的 rows 列表；失败返回 []。"""
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


def load_old():
    """读取旧的 kline_data.js。返回 (旧KLINE_DATA dict, 旧SPLICE_META dict)，缺失为 None。"""
    if not os.path.exists(OUT):
        return None, None
    try:
        with open(OUT, encoding="utf-8") as f:
            src = f.read()
        old = meta = None
        m = re.search(r"window\.KLINE_DATA\s*=\s*(\{.*\})\s*;", src)
        if m:
            old = json.loads(m.group(1))
        m = re.search(r"window\.KLINE_SPLICE_META\s*=\s*(\{.*\})\s*;", src)
        if m:
            meta = json.loads(m.group(1))
        return old, meta
    except Exception:
        return None, None


def scale_qqq_prefix(prefix, ndx_open):
    """把 QQQ 前缀按接缝比例折算：scale = 指数首日开盘 / QQQ 末日收盘。"""
    scale = ndx_open / prefix[-1]["c"]
    scaled = [
        {
            "d": r["d"],
            "o": round(r["o"] * scale, 2),
            "c": round(r["c"] * scale, 2),
            "h": round(r["h"] * scale, 2),
            "l": round(r["l"] * scale, 2),
            "v": r["v"],
        }
        for r in prefix
    ]
    return scale, scaled


def make_meta(prefix_rows, seam, scale):
    return {
        "seam": seam,
        "scale": round(scale, 6),
        "prefix": {"count": len(prefix_rows), "start": prefix_rows[0]["d"], "end": prefix_rows[-1]["d"]},
    }


def build():
    """抓取并生成全部日K。返回 (out, meta)：out 供 KLINE_DATA，meta 为拼接信息（可为 None）。"""
    old, old_meta = load_old()
    out = {}

    # ---- 标普500：东财全量真实指数（1986 年起）；抓取失败沿用旧数据 ----
    spx = fetch_kline(SYMBOLS["标普500"])
    if not spx and old and old.get("标普500"):
        spx = old["标普500"]
        print("  [兜底] 标普500 抓取失败，沿用旧的指数日K")
    out["标普500"] = spx
    time.sleep(0.3)

    # ---- 纳指100：真实指数（2019-04 起）+ QQQ 折算前缀拼接（2001 年起）----
    ndx = fetch_kline(SYMBOLS["纳指100"])
    time.sleep(0.3)
    meta = old_meta if not ndx else None
    if ndx:
        seam = ndx[0]["d"]
        qqq = fetch_kline(QQQ_SECID)
        prefix = [r for r in qqq if r["d"] < seam]
        if prefix:
            scale, scaled = scale_qqq_prefix(prefix, ndx[0]["o"])
            if abs(scaled[-1]["c"] - ndx[0]["o"]) > 0.01:  # 接缝必须相等，防御性检查
                print("  [警告] 拼接接缝出现跳变，请检查数据质量")
            out["纳指100"] = scaled + ndx
            meta = make_meta(scaled, seam, scale)
            print(
                f"  拼接接缝 {seam}：前段 {len(scaled)} 根 QQQ 折算"
                f" [{scaled[0]['d']} ~ {scaled[-1]['d']}]，比例 {round(scale, 6)}"
            )
        else:
            # QQQ 抓取失败：回退用旧文件中的拼接前缀（已折算，口径与指数段天然衔接）
            old_prefix = [r for r in (old or {}).get("纳指100", []) if r["d"] < seam]
            if old_prefix:
                out["纳指100"] = old_prefix + ndx
                meta = make_meta(old_prefix, seam, ndx[0]["o"] / old_prefix[-1]["c"])
                print(
                    f"  [兜底] QQQ 历史抓取失败，沿用旧拼接前缀 {len(old_prefix)} 根"
                    f" [{old_prefix[0]['d']} ~ {old_prefix[-1]['d']}]"
                )
            else:
                out["纳指100"] = ndx
                print("  [警告] 无 QQQ 拼接前缀（QQQ 抓取失败且无旧数据），纳指100 使用 2019 年起原始序列")
    elif old and old.get("纳指100"):
        # 指数本体抓取失败：整段沿用旧数据（保持原拼接状态与接缝口径）
        out["纳指100"] = old["纳指100"]
        print("  [兜底] 纳指100 抓取失败，沿用旧的指数日K")
    else:
        out["纳指100"] = []

    return out, meta


def main():
    out, meta = build()
    if not any(out.values()):
        print("  [警告] 指数日K全部抓取失败且无旧数据，保留旧的 kline_data.js")
        return
    payload = json.dumps(out, ensure_ascii=False, separators=(",", ":"))
    meta_payload = json.dumps(meta, ensure_ascii=False, separators=(",", ":")) if meta else "null"
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("window.KLINE_DATA = " + payload + ";\n")
        f.write("window.KLINE_SPLICE_META = " + meta_payload + ";\n")
    for name, rows in out.items():
        if rows:
            print(f"  {name}: {len(rows)} 根日K，{rows[0]['d']} ~ {rows[-1]['d']}")
    print("已写入", OUT)


if __name__ == "__main__":
    main()
