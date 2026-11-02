# -*- coding: utf-8 -*-
"""生成《毕业设计项目介绍》Word 文档（含项目实际运行截图）。"""
from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "毕业设计项目介绍-基于多源数据聚合的跨境指数基金申购额度监控与指数趋势可视化系统的设计与实现.docx")
if len(sys.argv) > 1:  # 目标文件被 Word 占用时，可用命令行参数指定其他输出文件名
    OUT = os.path.join(BASE, sys.argv[1])

doc = Document()

# ---------- 页面：A4，常规页边距 ----------
sec = doc.sections[0]
sec.page_width, sec.page_height = Cm(21.0), Cm(29.7)
sec.top_margin = sec.bottom_margin = Cm(2.54)
sec.left_margin = sec.right_margin = Cm(3.17)

# ---------- 样式 ----------
def _east_asia(style_or_run, name):
    rpr = style_or_run.element.get_or_add_rPr()
    rfonts = rpr.get_or_add_rFonts()
    rfonts.set(qn("w:eastAsia"), name)

normal = doc.styles["Normal"]
normal.font.name = "Times New Roman"
normal.font.size = Pt(12)
_east_asia(normal, "宋体")
normal.paragraph_format.line_spacing = 1.4

for hname, size in (("Heading 1", 16), ("Heading 2", 13.5), ("Heading 3", 12.5)):
    hs = doc.styles[hname]
    hs.font.name = "Arial"
    hs.font.size = Pt(size)
    hs.font.bold = True
    hs.font.color.rgb = RGBColor(0, 0, 0)
    _east_asia(hs, "黑体")

def body(text, indent=True, bold=False, center=False, size=12, space_after=6):
    p = doc.add_paragraph()
    if center:
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    if indent:
        p.paragraph_format.first_line_indent = Pt(24)
    run = p.add_run(text)
    run.font.size = Pt(size)
    run.font.bold = bold
    _east_asia(run, "宋体")
    p.paragraph_format.space_after = Pt(space_after)
    return p

def bullet(text):
    p = doc.add_paragraph(style="List Bullet")
    run = p.add_run(text)
    run.font.size = Pt(12)
    _east_asia(run, "宋体")
    return p

def numbered(text):
    p = doc.add_paragraph(style="List Number")
    run = p.add_run(text)
    run.font.size = Pt(12)
    _east_asia(run, "宋体")
    return p

def add_fig(fname, caption, width_cm=15.2):
    path = os.path.join(BASE, fname)
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(6)
    run = p.add_run()
    run.add_picture(path, width=Cm(width_cm))
    cap = doc.add_paragraph()
    cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    cap.paragraph_format.space_after = Pt(12)
    crun = cap.add_run(caption)
    crun.font.size = Pt(10.5)
    crun.font.bold = True
    _east_asia(crun, "宋体")

def add_page_number():
    p = sec.footer.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run()
    f1 = OxmlElement("w:fldChar"); f1.set(qn("w:fldCharType"), "begin")
    it = OxmlElement("w:instrText"); it.set(qn("xml:space"), "preserve"); it.text = "PAGE"
    f2 = OxmlElement("w:fldChar"); f2.set(qn("w:fldCharType"), "end")
    run._element.append(f1); run._element.append(it); run._element.append(f2)
    run.font.size = Pt(9)

add_page_number()

# ============ 封面标题区 ============
t = doc.add_paragraph(); t.alignment = WD_ALIGN_PARAGRAPH.CENTER
tr = t.add_run("基于多源数据聚合的跨境指数基金\n申购额度监控与指数趋势可视化系统的设计与实现")
tr.font.size = Pt(22); tr.font.bold = True; tr.font.color.rgb = RGBColor(31, 56, 100)
tr.font.name = "Arial"; _east_asia(tr, "黑体")

sub = doc.add_paragraph(); sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
sr = sub.add_run("—— 以纳斯达克100 / 标普500 QDII 基金为例 ——")
sr.font.size = Pt(14); sr.font.bold = True; _east_asia(sr, "黑体")
sub.paragraph_format.space_before = Pt(10)

intro = doc.add_paragraph(); intro.alignment = WD_ALIGN_PARAGRAPH.CENTER
i2r = intro.add_run("毕 业 设 计 项 目 介 绍")
i2r.font.size = Pt(13); _east_asia(i2r, "黑体")
intro.paragraph_format.space_before = Pt(14)

info = doc.add_paragraph(); info.alignment = WD_ALIGN_PARAGRAPH.CENTER
ir = info.add_run("姓名：________　　学号：________　　专业：________　　指导教师：________")
ir.font.size = Pt(12); _east_asia(ir, "宋体")
info.paragraph_format.space_before = Pt(16)

dt = doc.add_paragraph(); dt.alignment = WD_ALIGN_PARAGRAPH.CENTER
dru = dt.add_run("2026 年 11 月")
dru.font.size = Pt(12); _east_asia(dru, "宋体")

doc.add_paragraph()

# ============ 一、项目概述 ============
doc.add_heading("一、项目概述", level=1)
body("近年来，境内投资者通过 QDII 基金配置美股的需求持续上升。以跟踪纳斯达克100、标普500 指数的 QDII 基金为例，由于外汇额度紧张，基金公司普遍采取“限额申购”“暂停申购”等措施，且额度随公告频繁变动。这些关键信息分散在天天基金等平台的每只基金详情页中，投资者若想对比 20 余只同类基金的申购可用性，需要逐只搜索、逐日刷新，效率低且极易遗漏。")
body("本项目设计并实现了一个“零成本、每日自动更新”的场外基金额度监控系统：以静态网页为载体，聚合当前市场上 22 只主流纳指100 / 标普500 / 纳指科技 QDII 基金（仅 A 类份额）的关键申购信息，包括申购状态（开放 / 限大额 / 暂停申购 / 暂不销售）、第三方代销渠道的单日限购金额、单位净值与净值日期、近一年收益率、年化跟踪误差、管理费与托管费率等，帮助投资者在一页之内完成“能不能买、还能买多少、值不值得买”的快速对比。同时，系统内置两大标的指数的多周期趋势视图：基于 Apache ECharts 实现的纳指100 / 标普500 日 K 线，覆盖纳指100 自 2001 年（2019 年 4 月前为 QQQ 复权价折算拼接）、标普500 自 1986 年以来的全历史行情，支持近 1 月至成立来的 8 档区间切换与拖拽缩放，投资者在查看额度的同时即可复盘指数长期趋势、阶段性回撤与当前位置。")
body("系统已部署于 GitHub Pages，可随时在线访问：https://drayven6657.github.io/Nasdaq_100_QDII_Fund/")

p = body("监控基金覆盖情况（每日更新）：", indent=False)
tbl = doc.add_table(rows=4, cols=3)
tbl.style = "Table Grid"
tbl.alignment = WD_ALIGN_PARAGRAPH.CENTER
head = ["跟踪指数", "基金数量", "说明"]
rows = [
    ("纳斯达克100", "17 只", "含场外 A 类与 LOF 份额（160213、161130）"),
    ("纳斯达克科技", "1 只", "景顺长城纳斯达克科技市值加权指数（017091）"),
    ("标普500", "4 只", "博时、华夏、大成、摩根旗下场外 A 类"),
]
for j, h in enumerate(head):
    c = tbl.rows[0].cells[j]
    c.text = ""
    r = c.paragraphs[0].add_run(h); r.font.bold = True; r.font.size = Pt(11); _east_asia(r, "黑体")
    c.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
for i, row in enumerate(rows, start=1):
    for j, v in enumerate(row):
        c = tbl.rows[i].cells[j]
        c.text = ""
        r = c.paragraphs[0].add_run(v); r.font.size = Pt(11); _east_asia(r, "宋体")
        if j < 2:
            c.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER

# ============ 二、需求分析 ============
doc.add_heading("二、需求分析", level=1)
doc.add_heading("2.1 功能需求", level=2)
bullet("数据采集：每日定时从各公开数据源抓取基金净值、申购状态、限购额度、费率、指数实时点位与指数历史日 K 线。")
bullet("数据展示：以分组表格集中展示全部基金的关键指标，对“暂停申购”与“可申购”用醒目的红 / 绿颜色区分，近一年收益率以进度条做同指数横向对比。")
bullet("指数趋势查看：内置纳指100（2001 年至今，2019 年 4 月前为 QQQ 复权价折算拼接）与标普500（1986 年至今）全历史日 K 趋势图，支持近 1 月～成立来 8 档时间区间切换、滚轮与滑杆拖拽缩放，直观复盘指数各周期走势与阶段性回撤。")
bullet("交互功能：按指数一键筛选、全列点击排序、“可申购优先”置顶开关；指数行情卡片与 K 线图跟随筛选联动；K 线支持 1 月～10 年／成立来的区间切换、滚轮与滑杆拖拽缩放、悬停查看开高低收。")
bullet("自动更新：每日两个时点自动抓取最新数据并自动发布上线，全程无需人工干预。")
doc.add_heading("2.2 非功能需求", level=2)
bullet("零成本：全部使用免费服务与公开免费接口，无服务器、无数据库、无第三方收费依赖。")
bullet("低依赖：后端仅用 Python 标准库（urllib / json / re），前端为原生 HTML + CSS + JavaScript，无任何框架与图表库。")
bullet("高可用：任一字段抓取失败时自动沿用上一次成功数据兜底；页面在 file:// 协议下双击即可打开。")
bullet("易维护：基金清单在脚本顶部一处配置即可增删基金，数据字段缺失不影响其余列的正常展示。")

# ============ 三、系统总体设计 ============
doc.add_heading("三、系统总体设计", level=1)
doc.add_heading("3.1 总体架构", level=2)
body("系统采用“定时采集 — 静态数据文件 — 纯前端渲染”的轻量三层架构，整体数据流为：")
body("公开数据源（天天基金 / 腾讯行情 / 东方财富）→ 采集脚本 scrape.py（抓取、解析、清洗、兜底）→ 静态数据文件（data.js / data.json / kline_data.js）→ 静态网页 index.html / kline.html（浏览器端渲染）→ GitHub Actions 定时触发 → GitHub Pages 对外发布。", indent=True)
bullet("数据层：五个免费公开接口——天天基金 pingzhongdata（净值 / 名称 / 申购费 / 复权收益率）、天天基金详情页（申购状态 / 限购额度 / 跟踪误差）、天天基金基金概况页（管理费 / 托管费 / 销售服务费）、腾讯行情（纳指100、标普500 实时点位）、东方财富 K 线接口（指数全量历史日 K）。")
bullet("采集层：核心脚本 scrape.py，纯 Python 标准库实现，内置重试与温和限速，输出 JSON 与 JS 两种数据文件。")
bullet("展示层：index.html 主页面与 kline.html 独立 K 线页，数据经 <script> 标签注入，规避 file:// 协议下的跨域限制；K 线渲染基于本地化部署的 Apache ECharts 5，两个页面共用同一渲染模块 kline_echarts.js。")
bullet("自动化层：GitHub Actions 定时工作流每日抓取并提交数据，GitHub Pages 同步发布最新页面。")
doc.add_heading("3.2 数据来源", level=2)
t2 = doc.add_table(rows=6, cols=2)
t2.style = "Table Grid"
src_head = ["数据内容", "数据来源"]
src_rows = [
    ("基金净值 / 名称 / 申购费 / 近 1 年收益率", "天天基金 pingzhongdata/{code}.js"),
    ("申购状态 / 代销限购金额 / 年化跟踪误差", "天天基金基金详情页 fund.eastmoney.com/{code}.html"),
    ("管理费 / 托管费 / 销售服务费", "天天基金基金概况页 fundf10.eastmoney.com/jbgk_{code}.html"),
    ("指数实时点位（纳指100 / 标普500）", "腾讯行情 qt.gtimg.cn"),
    ("指数历史日 K 线", "东方财富 push2his.eastmoney.com（100.NDX100 / 100.SPX / 105.QQQ）"),
]
for j, h in enumerate(src_head):
    c = t2.rows[0].cells[j]; c.text = ""
    r = c.paragraphs[0].add_run(h); r.font.bold = True; r.font.size = Pt(11); _east_asia(r, "黑体")
    c.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
for i, row in enumerate(src_rows, start=1):
    for j, v in enumerate(row):
        c = t2.rows[i].cells[j]; c.text = ""
        r = c.paragraphs[0].add_run(v); r.font.size = Pt(11); _east_asia(r, "宋体")
doc.add_paragraph()
doc.add_heading("3.3 关键设计与数据口径", level=2)
numbered("滞后净值口径：QDII 基金净值为 T+1／T+2 公布的滞后净值（美股收盘在 A 股次日凌晨），页面明示该口径，避免用户将其误读为实时估值。")
numbered("复权收益率：近 1 年收益率优先取天天基金官方复权字段（含分红再投），其次回退到累计净值走势、最后回退到单位净值走势计算，避免分红除权导致收益率被误算为大幅亏损。")
numbered("状态与额度一致性：基金“暂停申购 / 暂不销售”时自动清空残留的历史限购金额，防止“状态已暂停、金额照旧显示”的自相矛盾。")
numbered("字段级兜底：任一字段本次抓取失败时，自动沿用上一次 data.json 中同字段数据补齐，保证表格不出现整列空白；指数日 K 全量抓取失败时保留旧文件。")
numbered("大历史聚合：指数日 K 一次请求即取全量历史（标普500 自 1986 年起），超过 1000 个数据点时自动按区间聚合开高低收与成交量，保证长周期渲染性能。")
numbered("纳指100 历史拼接：东财指数日线源头仅收录 2019 年 4 月之后，更早段以 Invesco QQQ（跟踪纳指100 的旗舰 ETF）前复权价按接缝比例整体折算后拼接，接缝两侧点位严格相等、趋势连续无跳变；拼接段成交量沿用 QQQ 原始值、仅作长期趋势参考，页面以灰色小字明示拼接区间与口径。拼接随每日数据采集自动重建，QQQ 偶发抓取失败时自动沿用旧拼接前缀，不影响日常更新。")

# ============ 四、功能模块设计 ============
doc.add_heading("四、功能模块设计", level=1)
doc.add_heading("4.1 数据采集模块（scrape.py）", level=2)
body("采集模块由 fetch_nav、fetch_detail、fetch_fees、fetch_index_quotes、write_kline_data 五个子函数构成，分别对应净值类、申购状态类、费率类、指数点位类与指数日 K 类数据。每个子函数独立重试，配合统一请求函数完成限速与编码处理。")
doc.add_heading("4.2 数据兜底模块", level=2)
body("主流程在单只基金采集完成后进行字段级缺失检查，用上一次成功生成的 data.json 兜底补齐；随后执行一致性清理（暂停申购清空限购金额），最后写入 data.json（可读副本）与 data.js（网页加载用）。")
doc.add_heading("4.3 前端展示模块", level=2)
bullet("基金表格：按指数分组展示 9 列信息，支持全部数值列排序与“可申购优先”一键置顶。")
bullet("指数实时行情卡片：纳指100 / 标普500 最新点位与当日涨跌，红涨绿跌着色，跟随指数筛选联动显示。")
bullet("指数趋势图（日K线）：基于 Apache ECharts 5（本地化部署，零外链）绘制纳指100 / 标普500 的蜡烛图 + MA5 / MA10 / MA20 均线 + 成交量副图，覆盖两大指数全历史行情（标普500 自 1986 年、纳指100 自 2001 年，2019 年 4 月前为 QQQ 复权价折算拼接）；支持近 1 月～成立来 8 档区间切换、滚轮与底部滑杆拖拽缩放、悬停十字光标与开高低收明细。")
doc.add_heading("4.4 自动化部署模块（GitHub Actions + Pages）", level=2)
body("工作流每天北京时间 04:05 / 16:05 定时运行 scrape.py，将生成的 data.json、data.js、kline_data.js 自动提交到仓库，GitHub Pages 随之发布最新数据，实现“抓取—提交—发布”全自动闭环，并支持手动触发。")
doc.add_heading("4.5 本地运行方式", level=2)
bullet("Windows：双击“启动.bat”，自动定位本机 Python 并完成数据更新后打开页面，日常每日双击一次即可。")
bullet("跨平台：执行 python scrape.py 生成数据后，浏览器直接打开 index.html（file:// 协议可直接渲染）。")

# ============ 五、成果界面展示 ============
doc.add_heading("五、成果界面展示", level=1)
body("以下截图均为系统 2026 年 11 月 2 日更新数据下的实际运行效果（浏览器 1440×1000 分辨率）。")
doc.add_heading("5.1 系统主页面", level=2)
add_fig("fig1_页面顶部.png", "图 1  系统主页面：说明区、指数筛选栏、纳斯达克100 实时行情卡片与基金额度表")
body("页面顶部为口径说明与提醒区，向用户明示“代销额度”含义与 QDII 滞后净值口径。筛选栏支持按指数一键切换；行情卡片显示纳斯达克100指数实时点位与涨跌幅；下方额度表按“近 1 年收益率”默认降序排列，近 1 年收益率列以进度条进行同指数基金间的横向对比，“暂停申购”以红色高亮、“可申购”与限购金额以绿 / 红醒目标注，最右侧两列展示年化跟踪误差与合计费率。")
doc.add_heading("5.2 指数趋势查看（日K线）", level=2)
body("除申购额格外，指数趋势查看是本系统的另一核心功能。额度回答的是“现在能不能买”，日 K 趋势回答的则是“当前处于什么位置、过去走得怎么样”：系统将纳指100（自 2001 年，2019 年 4 月前为 QQQ 复权价折算拼接）与标普500（自 1986 年）的全历史日 K 以 ECharts 蜡烛图呈现，配合均线与成交量，投资者可在一页内横跨近 1 个月到近 40 年复盘指数的趋势方向、阶段性回撤与关键位震荡。")
add_fig("fig2_指数日K线_纳指100.png", "图 2  纳斯达克100 指数趋势查看（ECharts 渲染，成立来视图）：2001 年起拼接序列、MA 均线、成交量副图与底部缩放滑杆")
body("图头实时显示最新点位、涨跌幅与三条均线数值；支持近 1 月至成立来的 8 档区间切换，底部缩略滑杆与鼠标滚轮可对任意子区间拖拽缩放；下半部为成交量副图，坐标轴自动以万 / 亿换算；鼠标悬停显示十字光标与当日开、高、低、收、均线及成交量明细；页面在「指数日K线」标题旁以灰色小字明示纳指100 的拼接区间与折算口径。")
doc.add_heading("5.3 指数筛选交互", level=2)
add_fig("fig3_筛选交互_标普500.png", "图 3  点击「标普500」后的联动效果：行情卡片、额度表与 K 线同步切换")
body("点击筛选栏「标普500」后，行情卡片、额度表与日 K 线三个区域同步联动切换为标普500 数据，tables 组标题变为「标普500 · 场外 A 类」，演示了系统“一处筛选、全局联动”的交互设计。")
doc.add_heading("5.4 独立 K 线页面", level=2)
add_fig("fig4_独立K线页面.png", "图 4  独立指数日 K 线页面 kline.html（纳指100 与标普500 上下对照）")
body("除主页面内嵌的 K 线模块外，系统另提供独立的 K 线页面 kline.html，与主页面共用同一 ECharts 渲染模块（kline_echarts.js）与数据文件（kline_data.js），将纳指100 与标普500 的日 K 上下对照展示，便于长周期复盘。")

# ============ 六、项目特色与创新点 ============
doc.add_heading("六、项目特色与创新点", level=1)
numbered("全流程零成本自动化：数据抓取、提交、发布完全由 GitHub 免费基础设施完成，运行成本为 0，个人可持续维护。")
numbered("零依赖架构：后端仅用 Python 标准库、前端零框架零图表库，任何装有 Python 3 的机器均可直接运行，规避了环境配置与依赖升级问题。")
numbered("file:// 协议兼容设计：通过将数据包装为 JS 文件并以 <script> 标签加载，绕开浏览器跨域限制，用户双击 HTML 即可查看，无需搭建任何本地服务。")
numbered("多周期指数趋势复盘：内置纳指100 与标普500 全历史日 K 趋势（标普500 最早可回溯至 1986 年，纳指100 经 QQQ 复权价拼接回溯至 2001 年，接缝两侧点位严格相等、趋势连续），引入业界主流的 Apache ECharts（Apache-2.0 协议，本地化打包、零 CDN 外链）获得拖拽缩放与十字光标查价等成熟交互，配合超 1000 点自动分桶聚合策略，将近 40 年行情在一页内流畅呈现。")
numbered("数据口径严谨：明示 QDII 滞后净值口径，采用官方复权字段计算近 1 年收益率，并对“暂停申购 + 旧额度”等矛盾状态做一致性清理。")
numbered("多级容错：请求级重试、字段级兜底、文件级保留旧数据三层设计，单一接口故障不影响整体可用性。")

# ============ 七、总结与展望 ============
doc.add_heading("七、总结与展望", level=1)
body("本项目围绕 QDII 基金额度信息分散、更新频繁的真实痛点，完成了从数据采集、数据治理、前端可视化到自动化部署的完整链路，实现了一个真正可日常使用、零成本长期运行的监控系统，验证了“免费接口 + 静态页面 + 免费云”这一轻量技术路线的可行性。")
body("后续可从以下方向继续完善：")
bullet("增加场内 ETF 溢价监控，覆盖“场内买入还是场外申购”的决策场景。")
bullet("建设历史额度数据库，绘制各基金限购额度随时间变化的趋势图。")
bullet("接入更多指数（如恒生科技、日经225、德国DAX 等）并支持自定义清单。")
bullet("增加额度变动提醒（邮件 / Webhook），实现由“主动查看”到“被动通知”的升级。")

# ============ 附注 ============
doc.add_paragraph()
note = doc.add_paragraph()
note.alignment = WD_ALIGN_PARAGRAPH.CENTER
nr = note.add_run("（声明：本系统仅做公开数据聚合与展示，数据可能存在延迟或错误，不构成任何投资建议。）")
nr.font.size = Pt(10.5); nr.font.color.rgb = RGBColor(110, 110, 110); _east_asia(nr, "宋体")

doc.save(OUT)
print("saved:", OUT)
