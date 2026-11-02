/* 指数日K线渲染模块 —— index.html 与 kline.html 共用
 * 渲染引擎：Apache ECharts 5（本地 echarts.min.js，无 CDN 依赖）
 * 数据来源：window.KLINE_DATA（由 scrape.py / kline_data.py 生成）
 *
 * 用法：
 *   KLINE_ECHARTS.init({
 *     idx: '纳指100',                 // KLINE_DATA 的键，同时用于拼接元素 id
 *     elId: 'wrap-纳指100',           // 图表容器（需有高度，css 里给定）
 *     priceId: 'price-纳指100',       // 图头最新价元素
 *     chgId: 'chg-纳指100',           // 图头涨跌幅元素
 *     maIds: { ma5: 'ma5-纳指100', ma10: 'ma10-纳指100', ma20: 'ma20-纳指100' },
 *     rangeBoxId: 'range-纳指100',    // 时间区间按钮容器
 *   });
 * 注意：容器初始为 display:none 时不会立即创建图表，
 *       变为可见后调用 KLINE_ECHARTS.resizeAll() 即自动补建/重算尺寸。
 */
(function () {
  'use strict';

  const MAX_POINTS = 1000;   // 超过则聚合，保证渲染流畅
  const DEFAULT_RANGE = 126;
  const RANGES = [
    { label: '近1月', days: 22 }, { label: '3月', days: 66 }, { label: '半年', days: 126 },
    { label: '1年', days: 252 }, { label: '3年', days: 756 }, { label: '5年', days: 1260 },
    { label: '10年', days: 2520 }, { label: '成立来', days: 0 },
  ];
  const MA = { ma5: { n: 5, color: '#f59e0b' }, ma10: { n: 10, color: '#2563eb' }, ma20: { n: 20, color: '#7c3aed' } };
  const UP = '#dc2626', DOWN = '#16a34a';

  const states = {};

  function fmtNum(v, d) { return v.toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d }); }
  function fmtVol(v) {
    const n = Number(v);
    if (n >= 1e8) return (n / 1e8).toFixed(1) + '亿';
    if (n >= 1e4) return (n / 1e4).toFixed(1) + '万';
    return String(Math.round(n));
  }
  function calcMA(rows, n) {
    const out = new Array(rows.length).fill(null);
    let sum = 0;
    for (let i = 0; i < rows.length; i++) { sum += rows[i].c; if (i >= n) sum -= rows[i - n].c; if (i >= n - 1) out[i] = sum / n; }
    return out;
  }
  // 把多根日K聚合成一根（保留首开/末收/最高/最低/量合计），用于超长区间
  function aggregate(rows, maxPoints) {
    if (rows.length <= maxPoints) return rows;
    const bucket = Math.ceil(rows.length / maxPoints);
    const out = [];
    for (let i = 0; i < rows.length; i += bucket) {
      const c = rows.slice(i, i + bucket);
      out.push({ d: c[0].d, o: c[0].o, c: c[c.length - 1].c, h: Math.max(...c.map(r => r.h)), l: Math.min(...c.map(r => r.l)), v: c.reduce((s, r) => s + r.v, 0) });
    }
    return out;
  }
  function downsampleLast(arr, bucket) {
    const out = [];
    for (let i = 0; i < arr.length; i += bucket) out.push(arr[Math.min(i + bucket - 1, arr.length - 1)]);
    return out;
  }

  function buildData(idx, days) {
    const rows = (window.KLINE_DATA || {})[idx] || [];
    if (!rows.length) return null;
    const maFull = { ma5: calcMA(rows, 5), ma10: calcMA(rows, 10), ma20: calcMA(rows, 20) };
    let data = days > 0 ? rows.slice(-days) : rows.slice();
    const startIdx = rows.length - data.length;
    let ma = { ma5: maFull.ma5.slice(startIdx), ma10: maFull.ma10.slice(startIdx), ma20: maFull.ma20.slice(startIdx) };
    if (data.length > MAX_POINTS) {
      const bucket = Math.ceil(data.length / MAX_POINTS);
      data = aggregate(data, MAX_POINTS);
      ma.ma5 = downsampleLast(ma.ma5, bucket);
      ma.ma10 = downsampleLast(ma.ma10, bucket);
      ma.ma20 = downsampleLast(ma.ma20, bucket);
    }
    return { data, ma, maFull };
  }

  // 容器有尺寸才创建 ECharts 实例（隐藏状态下初始化会得到 0 宽画布）
  function ensureChart(st) {
    if (st.chart) return true;
    if (!window.echarts) {
      const el = document.getElementById(st.elId);
      if (el) el.innerHTML = '<div style="padding:20px;text-align:center;color:#9ca3af">加载图表组件失败：未找到 echarts.min.js</div>';
      return false;
    }
    const el = document.getElementById(st.elId);
    if (!el || el.clientWidth === 0) return false;
    st.chart = echarts.init(el);
    return true;
  }

  function updateHeader(st, bd) {
    const rows = bd.data;
    const last = rows[rows.length - 1], prev = rows[rows.length - 2];
    const chg = prev ? last.c - prev.c : 0;
    const pct = prev ? chg / prev.c * 100 : 0;
    const cls = chg >= 0 ? 'up' : 'down';
    const priceEl = document.getElementById(st.priceId);
    const chgEl = document.getElementById(st.chgId);
    if (priceEl) { priceEl.textContent = fmtNum(last.c, 2); priceEl.className = 'chart-price ' + cls; }
    if (chgEl) {
      chgEl.textContent = `${chg >= 0 ? '+' : ''}${chg.toFixed(2)} (${chg >= 0 ? '+' : ''}${pct.toFixed(2)}%)`;
      chgEl.className = 'chart-chg ' + cls;
    }
    for (const k of ['ma5', 'ma10', 'ma20']) {
      const el = document.getElementById(st.maIds[k]);
      if (!el) continue;
      const v = bd.maFull[k][bd.maFull[k].length - 1];
      el.textContent = (v === null || v === undefined) ? '—' : fmtNum(v, 2);
    }
  }

  function makeOption(st, bd) {
    const rows = bd.data, ma = bd.ma;
    const dates = rows.map(r => r.d);
    const candles = rows.map(r => [r.o, r.c, r.l, r.h]);
    const volData = rows.map(r => ({ value: r.v, itemStyle: { color: r.c >= r.o ? 'rgba(220,38,38,.5)' : 'rgba(22,163,74,.5)' } }));
    const maSeries = ['ma5', 'ma10', 'ma20'].map(k => ({
      name: k.toUpperCase(), type: 'line', xAxisIndex: 0, yAxisIndex: 0,
      data: ma[k], symbol: 'none', silent: true, connectNulls: false,
      lineStyle: { width: 1.2, color: MA[k].color },
    }));
    return {
      animation: false,
      grid: [
        { left: 56, right: 64, top: 14, height: '56%' },
        { left: 56, right: 64, top: '73%', height: '16%' },
      ],
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'cross', label: { backgroundColor: '#111827' } },
        backgroundColor: 'rgba(17,24,39,.92)', borderWidth: 0,
        textStyle: { color: '#fff', fontSize: 12 },
        formatter: function (params) {
          if (!Array.isArray(params)) params = [params];
          const c = params.find(x => x.seriesType === 'candlestick') || params[0];
          const di = c.dataIndex;
          const row = st.rows[di];
          if (!row) return '';
          const prev = di > 0 ? st.rows[di - 1] : null;
          const pct = prev ? (row.c - prev.c) / prev.c * 100 : 0;
          const line = (lb, v, color) =>
            `<div style="display:flex;justify-content:space-between;gap:14px"><span style="color:#9ca3af">${lb}</span><span${color ? ` style="color:${color}"` : ''}>${v}</span></div>`;
          let html = line(row.d, (pct >= 0 ? '+' : '') + pct.toFixed(2) + '%', pct >= 0 ? '#fca5a5' : '#86efac');
          html += line('开', fmtNum(row.o, 2)) + line('高', fmtNum(row.h, 2))
                + line('低', fmtNum(row.l, 2)) + line('收', fmtNum(row.c, 2));
          for (const k of ['ma5', 'ma10', 'ma20']) {
            const v = st.ma[k][di];
            if (v !== null && v !== undefined) html += line(k.toUpperCase(), fmtNum(v, 2), MA[k].color);
          }
          html += line('成交量', fmtVol(row.v));
          return html;
        },
      },
      axisPointer: { link: [{ xAxisIndex: 'all' }] },
      xAxis: [
        { type: 'category', data: dates, gridIndex: 0, boundaryGap: true,
          axisLine: { lineStyle: { color: '#e5e7eb' } }, axisTick: { show: false },
          axisLabel: { show: false }, splitLine: { show: false } },
        { type: 'category', data: dates, gridIndex: 1, boundaryGap: true,
          axisLine: { lineStyle: { color: '#e5e7eb' } }, axisTick: { show: false },
          axisLabel: { color: '#9ca3af', fontSize: 10 }, splitLine: { show: false } },
      ],
      yAxis: [
        { scale: true, gridIndex: 0, position: 'right',
          splitLine: { lineStyle: { color: '#f1f2f4' } },
          axisLabel: { color: '#9ca3af', fontSize: 10, formatter: v => fmtNum(v, v >= 1000 ? 0 : 2) } },
        { scale: true, gridIndex: 1, position: 'right', splitNumber: 2,
          splitLine: { show: false },
          axisLabel: { color: '#9ca3af', fontSize: 10, formatter: fmtVol } },
      ],
      dataZoom: [
        { type: 'inside', xAxisIndex: [0, 1], start: 0, end: 100, zoomOnMouseWheel: true },
        { type: 'slider', xAxisIndex: [0, 1], start: 0, end: 100, height: 18, bottom: 4,
          borderColor: '#e5e7eb', fillerColor: 'rgba(37,99,235,.07)',
          handleStyle: { color: '#2563eb' }, moveHandleSize: 5,
          textStyle: { color: '#9ca3af', fontSize: 10 },
          dataBackground: { lineStyle: { color: '#d1d5db' }, areaStyle: { color: 'rgba(209,213,219,.25)' } },
          selectedDataBackground: { lineStyle: { color: '#2563eb' }, areaStyle: { color: 'rgba(37,99,235,.12)' } } },
      ],
      series: [
        { name: '日K', type: 'candlestick', xAxisIndex: 0, yAxisIndex: 0, data: candles, barMaxWidth: 22,
          itemStyle: { color: UP, color0: DOWN, borderColor: UP, borderColor0: DOWN } },
        ...maSeries,
        { name: '成交量', type: 'bar', xAxisIndex: 1, yAxisIndex: 1, data: volData, barMaxWidth: 22 },
      ],
    };
  }

  function render(idx) {
    const st = states[idx];
    if (!st) return;
    const bd = buildData(st.idx, st.days);
    if (!bd) {
      const el = document.getElementById(st.elId);
      if (el) el.innerHTML = '<div style="padding:20px;text-align:center;color:#9ca3af">暂无数据：请先运行 scrape.py 或 kline_data.py 生成 kline_data.js</div>';
      return;
    }
    st.rows = bd.data;
    st.ma = bd.ma;
    st.dirty = true;
    updateHeader(st, bd);
    if (ensureChart(st)) {
      st.chart.setOption(makeOption(st, bd), true);
      st.dirty = false;
    }
    // 容器不可见时先记 dirty，等 resizeAll() 时再补建
  }

  function setDays(idx, days) {
    const st = states[idx];
    if (!st) return;
    st.days = days;
    const rangeBox = document.getElementById(st.rangeBoxId);
    if (rangeBox) rangeBox.querySelectorAll('button').forEach(b => b.classList.toggle('active', Number(b.dataset.days) === days));
    render(idx);
  }

  function init(opt) {
    states[opt.idx] = {
      idx: opt.idx, elId: opt.elId, priceId: opt.priceId, chgId: opt.chgId,
      maIds: opt.maIds, rangeBoxId: opt.rangeBoxId,
      days: opt.defaultDays || DEFAULT_RANGE, chart: null, dirty: false, rows: [], ma: null,
    };
    const st = states[opt.idx];
    const rangeBox = document.getElementById(opt.rangeBoxId);
    if (rangeBox) {
      RANGES.forEach(r => {
        const b = document.createElement('button');
        b.textContent = r.label;
        b.dataset.days = r.days;
        if (r.days === st.days) b.classList.add('active');
        b.addEventListener('click', () => setDays(opt.idx, r.days));
        rangeBox.appendChild(b);
      });
    }
    render(opt.idx);
  }

  // 显示状态切换 / 窗口尺寸变化后调用：重建或重算所有图表
  function resizeAll() {
    for (const idx of Object.keys(states)) {
      const st = states[idx];
      const el = document.getElementById(st.elId);
      if (st.chart) {
        if (el && el.clientWidth > 0) st.chart.resize();
      } else if (el && el.clientWidth > 0 && st.dirty) {
        render(idx);
      }
    }
  }

  window.addEventListener('resize', resizeAll);

  window.KLINE_ECHARTS = { init, render, resizeAll, RANGES, DEFAULT_RANGE };
})();
