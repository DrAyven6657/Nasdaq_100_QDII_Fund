#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
纳斯达克100 QDII 基金监控 —— 每日抓取脚本
================================================

数据源（均免费、无需登录）：
  1. 净值/名称/申购费 天天基金 pingzhongdata（Data_netWorthTrend 末条为最新净值）
  2. 申购状态/限购金额/跟踪误差  天天基金基金详情页 HTML
  3. 管理费/托管费/销售服务费   天天基金基金概况页（f10 jbgk）

输出：data.json（供 index.html 渲染）

用法：python scrape.py
"""

import urllib.request
import json
import re
import time
import datetime
import os

# 基金清单：(代码, 市场, 类型, 指数, 基金公司)
#   市场：'sh' 沪市 / 'sz' 深市 / None 场外（无场内交易）
#   类型：'ETF' / 'LOF' / '场外'
#   指数：'纳指100' / '标普500' / '纳指科技'
#   仅保留 A 类份额（C/D/E/F/I 类份额已去掉）
FUNDS = [
    # ================= 纳斯达克100（场外 A 类） =================
    ("270042", None, "场外", "纳指100", "广发基金"),
    ("040046", None, "场外", "纳指100", "华安基金"),
    ("000834", None, "场外", "纳指100", "大成基金"),
    ("539001", None, "场外", "纳指100", "建信基金"),
    ("016452", None, "场外", "纳指100", "南方基金"),
    ("018043", None, "场外", "纳指100", "天弘基金"),
    ("019172", None, "场外", "纳指100", "摩根基金"),
    ("018966", None, "场外", "纳指100", "汇添富基金"),
    ("019524", None, "场外", "纳指100", "华泰柏瑞基金"),
    ("019547", None, "场外", "纳指100", "招商基金"),
    ("019441", None, "场外", "纳指100", "万家基金"),
    ("019736", None, "场外", "纳指100", "宝盈基金"),
    ("160213", "sz", "LOF", "纳指100", "国泰基金"),
    ("161130", "sz", "LOF", "纳指100", "易方达基金"),
    ("015299", None, "场外", "纳指100", "华夏基金"),
    ("016532", None, "场外", "纳指100", "嘉实基金"),
    ("016055", None, "场外", "纳指100", "博时基金"),
    # ================= 纳指科技（场外 A 类） =================
    ("017091", None, "场外", "纳指科技", "景顺长城基金"),
    # ================= 标普500（场外 A 类） =================
    ("050025", None, "场外", "标普500", "博时基金"),
    ("018064", None, "场外", "标普500", "华夏基金"),
    ("096001", None, "场外", "标普500", "大成基金"),
    ("017641", None, "场外", "标普500", "摩根基金"),
]

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
OUT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data.json")
JS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data.js")


def fetch(url, referer="https://fund.eastmoney.com/", retry=3, raw=False):
    """GET 请求，返回 bytes（raw=True）或解码后的 str。"""
    last_err = None
    for i in range(retry):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": referer})
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = resp.read()
                return data if raw else data.decode("utf-8", errors="replace")
        except Exception as e:  # noqa
            last_err = e
            time.sleep(1.0 * (i + 1))
    raise RuntimeError(f"请求失败 {url}: {last_err}")


# ---------------------------------------------------------------- 净值/名称/申购费
def _ret_1y_from_series(points):
    """points: [(时间戳ms, 数值), ...] 按时间升序。返回「最新 vs 约365天前」的涨跌幅 %。"""
    if not points:
        return None
    last_ts, last_v = points[-1]
    if not last_v:
        return None
    target = last_ts - 365 * 24 * 3600 * 1000
    prev = None
    for ts, v in points:  # 顺序遍历，找第一个 >= target 的值
        if ts >= target:
            prev = v
            break
    if not prev:
        return None
    return round((last_v - prev) / prev * 100, 2)


def fetch_nav(code):
    """从 pingzhongdata 拿最新单位净值 + 净值日期 + 名称 + 申购费率。返回 dict 或 None。"""
    url = f"https://fund.eastmoney.com/pingzhongdata/{code}.js"
    js = fetch(url)
    name = None
    nav = None
    nav_date = None
    ret_1y = None
    fee_buy = None
    fee_buy_orig = None
    m = re.search(r'var fS_name = "([^"]+)"', js)
    if m:
        name = m.group(1)
    m = re.search(r'var fS_code = "([^"]+)"', js)
    if m and m.group(1) != code:
        return None  # 代码与接口返回不符，跳过
    # 申购费率：fund_sourceRate 原费率，fund_Rate 天天基金优惠费率
    m = re.search(r'var fund_sourceRate\s*=\s*"([^"]+)"', js)
    if m and m.group(1):
        try:
            fee_buy_orig = float(m.group(1))
        except ValueError:
            pass
    m = re.search(r'var fund_Rate\s*=\s*"([^"]+)"', js)
    if m and m.group(1):
        try:
            fee_buy = float(m.group(1))
        except ValueError:
            pass
    # Data_netWorthTrend = [{"x":...,"y":净值,...}, ...]
    nav_points = []
    m = re.search(r"Data_netWorthTrend = (\[.*?\]);", js)
    if m:
        try:
            arr = json.loads(m.group(1))
            if arr:
                last = arr[-1]
                nav = last.get("y")
                ts = last.get("x")
                if ts:
                    nav_date = datetime.datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d")
                nav_points = [(it["x"], it["y"]) for it in arr if it.get("x") and it.get("y")]
        except Exception:
            nav = None
    if nav is None:
        return None

    # 近一年收益率优先取天天基金官方字段 syl_1n（已复权，含分红再投）。
    # 不能用单位净值算：分红/份额折算会除权，把收益算成大幅亏损
    # （如 160213 于 2025-08-20 每份分红 2.8 元、2025-11-25 每份分红 0.9 元）。
    m = re.search(r'var syl_1n\s*=\s*"([^"]*)"', js)
    if m and m.group(1).strip() not in ("", "-", "--"):
        try:
            ret_1y = round(float(m.group(1)), 2)
        except ValueError:
            ret_1y = None
    # 退路1：累计净值走势（同样已含分红）
    if ret_1y is None:
        m = re.search(r"Data_ACWorthTrend = (\[.*?\]);", js)
        if m:
            try:
                arr = json.loads(m.group(1))
                ret_1y = _ret_1y_from_series(
                    [(p[0], p[1]) for p in arr if isinstance(p, list) and len(p) >= 2]
                )
            except Exception:
                ret_1y = None
    # 退路2：单位净值走势
    if ret_1y is None:
        ret_1y = _ret_1y_from_series(nav_points)
    return {
        "code": code, "name": name, "nav": float(nav), "nav_date": nav_date,
        "fee_buy": fee_buy, "fee_buy_orig": fee_buy_orig, "ret_1y": ret_1y,
    }


# ---------------------------------------------------------------- 申购状态/限购/跟踪误差
def fetch_detail(code, is_otc=True):
    """从详情页拿 场外申购状态(代销视角) + 限购金额 + 年化跟踪误差。返回 dict。

    is_otc=True 表示场外基金，此时「暂不开放购买」判定为代销不销售；
    场内 ETF/LOF 的详情页也常有该提示（仅场外申购通道关闭），故不适用。
    """
    url = f"https://fund.eastmoney.com/{code}.html"
    try:
        html = fetch(url)
    except Exception as e:  # noqa
        print(f"  [警告] 详情页获取失败 {code}: {e}")
        return {"otc_status": None, "otc_limit": None, "tracking_error": None}
    status = None
    # 第一个 staticCell 为场外申购状态（限大额/暂停申购/场内交易/开放申购）
    m = re.search(r"交易状态：</span><span class=\"staticCell\">\s*([^<(]+)", html)
    if m:
        status = m.group(1).strip()
    # 代销渠道不销售该基金（I/D/F 等直销/专属份额在天天基金不上架）
    if is_otc and ("暂不开放购买" in html or "暂不销售" in html):
        status = "暂不销售"
    limit_text = None
    # 仅「限大额」才显示限额金额；「暂停申购」时括号内的上限无实际意义（不抓取）
    if status and ('限大额' in status or '限额' in status):
        m = re.search(r"单日[^<]{0,20}上限([0-9.,]+)\s*(元|万元|万)", html)
        if m:
            num = m.group(1).replace(",", "")
            unit = m.group(2)
            try:
                v = float(num)
                if v == int(v):
                    num = str(int(v))  # 5.00 -> 5
            except ValueError:
                pass
            limit_text = f"单日{num}{unit}"
    # 年化跟踪误差（仅指数基金有）
    tracking_error = None
    m = re.search(r"年化跟踪误差[^0-9]*([0-9.]+)%", html)
    if m:
        try:
            tracking_error = float(m.group(1))
        except ValueError:
            pass
    return {"otc_status": status, "otc_limit": limit_text, "tracking_error": tracking_error}


# ---------------------------------------------------------------- 管理费/托管费/销售服务费
def fetch_fees(code):
    """从基金概况页拿 管理费/托管费/销售服务费（%）。返回 dict。"""
    url = f"https://fundf10.eastmoney.com/jbgk_{code}.html"
    try:
        html = fetch(url, referer="https://fundf10.eastmoney.com/")
    except Exception as e:  # noqa
        print(f"  [警告] 费率页获取失败 {code}: {e}")
        return {"fee_mgmt": None, "fee_custodian": None, "fee_sales": None}
    def _pct(label):
        m = re.search(re.escape(label) + r"</th><td>([0-9.]+)%", html)
        return float(m.group(1)) if m else None
    return {
        "fee_mgmt": _pct("管理费率"),
        "fee_custodian": _pct("托管费率"),
        "fee_sales": _pct("销售服务费率"),
    }


# ---------------------------------------------------------------- 指数实时点位
# 数据源：腾讯行情 qt.gtimg.cn（us.NDX=纳斯达克100，us.INX=标普500，与场内 ETF 同一接口）。
INDEX_QUOTES = {
    "纳指100": "us.NDX",
    "标普500": "us.INX",
}


def fetch_index_quotes():
    """抓取纳指100/标普500 实时点位与今日涨跌（点数、百分比）。

    返回 {"纳指100": {"name":..., "price":..., "change":..., "pct":...}, ...}
    字段取自腾讯行情：f[3]=点位, f[31]=涨跌点数, f[32]=涨跌百分比。
    """
    result = {}
    symbols = ",".join(INDEX_QUOTES.values())
    try:
        raw = fetch(f"https://qt.gtimg.cn/q={symbols}", referer="https://gu.qq.com/", raw=True)
        text = raw.decode("gbk", errors="replace")
    except Exception as e:  # noqa
        print(f"  [警告] 指数行情获取失败: {e}")
        return result
    for line in text.strip().split(";"):
        line = line.strip()
        if "=" not in line:
            continue
        var, val = line.split("=", 1)
        f = val.strip('"').split("~")
        sym = var.replace("v_", "")
        idx = next((k for k, v in INDEX_QUOTES.items() if v == sym), None)
        if idx is None or len(f) < 33:
            continue
        try:
            price = float(f[3])
        except ValueError:
            continue
        def _fnum(i):
            try:
                return float(f[i]) if f[i] not in ("", "-") else None
            except (ValueError, IndexError):
                return None
        result[idx] = {
            "name": f[1],
            "price": price,
            "change": _fnum(31),
            "pct": _fnum(32),
        }
    return result


# ---------------------------------------------------------------- 指数日K（kline_data.js）
# 数据源：东方财富 push2his（100.NDX100=纳指100，100.SPX=标普500）。国内直连，
# 一次请求返回全部历史日K（纳指100 自 2019 年、标普500 自 1986 年）。
# 注意：东财的 100.NDX 是纳斯达克综合指数（COMP），点位和逐日涨跌都与纳指100 不同，不能用。
KLINE_OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kline_data.js")
KLINE_EASTMONEY = {
    "纳指100": "100.NDX100",
    "标普500": "100.SPX",
}


def fetch_all_kline(secid):
    """从东财 K 线接口抓取全部日K，返回按日期升序的 rows 列表。"""
    url = (
        "https://push2his.eastmoney.com/api/qt/stock/kline/get"
        f"?secid={secid}&fields1=f1,f2,f3,f4,f5,f6"
        "&fields2=f51,f52,f53,f54,f55,f56&klt=101&fqt=1&beg=0&end=20500101"
    )
    try:
        data = json.loads(fetch(url, referer="https://quote.eastmoney.com/"))
    except Exception as e:  # noqa
        print(f"  [警告] {secid} K线抓取失败: {e}")
        return []
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


def write_kline_data():
    """抓取纳指100/标普500 全部日K，写入 kline_data.js（供 index.html / kline.html 加载）。"""
    print("  指数日K抓取中（东方财富，一次请求拿全量历史）...")
    out = {}
    for name, secid in KLINE_EASTMONEY.items():
        out[name] = fetch_all_kline(secid)
        time.sleep(0.3)
    if not any(out.values()):
        print("  [警告] 指数日K全部抓取失败，保留旧的 kline_data.js")
        return  # 抓取失败，保留旧文件
    payload = json.dumps(out, ensure_ascii=False, separators=(",", ":"))
    with open(KLINE_OUT, "w", encoding="utf-8") as f:
        f.write("window.KLINE_DATA = " + payload + ";\n")
    print(f"  指数日K: {', '.join(f'{k} {len(v)} 根' for k, v in out.items())}")


# ---------------------------------------------------------------- 主流程
def main():
    start = time.time()
    print(f"[{datetime.datetime.now():%Y-%m-%d %H:%M:%S}] 开始抓取 {len(FUNDS)} 只场外基金...")

    funds = []
    for code, market, ftype, index, company in FUNDS:
        item = {
            "code": code,
            "market": market,
            "type": ftype,
            "index": index,
            "company": company,
            "name": None,
            "nav": None,
            "nav_date": None,
            "ret_1y": None,          # 近一年收益率 %
            "otc_status": None,      # 代销状态（天天基金）
            "otc_limit": None,       # 代销限额
            "tracking_error": None,  # 年化跟踪误差 %
            "fee_mgmt": None,        # 管理费 %
            "fee_custodian": None,   # 托管费 %
            "fee_sales": None,       # 销售服务费 %
            "fee_buy": None,         # 申购费(优惠) %
            "fee_buy_orig": None,    # 申购费(原) %
        }
        # 净值 + 名称 + 申购费 + 近一年收益率
        try:
            nav_info = fetch_nav(code)
            if nav_info:
                item["name"] = nav_info["name"]
                item["nav"] = nav_info["nav"]
                item["nav_date"] = nav_info["nav_date"]
                item["ret_1y"] = nav_info["ret_1y"]
                item["fee_buy"] = nav_info["fee_buy"]
                item["fee_buy_orig"] = nav_info["fee_buy_orig"]
            else:
                print(f"  [跳过] {code}: 净值数据缺失")
        except Exception as e:  # noqa
            print(f"  [错误] {code} 净值: {e}")

        # 场外申购状态/限购（代销）+ 跟踪误差
        detail = fetch_detail(code, is_otc=True)
        item["otc_status"] = detail["otc_status"]
        item["otc_limit"] = detail["otc_limit"]
        item["tracking_error"] = detail["tracking_error"]

        # 管理费/托管费/销售服务费
        fees = fetch_fees(code)
        item["fee_mgmt"] = fees["fee_mgmt"]
        item["fee_custodian"] = fees["fee_custodian"]
        item["fee_sales"] = fees["fee_sales"]

        # 直销额度已移除

        funds.append(item)
        time.sleep(0.3)  # 温和限速，避免触发风控

    # 兜底：缺失字段用上一次 data.json 的数据补（若存在）
    # 覆盖全部字段，避免某一接口临时失败导致该字段整列空白
    if os.path.exists(OUT_FILE):
        try:
            old = json.load(open(OUT_FILE, encoding="utf-8"))
            old_map = {f["code"]: f for f in old.get("funds", [])}
            fields = ("name", "nav", "nav_date", "ret_1y",
                      "otc_status", "otc_limit",
                      "tracking_error", "fee_mgmt", "fee_custodian", "fee_sales",
                      "fee_buy", "fee_buy_orig")
            for item in funds:
                o = old_map.get(item["code"])
                if not o:
                    continue
                for k in fields:
                    if item.get(k) is None:
                        item[k] = o.get(k)
        except Exception:
            pass

    # 清理规则：暂停申购 / 暂不销售 的基金，不应残留「限购金额」
    # （旧数据兜底可能把上一次「限大额」时的金额带过来，导致状态与金额矛盾）
    for item in funds:
        for status_key, limit_key in (("otc_status", "otc_limit"),):
            st = item.get(status_key) or ""
            if ("暂停" in st) or ("暂不销售" in st):
                item[limit_key] = None

    # 指数实时点位与今日涨跌（纳指100 / 标普500）
    index_quotes = fetch_index_quotes()
    # 兜底：指数行情获取失败时沿用上一次的数据，避免卡片空白
    if not index_quotes and os.path.exists(OUT_FILE):
        try:
            old = json.load(open(OUT_FILE, encoding="utf-8"))
            index_quotes = old.get("index_quotes") or {}
        except Exception:
            pass
    print(f"  指数点位: {', '.join(k + ' ' + str(v.get('price')) for k, v in index_quotes.items())}")

    out = {
        "updated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "note": "QDII 净值为滞后净值（T+1/T+2）。代销额度=天天基金渠道（单日限购金额）。",
        "funds": funds,
        "index_quotes": index_quotes,
    }
    payload = json.dumps(out, ensure_ascii=False, indent=2)
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        f.write(payload)
    # 额外输出 data.js：供 index.html 用 <script> 加载，
    # 这样浏览器直接双击 index.html（file:// 协议）也能显示，无需本地 HTTP 服务。
    with open(JS_FILE, "w", encoding="utf-8") as f:
        f.write("window.FUND_DATA = " + payload + ";\n")

    # 指数日K（供 K线图加载）
    write_kline_data()

    # 简要汇总
    ok = sum(1 for x in funds if x["nav"])
    print(f"  完成：{ok}/{len(funds)} 只基金有净值数据，用时 {time.time()-start:.1f}s")
    print(f"  已写入 {OUT_FILE}")


if __name__ == "__main__":
    main()
