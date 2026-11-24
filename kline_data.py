#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""抓取纳指100/标普500/上证指数 全部日K数据，输出 kline_data.js（供 index.html / kline.html 加载）。
另抓取定投模拟用场外基金（dca.html）的全部历史净值，合成分红再投的复权净值写入同一文件。

用法：python kline_data.py   （scrape.py 每日运行时也会自动调用本模块）

数据源（2026-11 主干换新，家里 IP 不再直接碰任何行情站）：
  主渠道  自有 Cloudflare Worker 中转（WORKER 常量，域名更换只改它和 index.html 的 RT_PROXY）
          ——worker 端按 vendor 参数代取：sinaus=新浪美股日K / sina=新浪A股指数日K / eastmoney=东财日K
  兜底链  worker 不可用时本机直连同一三家（新浪不设限；东财若仍封本机 IP 则该兜底自然失效）
  旧数据  单个标的全部失败时沿用旧 kline_data.js 对应序列（原有行为不变）
注意：东财的 100.NDX 是纳斯达克综合指数（COMP），不是纳指100；新浪的 .ndx 才是纳指100
（实测与实时卡片同值：2026-11-23 收 26746.10）。东财 105.QQQ 自 2026-11 起持续 520，
QQQ 前缀改用新浪 qqq 原始价（不复权）。
输出格式：KLINE_DATA 每行为紧凑数组 [日期, 开盘, 收盘, 最高, 最低, 成交量]
（相比对象格式省 ~40% 体积），前端 kline_echarts.js 做归一化，两种格式都能读。

纳指100 历史拼接说明：
  新浪的纳斯达克100 指数（.ndx）收录 2014-02-18 之后，更早的真实指数
  日线在国内免费直连源中拿不到。因此用 Invesco QQQ（跟踪纳指100 的旗舰 ETF）
  的日K，按「接缝比例折算」拼接到指数序列前面，把趋势图回溯到 2001 年：
    scale = 指数首日开盘价 / QQQ 前末日收盘价，前段开高低收同乘 scale，
    接缝处「QQQ 末日折算收盘 == 指数首日开盘」，序列连续无跳变；
    成交量沿用 QQQ 原始值（口径不同，仅作趋势参考）。
  前缀是静态历史：折算一次后冻结为 kline_prefix.json，每日直接复用，不再依赖行情站。
  生成来源依次为：本地/在线 Pages 上的旧完整前缀（东财 QQQ 前复权口径，2001~2014 无缺档，
  首选）→ 旧 kline_data.js → 新浪 qqq（其归档缺 2005~2010 整段，且原东财 105.QQQ 自 2026-11
  起持续 520，仅作最后手段）。各来源均不可用时跳过前缀，纳指100 退为 2014 年起原始序列。
"""
import urllib.request
import json
import re
import time
import os
import datetime

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"

# ── 换域名只改这里 ─────────────────────────────────────────────
# （另一处在 index.html 的 RT_PROXY 常量，两处一起换；scrape.py 的分时抓取复用本常量）
WORKER_HOST = "https://yingman.chitong-indextracking.xyz"
WORKER = WORKER_HOST + "/kline"
# ──────────────────────────────────────────────────────────────
# 本机直连兜底 URL（与 Worker 内部请求同构；新浪不设限，东财对本机 IP 可能仍封锁）
SINA_CN_K = ("https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
             "CN_MarketData.getKLineData?symbol={sym}&scale=240&ma=no&datalen={n}")
SINA_US_K = ("https://stock.finance.sina.com.cn/usstock/api/json_v2.php/"
             "US_MinKService.getDailyK?symbol={sym}&num={n}&page=1")
EM_K = ("https://push2his.eastmoney.com/api/qt/stock/kline/get"
        "?secid={secid}&fields1=f1,f2,f3,f4,f5,f6"
        "&fields2=f51,f52,f53,f54,f55,f56&klt=101&fqt=1&beg=0&end=20500101")
CN_KLINE_MAX = 9000  # 上证全历史 8769 根，9000 足够（新浪该接口实测无上限）

# 真指数/序列本体：(渠道, 代码)；渠道 = sina（新浪A股） / sinaus（新浪美股） / eastmoney
SYMBOLS = {
    "纳指100": ("sinaus", ".ndx"),        # 新浪纳指100（2014-02-18 起）
    "标普500": ("eastmoney", "100.SPX"),  # 东财（1986-03-17 起，前复权）
    "上证指数": ("sina", "sh000001"),     # 新浪（1990-12-19 起）
}
# 纳指100 拼接前缀 ETF：东财 105.QQQ 已持续 520（2026-11 起），改用新浪 qqq 原始价
QQQ_SRC = ("sinaus", "qqq")
# dca.html 定投模拟用场外基金：key 与页脚下拉框 value 对应，value=天天基金代码
DCA_FUNDS = {"红利低波50": "008163"}  # 南方标普中国A股大盘红利低波50ETF联接A
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kline_data.js")
# 纳指100 折算前缀的冻结文件与重建来源（说明见模块 docstring「纳指100 历史拼接说明」）
PREFIX_ARTIFACT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kline_prefix.json")
PAGES_BACKUP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kline_data_pages_backup.js")
PAGES_URL = "https://drayven6657.github.io/Nasdaq_100_QDII_Fund/kline_data.js"


def _parse_kline(vendor, txt):
    """把三种日K响应统一解析为日期升序的 {d,o,c,h,l,v} rows；解析失败返回 []。

    新浪A股：[{day,open,high,low,close,volume}, ...]（字符串值）
    新浪美股：[{d,o,h,l,c,v,a}, ...]
    东财：{data:{klines:["日期,开盘,收盘,最高,最低,成交量", ...]}}
    """
    def _rows(pairs):
        out = []
        for d, o, c, h, l, v in pairs:
            try:
                out.append({
                    "d": d,
                    "o": round(float(o), 2), "c": round(float(c), 2),
                    "h": round(float(h), 2), "l": round(float(l), 2),
                    "v": float(v),
                })
            except (TypeError, ValueError):
                continue
        return out

    try:
        data = json.loads(txt)
    except ValueError:
        return []
    if vendor == "eastmoney":
        lines = (data.get("data") or {}).get("klines") or []
        return _rows(line.split(",")[:6] for line in lines if len(line.split(",")) >= 6)
    arr = data if isinstance(data, list) else []
    pairs = [
        (p.get("day"), p.get("open"), p.get("close"), p.get("high"), p.get("low"), p.get("volume"))
        if isinstance(p, dict) and "day" in p
        else (p.get("d"), p.get("o"), p.get("c"), p.get("h"), p.get("l"), p.get("v"))
        for p in arr if isinstance(p, dict)
    ]
    return _rows(pairs)


def fetch_kline(vendor, code):
    """按 (渠道, 代码) 抓全部日K：先过自有 Worker，失败退本机直连（各自尝试 3 次）。

    返回日期升序 rows；全部失败返回 []（由调用方走旧数据兜底）。
    """
    if vendor == "sina":
        worker_q = f"?vendor=sina&symbol={code}&n={CN_KLINE_MAX}"
        direct = SINA_CN_K.format(sym=code, n=CN_KLINE_MAX)
        referer = "https://finance.sina.com.cn/"
    elif vendor == "sinaus":
        worker_q = f"?vendor=sinaus&symbol={code}"
        direct = SINA_US_K.format(sym=code, n=9000)
        referer = "https://finance.sina.com.cn/"
    elif vendor == "eastmoney":
        worker_q = f"?vendor=eastmoney&symbol={code}"
        direct = EM_K.format(secid=code)
        referer = "https://quote.eastmoney.com/"
    else:
        return []

    for url in (WORKER + worker_q, direct):
        for attempt in range(3):
            try:
                req = urllib.request.Request(
                    url, headers={"User-Agent": UA, "Referer": referer}
                )
                txt = urllib.request.urlopen(req, timeout=40).read().decode("utf-8", "replace")
            except Exception as e:  # noqa
                print(f"  [警告] {vendor}:{code} 经 {url.split('/')[2]} 第{attempt + 1}次失败: {e}")
                time.sleep(1)
                continue
            rows = _parse_kline(vendor, txt)
            if rows:  # 空响应（如东财 grep 到的 520 错误页）同样退避重试
                return rows
            time.sleep(1)
    return []


def fetch_fund_nav(code):
    """抓取场外基金全部历史净值（天天基金 pingzhongdata），合成分红再投的复权净值。

    复权方法：某日每份分红 = (累计净值差) - (单位净值差)（累计净值=单位净值+累计每份分红，
    两边都是 4 位小数、普通日两差相抵恰好为 0；足额分红远大于小数舍入噪声，据此去噪），
    当日真实收益 = (单位净值+每份分红) / 昨日单位净值，逐日连乘得复权净值。
    行口径与指数一致（[日期,开,收,高,低,量]，开=高=低=复权净值，量=0），
    前端 buildIndex 取收盘归一化后即「分红再投累计倍数」。
    返回 (rows, meta)：rows 为复权序列，失败为 []；meta = {code, navs:[[日,单位净值]],
    divs:[[日,每份分红]]} 供前端「现金分红」模式模拟（分红发现金、不再生息），失败为 None。"""
    url = f"https://fund.eastmoney.com/pingzhongdata/{code}.js"
    req = urllib.request.Request(
        url, headers={"User-Agent": UA, "Referer": "https://fund.eastmoney.com/"}
    )
    src = None
    for attempt in range(3):
        try:
            src = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")
            break
        except Exception as e:  # noqa
            if attempt == 2:
                print(f"  [警告] 基金 {code} 净值抓取失败: {e}")
                return [], None
            time.sleep(1)

    def _series(name):
        m = re.search(name + r"\s*=\s*(\[.*?\]);", src, re.S)
        return json.loads(m.group(1)) if m else []

    nav_pts = _series("Data_netWorthTrend")
    acc_pts = _series("Data_ACWorthTrend")
    if not nav_pts:
        print(f"  [警告] 基金 {code} 未取到单位净值趋势，跳过")
        return [], None
    to_date = lambda ms: (  # noqa: E731
        datetime.datetime(1970, 1, 1)
        + datetime.timedelta(milliseconds=int(ms) + 8 * 3600 * 1000)
    ).strftime("%Y-%m-%d")
    # 累计净值按日期对齐（与单位净值同源同日，个别起点缺失时沿用上一个已知值）
    acc_map = {to_date(p[0]): float(p[1]) for p in acc_pts if isinstance(p, (list, tuple)) and len(p) >= 2}

    rows = []
    meta = {"code": code, "navs": [], "divs": []}
    prev_nav = prev_acc = adj = None
    div_days = 0
    last_d = ""
    for p in nav_pts:
        try:
            nav = float(p.get("y"))
        except (TypeError, ValueError):
            continue
        if nav <= 0 or not p.get("x"):
            continue
        d = to_date(p["x"])
        if d == last_d:
            continue
        last_d = d
        acc = acc_map.get(d, prev_acc)
        div = 0.0
        if adj is None:
            adj = nav
        else:
            if acc is not None and prev_acc is not None:
                raw = (acc - prev_acc) - (nav - prev_nav)
                if raw > 0.001:  # 分红日才显著非零
                    div = raw
                    div_days += 1
            adj = adj * (nav + div) / prev_nav
        rows.append({
            "d": d,
            "o": round(adj, 4), "c": round(adj, 4),
            "h": round(adj, 4), "l": round(adj, 4), "v": 0,
        })
        meta["navs"].append([d, nav])
        if div > 0.001:
            meta["divs"].append([d, round(div, 6)])
        prev_nav = nav
        if acc is not None:
            prev_acc = acc
    print(f"  基金 {code}: {len(rows)} 个净值交易日，识别分红 {div_days} 次（已再投）")
    return rows, meta


def _js_blobs(src):
    """把 kline_data.js 文本按 window.变量名 分段解析成 dict
    （分段解析以避免贪婪正则把后一个变量的内容吞进前一个）。"""
    parts = re.split(r"window\.(\w+)\s*=\s*", src)
    return {parts[i]: parts[i + 1].strip().rstrip(";").strip() for i in range(1, len(parts) - 1, 2)}


def load_old():
    """读取旧的 kline_data.js。返回 (旧KLINE_DATA dict, 旧SPLICE_META dict, 旧DCA_FUND_META)，
    缺失为 None。（按 window.变量名 分段解析，避免贪婪正则把后一个变量的内容吞进前一个）"""
    if not os.path.exists(OUT):
        return None, None, None
    try:
        with open(OUT, encoding="utf-8") as f:
            src = f.read()
        blobs = _js_blobs(src)
        old = meta = dca = None
        if "KLINE_DATA" in blobs:
            old = json.loads(blobs["KLINE_DATA"])
            old = {k: _norm_rows(v) for k, v in old.items()}
        if "KLINE_SPLICE_META" in blobs:
            meta = json.loads(blobs["KLINE_SPLICE_META"])
        if "DCA_FUND_META" in blobs:
            dca = json.loads(blobs["DCA_FUND_META"])
        return old, meta, dca
    except Exception:
        return None, None, None


def _norm_rows(rows):
    """行数据统一为 dict：旧版为 {d,o,c,h,l,v} 对象，新版为紧凑数组 [d,o,c,h,l,v]。"""
    if not rows or isinstance(rows[0], dict):
        return rows
    return [{"d": r[0], "o": r[1], "c": r[2], "h": r[3], "l": r[4], "v": r[5]} for r in rows]


def _kline_from_js(src):
    """从 kline_data.js 文本解析 KLINE_DATA → {name: dictRows}；缺变量返回 {}。"""
    blobs = _js_blobs(src)
    if "KLINE_DATA" not in blobs:
        return {}
    return {k: _norm_rows(v) for k, v in json.loads(blobs["KLINE_DATA"]).items()}


def _dense(rows):
    """「静态历史段」的连续性检查：相邻日期最大间隔 ≤21 天视为完整衔接段
    （美股最长自然休市缺口约 11 天；新浪 qqq 归档的大跨度缺档会被此拦下）。"""
    if len(rows) < 50:
        return False
    to_d = lambda s: datetime.date(*map(int, s.split("-")))  # noqa: E731
    return all(
        (to_d(rows[i]["d"]) - to_d(rows[i - 1]["d"])).days <= 21
        for i in range(1, len(rows))
    )


def _pack(rows):
    """dict 行压缩为紧凑数组 [日期,开,收,高,低,量] 再序列化（省去每行重复的键名）。"""
    return [[r["d"], r["o"], r["c"], r["h"], r["l"], r["v"]] for r in rows]


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


def frozen_prefix(seam):
    """读取冻结前缀（已按接缝折算），截取早于 seam 的部分；无效返回 (None, None)。"""
    try:
        with open(PREFIX_ARTIFACT, encoding="utf-8") as f:
            art = json.load(f)
        rows = [r for r in _norm_rows(art.get("prefix") or []) if r["d"] < seam]
        if rows:
            return rows, art.get("scale") or 1.0
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None, None


def rebuild_prefix(seam, ndx_open, old):
    """本地无冻结前缀时重新生成一份并写 PREFIX_ARTIFACT 落盘。

    来源优先级：
      1. 本地 Pages 备份 kline_data_pages_backup.js（旧东财 QQQ 前复权前缀，2001~2014 无缺档）
      2. 在线 Pages 的 kline_data.js（同上；顺手刷新本地备份）
      3. 旧本地 kline_data.js 的纳指100 段
      4. 新浪 qqq（归档缺 2005~2010 整段，仅作最后手段，段内有洞时图上可见）
    1~3 各自先过 _dense 连续性检查；折算比例 = ndx_open / 前末日收盘。
    全部失败返回 ([], None)（由调用方退化为「无前缀」）。
    """
    cands = []
    try:
        with open(PAGES_BACKUP, encoding="utf-8") as f:
            cands.append(("本地 Pages 备份", f.read()))
    except OSError:
        pass
    try:
        req = urllib.request.Request(PAGES_URL, headers={"User-Agent": UA})
        src = urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "replace")
        online = [r for r in (_kline_from_js(src).get("纳指100") or []) if r["d"] < seam]
        if _dense(online):
            cands.append(("在线 Pages", src))
            try:  # 仅当在线版仍是完整前缀时才刷新本地备份，防止完整版被新版 Page 覆盖
                with open(PAGES_BACKUP, "w", encoding="utf-8") as f:
                    f.write(src)
            except OSError:
                pass
        else:
            print("  [提示] 在线 Pages 前缀已不完整（可能已被新版覆盖），仅用本地备份")
    except Exception as e:  # noqa
        print(f"  [提示] 在线 Pages 旧前缀不可用: {e}")
    if old and old.get("纳指100"):
        cands.append(("旧本地文件", old["纳指100"]))

    for label, data in cands:
        if isinstance(data, str):
            data = _kline_from_js(data).get("纳指100") or []
        rows = [r for r in data if r["d"] < seam]
        if not _dense(rows):
            print(f"  [提示] 前缀候选「{label}」不连续（{len(rows)} 根），跳过")
            continue
        scale, scaled = scale_qqq_prefix(rows, ndx_open)
        try:
            with open(PREFIX_ARTIFACT, "w", encoding="utf-8") as f:
                json.dump({"seam": seam, "scale": round(scale, 6), "prefix": _pack(scaled)},
                          f, ensure_ascii=False)
        except OSError:
            pass
        print(f"  前缀来源「{label}」：{len(scaled)} 根已折算并冻结到 kline_prefix.json")
        return scaled, scale

    qqq = fetch_kline(*QQQ_SRC)  # 最后手段：新浪 qqq（2005~2010 缺档）
    rows = [r for r in qqq if r["d"] < seam]
    if rows:
        scale, scaled = scale_qqq_prefix(rows, ndx_open)
        print(f"  [警告] 仅剩新浪 qqq 前缀（缺 2005~2010 段，{len(scaled)} 根），图中该段不完整")
        return scaled, scale
    return [], None


def build():
    """抓取并生成全部日K。返回 (out, meta, dca_meta)：out 供 KLINE_DATA，meta 为拼接信息
    （可为 None），dca_meta 供定投模拟的现金分红口径（{key: {code,navs,divs}}，缺项可为 None）。"""
    old, old_meta, old_dca_meta = load_old()
    out = {}
    dca_meta = {}

    # ---- 标普500：东财全量真实指数（1986 年起，经 Worker 代取）；抓取失败沿用旧数据 ----
    spx = fetch_kline(*SYMBOLS["标普500"])
    if not spx and old and old.get("标普500"):
        spx = old["标普500"]
        print("  [兜底] 标普500 抓取失败，沿用旧的指数日K")
    out["标普500"] = spx
    time.sleep(0.3)

    # ---- 纳指100：新浪真指数（2014-02 起）+ QQQ 折算前缀拼接（2001 年起）----
    ndx = fetch_kline(*SYMBOLS["纳指100"])
    time.sleep(0.3)
    meta = old_meta if not ndx else None
    if ndx:
        seam = ndx[0]["d"]
        prefix, scale = frozen_prefix(seam)
        if prefix is None:
            prefix, scale = rebuild_prefix(seam, ndx[0]["o"], old)
        if prefix:
            if abs(prefix[-1]["c"] - ndx[0]["o"]) > 0.01:  # 接缝必须相等，防御性检查
                print("  [警告] 拼接接缝出现跳变，请检查数据质量")
            out["纳指100"] = prefix + ndx
            meta = make_meta(prefix, seam, scale if scale else 1.0)
            print(
                f"  拼接接缝 {seam}：前段 {len(prefix)} 根 QQQ 折算"
                f" [{prefix[0]['d']} ~ {prefix[-1]['d']}]，比例 {round(scale, 6)}"
            )
        else:
            out["纳指100"] = ndx
            print("  [警告] 无 QQQ 拼接前缀（各来源均不可用），纳指100 使用 2014 年起原始序列")
    elif old and old.get("纳指100"):
        # 指数本体抓取失败：整段沿用旧数据（保持原拼接状态与接缝口径）
        out["纳指100"] = old["纳指100"]
        print("  [兜底] 纳指100 抓取失败，沿用旧的指数日K")
    else:
        out["纳指100"] = []

    # ---- 上证指数：新浪全量真实指数（1990-12 起）；抓取失败沿用旧数据 ----
    sse = fetch_kline(*SYMBOLS["上证指数"])
    if not sse and old and old.get("上证指数"):
        sse = old["上证指数"]
        print("  [兜底] 上证指数 抓取失败，沿用旧的指数日K")
    out["上证指数"] = sse
    time.sleep(0.3)

    # ---- 定投场外基金（dca.html 选项）：基金复权净值全历史；失败沿用旧数据 ----
    for key, code in DCA_FUNDS.items():
        fld, fmeta = fetch_fund_nav(code)
        if not fld and old and old.get(key):
            fld = old[key]
            fmeta = (old_dca_meta or {}).get(key)
            print(f"  [兜底] {key}（{code}）净值抓取失败，沿用旧数据")
        out[key] = fld
        if fmeta:
            dca_meta[key] = fmeta
        time.sleep(0.3)

    return out, meta, dca_meta


def main():
    out, meta, dca_meta = build()
    if not any(out.values()):
        print("  [警告] 指数日K全部抓取失败且无旧数据，保留旧的 kline_data.js")
        return
    payload = json.dumps({k: _pack(v) for k, v in out.items()}, ensure_ascii=False, separators=(",", ":"))
    meta_payload = json.dumps(meta, ensure_ascii=False, separators=(",", ":")) if meta else "null"
    dca_payload = json.dumps(dca_meta, ensure_ascii=False, separators=(",", ":")) if dca_meta else "null"
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("window.KLINE_DATA = " + payload + ";\n")
        f.write("window.KLINE_SPLICE_META = " + meta_payload + ";\n")
        f.write("window.DCA_FUND_META = " + dca_payload + ";\n")
    for name, rows in out.items():
        if rows:
            print(f"  {name}: {len(rows)} 根日K，{rows[0]['d']} ~ {rows[-1]['d']}")
    if dca_meta:
        for name, m in dca_meta.items():
            print(f"  {name}: 附单位净值 {len(m.get('navs') or [])} 天、分红事件 {len(m.get('divs') or [])} 笔（现金分红口径用）")
    print("已写入", OUT)


if __name__ == "__main__":
    main()
