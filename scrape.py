#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
纳斯达克100 QDII 基金监控 —— 每日抓取脚本
================================================

数据源（均免费、无需登录）：
  1. 净值/名称/申购费 天天基金 pingzhongdata（Data_netWorthTrend 末条为最新净值）
  2. 申购状态/限购金额/跟踪误差  天天基金基金详情页 HTML
  3. 管理费/托管费/销售服务费   天天基金基金概况页（f10 jbgk）

输出：data.json / data.js（供 index.html 渲染）、kline_data.js（指数日K，含纳指100 历史拼接）

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
_OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "public")
os.makedirs(_OUT_DIR, exist_ok=True)   # public/ 目录随用随建
OUT_FILE = os.path.join(_OUT_DIR, "data.json")
JS_FILE = os.path.join(_OUT_DIR, "data.js")


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
# 数据源：腾讯行情 qt.gtimg.cn（us.NDX=纳斯达克100，us.INX=标普500，sh000001=上证指数，sz399006=创业板指，
# 与场内 ETF 同一接口，字段位次统一：f3=点位 f31=涨跌 f32=涨跌%）。
INDEX_QUOTES = {
    "纳指100": "us.NDX",
    "标普500": "us.INX",
    "上证指数": "sh000001",
    "创业板指": "sz399006",
    "恒生科技": "hkHSTECH",
}


# ---------------------------------------------------------------- 韩日指数（唯东财可取）
# 新浪 int_ 国际指数家族实测是整族冻结的旧收盘快照（对照实验 2026-11-25：同家族
# int_sp500=6643.70，与腾讯/东财双方实时的 7201.09 都对不上，int_nikkei 同理停更），
# 腾讯无日韩指数代码——日经225/韩国综合的免费实时源唯东财一家。
# 快照读 trends2（末点=现价、昨收=preClose），分时用同一份序列，进程内缓存免二次抓取。
_EAST_TRENDS_CACHE = {}


def _east_index_trends(secid):
    """东财世界指数当日分时（韩日唯一实时源）：返回 (昨收, 分钟点列表)。

    Worker /trends 优先、直连东财兜底（东财对机房 IP 间歇 520，各 2 次 × 2 秒重试）；
    命中 _EAST_TRENDS_CACHE 直接返回——与 fetch_index_quotes 的快照共用一次请求。
    """
    import kline_data
    if _EAST_TRENDS_CACHE.get(secid):
        c = _EAST_TRENDS_CACHE[secid]
        return c["pre"], c["pts"]
    urls = [
        f"{kline_data.WORKER_HOST}/trends?secid={secid}",
        ("https://push2his.eastmoney.com/api/qt/stock/trends2/get"
         f"?secid={secid}&fields1=f1,f2,f3,f7,f8&fields2=f51,f53,f56,f58&ndays=1&iscr=0"),
    ]
    last_err = None
    for url in urls:
        for _ in range(3):   # 东财闪断重试
            try:
                d = json.loads(fetch(url, raw=True)).get("data") or {}
                rows = d.get("trends") or []
                pts = [float(r.split(",")[1]) for r in rows if "," in r]
                pre = float(d.get("preClose") or 0)
                if len(pts) >= 5 and pre > 0:
                    _EAST_TRENDS_CACHE[secid] = {"pre": pre, "pts": pts}
                    return pre, pts
                raise ValueError("trends2 数据不完整（点数不足或缺昨收）")
            except Exception as e:  # noqa
                last_err = e
            time.sleep(2.0)
    raise last_err or RuntimeError(f"{secid} trends2 不可用")


def fetch_index_quotes():
    """抓取八项指数卡片的实时点位与今日涨跌（点数、百分比）。

    返回 {"纳指100": {"name":..., "price":..., "change":..., "pct":...}, ...}
    取数原则：有腾讯/新浪的先用腾讯/新浪，东财只当兜底或唯一源（东财最后）：
    纳指100/标普500/上证/创业板/恒生科技 → 腾讯（f[3]=点位, f[31]=涨跌点数,
    f[32]=涨跌百分比）；黄金 → 新浪 gds_AU9999；日经225/韩国综合 → 唯东财可取
    （新浪 int_ 家族冻结、腾讯无码，trends2 末点=现价，见 _east_index_trends）。
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
    # 黄金 Au99.99（上金所现货「沪金99」）：腾讯无代码，走新浪贵金属接口。
    # 新浪 gds_ 字段：0最新 4高 5低 6时间 7昨收(官方涨跌基准) 8今开；涨跌=现价-昨收。
    try:
        raw = fetch("https://hq.sinajs.cn/list=gds_AU9999",
                    referer="https://finance.sina.com.cn/", raw=True)
        g = raw.decode("gbk", errors="replace").split('"')[1].split(",")
        price = float(g[0])
        prev = float(g[7])
        result["黄金9999"] = {
            "name": "黄金Au99.99",
            "price": price,
            "change": price - prev,
            "pct": (price - prev) / prev * 100,
        }
    except Exception as e:  # noqa
        print(f"  [提示] 黄金 Au99.99 快照获取失败: {e}")
    # 日经225 / 韩国综合：新浪 int_ 家族冻结、腾讯无码——唯东财可取，trends2 端点
    #（末点=现价，昨收=preClose，涨跌按官方口径「现价−昨收」）
    for name_, secid_ in (("日经225", "100.N225"), ("韩国综合", "100.KS11")):
        try:
            pre, pts = _east_index_trends(secid_)
            price = pts[-1]
            result[name_] = {
                "name": name_,
                "price": price,
                "change": price - pre,
                "pct": (price - pre) / pre * 100,
            }
        except Exception as e:  # noqa
            print(f"  [提示] {name_} 快照获取失败: {e}")
    return result


# ---------------------------------------------------------------- 指数当日分时（卡片迷你走势线）
# 统一走 Worker 的 /trends 路由（worker 端代取东财 trends2）：本机不直连东财，
# 且 A股/美股 同一接口同一格式（腾讯对美股指数无分钟线，新浪无分时服务）。
# 纳指100 用东财 105.QQQ（Invesco 纳指100 旗舰 ETF）的日内走势：真实纳指100 指数
# 的分钟级免费源不存在（新浪无美股分时、腾讯美股只回单点、东财 100.NDX100 死）。
# 昨收字段（pre）必须与曲线同量纲：
#   纳指100 -> QQQ 自己的昨日收盘（新浪美股日K中「日期早于分时首日」的最后一根收盘；
#              实测与东财分时收盘 651.03 双源互证），绝不能用指数口径的 26700，否则
#              页面 y 轴被撑爆、曲线会画成一条直线；
#   标普500/上证 -> 实时指数快照 price - change（与分时同一次快照，同源同量纲）。
def _qqq_prev_close(minute_date):
    """取 QQQ 的昨日收盘（纳指100 分时线的着色/虚线基准）。"""
    try:
        import kline_data
        rows = json.loads(fetch(f"{kline_data.WORKER}?vendor=sinaus&symbol=qqq&n=8", raw=True))
        best = None
        for row in rows:
            if isinstance(row, dict) and row.get("d", "") < minute_date and row.get("c"):
                best = float(row["c"])
        return best
    except Exception as e:  # noqa
        print(f"  [警告] QQQ 昨收获取失败: {e}")
        return None


def _tencent_minutes(code):
    """腾讯分时（A 股最稳源）：web.ifzq.gtimg.cn 分钟序列，行格式「0930 2233.18 量 额」。"""
    try:
        j = json.loads(fetch(f"https://web.ifzq.gtimg.cn/appstock/app/minute/query?code={code}",
                             referer="https://gu.qq.com/"))
        node = (j.get("data") or {}).get(code) or {}
        d = node.get("data") or {}
        rows = d.get("data")
        if isinstance(rows, str):
            rows = rows.split(";")
        pts = []
        for row in rows or []:
            try:
                pts.append(float(str(row).split()[1]))
            except (IndexError, ValueError, TypeError):
                continue
        return pts if len(pts) >= 5 else None
    except Exception as e:  # noqa
        print(f"  [提示] 腾讯分时 {code} 不可用: {e}")
        return None


def fetch_index_minutes(index_quotes=None):
    """抓取八项行情卡的当日分时，供卡片迷你走势线（离线/file:// 时的静态底图）。

    返回 {名称: {"pre": 昨收（与曲线同量纲）, "pts": [当日分钟价格, …]}}，
    获取失败的项不进结果。源优先级（有腾讯/新浪先用腾讯/新浪，东财最后）：
    A 股/港股（上证/创业板/恒生科技）先走腾讯 minute/query 直连（实测最稳，
    港股午休行自动省略），失败再退东财 trends2 经 CF（间歇 520，6 次 × 2 秒重试）；
    美股/韩日指数两家免费源都没有分时接口（新浪国际无分钟序列、腾讯无日韩代码），
    东财是唯一来源，直接经 CF；日经225/韩国综合复用快照阶段的缓存；
    黄金 Au99.99 分时 = 东财 118.AU9999（含昨夜 20:00 起的夜盘）经 CF。
    """
    import kline_data
    secids = {"纳指100": "105.QQQ", "标普500": "100.SPX", "上证指数": "1.000001",
              "创业板指": "0.399006", "恒生科技": "124.HSTECH", "黄金9999": "118.AU9999",
              "韩国综合": "100.KS11", "日经225": "100.N225"}
    tz_codes = {"上证指数": "sh000001", "创业板指": "sz399006", "恒生科技": "hkHSTECH"}
    index_quotes = index_quotes or {}
    result = {}
    for name, secid in secids.items():
        got = None
        # ⓪ 日经225/韩国综合：快照阶段已抓过 trends2（唯东财可取），直接复用不再二次请求
        if name in ("日经225", "韩国综合"):
            cached = _EAST_TRENDS_CACHE.get(secid)
            if cached and cached.get("pts"):
                got = (cached["pts"], None, "东财", cached["pre"])
        # ① A 股/港股：腾讯分时直连
        if not got and name in tz_codes:
            pts = _tencent_minutes(tz_codes[name])
            if pts:
                got = (pts, None, "腾讯", 0)
        # ② 东财 trends2 经 CF（兜底；美股指数唯一来源）
        if not got:
            last_err = None
            for _ in range(6):  # 上游闪断 520 重试，2 秒间隔（QQQ 通道成功率最低，放宽重试）
                try:
                    data = json.loads(fetch(f"{kline_data.WORKER_HOST}/trends?secid={secid}", raw=True))
                    d = data.get("data") or {}
                    rows = d.get("trends") or []
                    pts = []
                    for row in rows:
                        try:
                            pts.append(float(row.split(",")[1]))
                        except (IndexError, ValueError):
                            continue
                    if len(pts) >= 5:
                        got = (pts, rows[0].split(",")[0][:10], "东财",
                               float(d.get("preClose") or 0))  # 首行时间戳的日期部分
                        break
                except Exception as e:  # noqa
                    last_err = e
                time.sleep(2.0)
        if got:
            pts, minute_date, label, east_pre = got
            if name == "纳指100":
                pre = _qqq_prev_close(minute_date)
            else:
                q = index_quotes.get(name) or {}
                if q.get("price") is not None and q.get("change") is not None:
                    pre = q["price"] - q["change"]
                else:
                    pre = east_pre or None   # 东财响应自带的 preClose（与点序列同源同量纲）
            result[name] = {"pre": pre, "pts": pts}
            print(f"  {name} 分时({label}): "
                  f"{len(pts)} 个分钟点，昨收 {pre}")
        else:
            print(f"  [警告] {name} 分时获取失败: {last_err}")
        time.sleep(0.3)
    return result


# ---------------------------------------------------------------- 指数日K（kline_data.js）
# 抓取逻辑（含纳指100 的 QQQ 历史拼接，见 kline_data.py 模块文档）统一放在 kline_data.py，
# 这里只负责调用，避免两处数据生成入口口径不一致。


def write_kline_data():
    """更新指数日K数据文件 kline_data.js（含纳指100 历史拼接）。"""
    try:
        import kline_data
        kline_data.main()
    except Exception as e:  # noqa
        print(f"  [警告] 指数日K更新失败（保留旧的 kline_data.js）: {e}")


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
    # 兜底：哪个指数行情没抓到就逐个沿用它上一次的数据（按指数补，不再全军覆没才兜），
    # 避免单只指数卡片空白
    if os.path.exists(OUT_FILE):
        try:
            old_q = (json.load(open(OUT_FILE, encoding="utf-8")).get("index_quotes") or {})
            for k, v in old_q.items():
                index_quotes.setdefault(k, v)
        except Exception:
            pass
    print(f"  指数点位: {', '.join(k + ' ' + str(v.get('price')) for k, v in index_quotes.items())}")

    # 指数当日分时（卡片迷你走势线底图）
    index_minutes = fetch_index_minutes(index_quotes)
    # 兜底：单只指数分时抓空时逐只沿用上一次的底图（东财 520 闪断常见）。
    # 这里必须逐只补：pre 和 pts 是一对，烤库丢哪只指数，哪只卡片就缺失同量纲基准，
    # 页面若有错误量纲的兜底路径会把整条曲线压成一条直线
    if os.path.exists(OUT_FILE):
        try:
            old_m = (json.load(open(OUT_FILE, encoding="utf-8")).get("index_minutes") or {})
            for k, v in old_m.items():
                index_minutes.setdefault(k, v)
        except Exception:
            pass

    updated = (datetime.datetime.utcnow() + datetime.timedelta(hours=8)).strftime("%Y-%m-%d %H:%M:%S")
    out = {
        # 显示统一用北京时间：Actions 的机器时区是 UTC，不 +8 会显示成"昨天"，易被误判为没更新
        "updated": updated,
        "note": "QDII 净值为滞后净值（T+1/T+2）。代销额度=天天基金渠道（单日限购金额）。",
        "funds": funds,
        "index_quotes": index_quotes,
        "index_minutes": index_minutes,
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
