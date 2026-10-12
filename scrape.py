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
#   仅保留场外 A 类份额（已去掉场内 ETF/LOF 及 C/D/E/F/I 类份额）
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
                # 近一年收益率：往前找约 365 天前最近的一个净值
                try:
                    target = last.get("x") - 365 * 24 * 3600 * 1000
                    prev = None
                    for it in arr:  # 顺序遍历，找第一个 >= target 的净值
                        if it.get("x") >= target:
                            prev = it.get("y")
                            break
                    if prev and nav:
                        ret_1y = round((nav - prev) / prev * 100, 2)
                except Exception:
                    ret_1y = None
        except Exception:
            nav = None
    if nav is None:
        return None
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


# ---------------------------------------------------------------- 暂停申购时长
def fetch_pause_date(code):
    """获取最近一次非节假日「暂停申购」公告日期，返回 'YYYY-MM-DD' 或 None。"""
    try:
        url = f"https://api.fund.eastmoney.com/f10/JJGG?fundcode={code}&pageIndex=1&pageSize=50&type=5"
        data = json.loads(fetch(url, referer="https://fundf10.eastmoney.com/"))
        items = data.get("Data") or []
    except Exception:
        return None
    items.sort(key=lambda x: x.get("PUBLISHDATEDesc", ""), reverse=True)
    for it in items:
        t = it.get("TITLE", "")
        if "节假日" in t:
            continue
        # 完全暂停申购（排除「暂停大额」=限大额、「恢复」）
        if "暂停申购" in t and "大额" not in t and "恢复" not in t:
            return it.get("PUBLISHDATEDesc")
    return None


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
# 数据源：雅虎财经 chart API（^NDX=纳指100，^GSPC=标普500）。可回溯到指数发布之初
# （纳指100 1985 年、标普500 1970 年）。腾讯 us.NDX 只到 2000 年，故弃用。
KLINE_OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kline_data.js")
KLINE_YAHOO = {
    "纳指100": "%5ENDX",   # ^NDX
    "标普500": "%5EGSPC",  # ^GSPC
}


def fetch_all_kline(yahoo_code):
    """从雅虎 chart API 抓取全部日K（自发布以来），返回按日期升序的 rows 列表。"""
    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/"
        f"{yahoo_code}?period1=0&period2=9999999999&interval=1d"
    )
    try:
        data = json.loads(fetch(url))
    except Exception as e:  # noqa
        print(f"  [警告] {yahoo_code} K线抓取失败: {e}")
        return []
    result = (data.get("chart") or {}).get("result") or []
    if not result:
        return []
    r = result[0]
    ts = r.get("timestamp") or []
    q = ((r.get("indicators") or {}).get("quote") or [{}])[0]
    o = q.get("open") or []
    c = q.get("close") or []
    h = q.get("high") or []
    l = q.get("low") or []
    v = q.get("volume") or []
    rows = []
    for i, t in enumerate(ts):
        if c[i] is None:  # 跳过停牌/无成交日
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


def write_kline_data():
    """抓取纳指100/标普500 全部日K，写入 kline_data.js（供 index.html / kline.html 加载）。"""
    out = {}
    for name, yahoo_code in KLINE_YAHOO.items():
        out[name] = fetch_all_kline(yahoo_code)
        time.sleep(0.5)
    if not any(out.values()):
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

        # 场外基金：暂停申购超过3个月（90天）则无参考价值，跳过
        if item["otc_status"] and "暂停" in item["otc_status"]:
            pause_date = fetch_pause_date(code)
            if pause_date:
                try:
                    d = datetime.datetime.strptime(pause_date, "%Y-%m-%d")
                    if (datetime.datetime.now() - d).days > 90:
                        print(f"  [过滤] {code} {item['name']} 暂停申购已超3个月（{pause_date}），跳过")
                        continue
                except ValueError:
                    pass

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
