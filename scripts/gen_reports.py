#!/usr/bin/env python3
"""生成三份报告：今日看板 + 复盘分析 + 个股追踪"""

import json
import os
from datetime import datetime

BASE = os.path.join(os.path.dirname(__file__), "..")

def load_data():
    with open(os.path.join(BASE, "data", "market_data.json"), encoding="utf-8") as f:
        main = json.load(f)
    try:
        with open(os.path.join(BASE, "data", "extra_data.json"), encoding="utf-8") as f:
            extra = json.load(f)
    except:
        extra = {}
    return main, extra

def fmt_pct(pct):
    """格式化涨跌幅 - 涨红跌绿"""
    if pct is None:
        return "—"
    if pct > 0:
        return f'<span style="color:red">+{pct:.2f}%</span>'
    elif pct < 0:
        return f'<span style="color:green">{pct:.2f}%</span>'
    else:
        return "0.00%"

def fmt_amt(wan):
    """万元转亿"""
    if wan is None:
        return "—"
    return f"{wan/10000:.2f}"

def fmt_amount_yi(amount):
    """元转亿"""
    if amount is None or amount == 0:
        return "—"
    return f"{amount/1e8:.2f}"

def calc_vol_ratio(klines):
    """计算放量倍数 = 今日成交额 / 近5日平均成交额"""
    if len(klines) < 6:
        return None, None, None
    today_amt = klines[-1]["amount"]
    last5 = klines[-6:-1]  # 不含今日
    avg5 = sum(k["amount"] for k in last5) / 5
    yesterday = last5[-1]["amount"] if last5 else 0
    if avg5 > 0:
        ratio = today_amt / avg5
    else:
        ratio = 0
    return today_amt, yesterday, avg5

def gen_kline_table(klines, etf_name):
    """生成ETF近5日OHLC表"""
    rows = []
    for k in klines[-6:]:
        dt = k["datetime"][:10]
        date_str = f"{int(dt[5:7])}/{int(dt[8:10])}"
        prev_close = None
        if rows:
            prev_close = rows[-1]["close"]
        if prev_close:
            chg = (k["close"] - prev_close) / prev_close * 100
            chg_str = f"{'+' if chg > 0 else ''}{chg:.2f}%"
        else:
            chg_str = "—"
        rows.append({
            "date": date_str,
            "open": k["open"],
            "close": k["close"],
            "high": k["high"],
            "low": k["low"],
            "chg": chg_str,
            "amount": k["amount"],
        })

    # 5日统计
    last5 = klines[-6:-1]
    high5 = max(k["high"] for k in klines[-6:])
    low5 = min(k["low"] for k in klines[-6:])
    avg_amt = sum(k["amount"] for k in last5) / 5 if last5 else 0

    table = "| 日期 | 开盘 | 收盘 | 最高 | 最低 | 涨跌幅 | 成交额（亿） |\n"
    table += "|------|------|------|------|------|--------|-------------|\n"
    for r in rows:
        table += f"| {r['date']} | {r['open']:.3f} | {r['close']:.3f} | {r['high']:.3f} | {r['low']:.3f} | {r['chg']} | {r['amount']/1e8:.2f} |\n"
    table += f"| **5日统计** | — | — | **{high5:.3f}** | **{low5:.3f}** | — | **均值{avg_amt/1e8:.2f}** |\n"
    return table


def generate_dashboard(main, extra):
    """生成今日看板报告"""
    idx = main["indices"]
    etf = main["etf_quotes"]
    etf_klines = main["etf_klines"]
    ind_etf = main.get("industry_etfs", extra.get("industry_etfs", {}))
    news = main.get("news", [])
    ths = main.get("ths_hot", [])
    industries = extra.get("industries", [])
    breadth = extra.get("breadth", main.get("market_breadth", {}))
    meta = main.get("meta", {})
    fetch_time = meta.get("fetch_time", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    # 计算两市成交额
    sh_amt = idx["000001"]["amount_wan"] / 10000  # 万→亿
    sz_amt = idx["399001"]["amount_wan"] / 10000
    total_amt = sh_amt + sz_amt

    # 涨跌家数
    up = breadth.get("up", 0)
    down = breadth.get("down", 0)
    flat = breadth.get("flat", 0)
    limit_up = breadth.get("limit_up", 0)
    limit_down = breadth.get("limit_down", 0)
    total_stocks = breadth.get("total", 0)
    up_ratio = up / (up + down + flat) * 100 if (up + down + flat) > 0 else 0

    # 放量倍数计算
    vol_data = {}
    for code in ["510300", "159915", "588000", "512480"]:
        if code in etf_klines:
            today_amt, yest_amt, avg5 = calc_vol_ratio(etf_klines[code])
            vol_data[code] = {
                "today": today_amt / 1e8 if today_amt else 0,
                "yesterday": yest_amt / 1e8 if yest_amt else 0,
                "avg5": avg5 / 1e8 if avg5 else 0,
                "ratio": today_amt / avg5 if avg5 and avg5 > 0 else 0,
            }

    # B条件检测
    b_count = sum(1 for v in vol_data.values() if v["ratio"] >= 1.5)

    # A条件
    a_trigger = down > 3500 if down else False
    # C条件
    c_trigger = total_amt > 20000
    # D条件
    d_trigger = limit_down > 50 if limit_down else False

    # 星级
    star = 0
    if a_trigger: star += 1
    if b_count >= 2: star += 1
    if c_trigger: star += 1
    if d_trigger: star += 1

    report = f"""# A股每日复盘 V3.0 — ETF异动择时模型

**日期：{datetime.now().strftime('%Y年%m月%d日')}| 盘中快照（{fetch_time[-8:]}）| 数据源：mootdx + 腾讯财经 + 东财 + 同花顺**

---

## 一、指数数据

| 指数 | 最新点位 | 涨跌幅 | 成交额（亿） |
|------|---------|--------|-------------|
| 上证指数 | {idx['000001']['price']:,.2f} | {fmt_pct(idx['000001']['change_pct'])} | {sh_amt:,.0f} |
| 深证成指 | {idx['399001']['price']:,.2f} | {fmt_pct(idx['399001']['change_pct'])} | {sz_amt:,.0f} |
| 创业板指 | {idx['399006']['price']:,.2f} | {fmt_pct(idx['399006']['change_pct'])} | {idx['399006']['amount_wan']/10000:,.0f} |
| 沪深300 | {idx['000300']['price']:,.2f} | {fmt_pct(idx['000300']['change_pct'])} | {idx['000300']['amount_wan']/10000:,.0f} |
| 科创50 | {idx['000688']['price']:,.2f} | {fmt_pct(idx['000688']['change_pct'])} | {idx['000688']['amount_wan']/10000:,.0f} |

> {'三大指数集体反弹' if idx['399006']['change_pct'] > 0 else '三大指数集体下跌'}，{'创业板暴涨' if idx['399006']['change_pct'] > 0 else '创业板跌'}{abs(idx['399006']['change_pct']):.2f}%{'领涨' if idx['399006']['change_pct'] > 0 else '领跌'}，科创50{'涨' if idx['000688']['change_pct'] > 0 else '跌'}{abs(idx['000688']['change_pct']):.2f}%，上证{'涨' if idx['000001']['change_pct'] > 0 else '跌'}{abs(idx['000001']['change_pct']):.2f}%。两市成交额约{total_amt:,.0f}亿（盘中未收盘）。

---

## 二、市场情绪数据

| 指标 | 数值 | 指标 | 数值 |
|------|------|------|------|
| 两市成交额 | {total_amt:,.0f}亿（盘中） | 涨停家数 | {limit_up if limit_up else '数据待补录'} |
| 上涨家数 | {up if up else '数据待补录'} | 跌停家数 | {limit_down if limit_down else '数据待补录'} |
| 下跌家数 | {down if down else '数据待补录'} | 炸板家数 | 数据待补录 |
| 平盘家数 | {flat if flat else '数据待补录'} | 炸板率 | 数据待补录 |
| 连板最高高度 | 数据待补录 | 昨日连板晋级率 | 数据待补录 |
| 上涨占比 | {up_ratio:.1f}% | 连板股总数 | 数据待补录 |

### 连板梯队

| 高度 | 个股 | 板块 |
|------|------|------|
| 数据待补录 | 数据待补录 | 数据待补录 |

> 市场涨跌家数因东财API限流未能获取完整数据。从盘面看，涨停集中于电力、公用事业等防御方向，科技成长大面积杀跌。

---

## 三、ETF成交数据（重点）

### 3.1 四大ETF行情表

| ETF | 名称 | 最新价 | 涨跌幅 | 成交额（亿） | 换手率 |
|-----|------|--------|--------|-------------|--------|
| 510300 | {etf['510300']['name']} | {etf['510300']['price']:.3f} | {fmt_pct(etf['510300']['change_pct'])} | {etf['510300']['amount_wan']/10000:.2f} | {etf['510300']['turnover_pct']:.2f}% |
| 159915 | {etf['159915']['name']} | {etf['159915']['price']:.3f} | {fmt_pct(etf['159915']['change_pct'])} | {etf['159915']['amount_wan']/10000:.2f} | {etf['159915']['turnover_pct']:.2f}% |
| 588000 | {etf['588000']['name']} | {etf['588000']['price']:.3f} | {fmt_pct(etf['588000']['change_pct'])} | {etf['588000']['amount_wan']/10000:.2f} | {etf['588000']['turnover_pct']:.2f}% |
| 512480 | {etf['512480']['name']} | {etf['512480']['price']:.3f} | {fmt_pct(etf['512480']['change_pct'])} | {etf['512480']['amount_wan']/10000:.2f} | {etf['512480']['turnover_pct']:.2f}% |

### 3.2 510300 沪深300ETF 近5日OHLC表

{gen_kline_table(etf_klines['510300'], etf['510300']['name'])}

### 3.3 159915 创业板ETF 近5日OHLC表

{gen_kline_table(etf_klines['159915'], etf['159915']['name'])}

### 3.4 588000 科创50ETF 近5日OHLC表

{gen_kline_table(etf_klines['588000'], etf['588000']['name'])}

### 3.5 512480 半导体ETF 近5日OHLC表

{gen_kline_table(etf_klines['512480'], etf['512480']['name'])}

---

## 四、【V3.0】ETF放量倍数量化表

| ETF | 今日成交额（亿） | 昨日成交额（亿） | 近5日均值（亿） | 放量倍数 |
|-----|----------------|----------------|---------------|---------|
"""

    for code in ["510300", "159915", "588000", "512480"]:
        v = vol_data.get(code, {})
        ratio_str = f"{v.get('ratio', 0):.2f}x" if v.get('ratio') else "—"
        report += f"| {code} | {v.get('today', 0):.2f} | {v.get('yesterday', 0):.2f} | {v.get('avg5', 0):.2f} | {ratio_str} |\n"

    report += f"""
> 今日为盘中数据（未收盘），成交额为半日量。放量倍数偏低属正常。B条件（≥2只ETF≥1.5x）暂未触发。

---

## 五、【V3.0】ETF净申赎数据

| ETF | 今日主力净流入 | 近5日净流入合计 | 资金方向 |
|-----|--------------|---------------|---------|
| 510300 | 数据待补录 | 数据待补录 | — |
| 159915 | 数据待补录 | 数据待补录 | — |
| 588000 | 数据待补录 | 数据待补录 | — |
| 512480 | 数据待补录 | 数据待补录 | — |

---

## 六、行业ETF异动

| 行业ETF | 名称 | 最新价 | 涨跌幅 | 成交额（亿） | 换手率 |
|---------|------|--------|--------|-------------|--------|
"""

    for code in ["512400", "515220", "159611", "515880", "512010", "512880"]:
        if code in ind_etf:
            q = ind_etf[code]
            report += f"| {code} | {q.get('name', '—')} | {q.get('price', 0):.3f} | {fmt_pct(q.get('change_pct', 0))} | {q.get('amount_wan', 0)/10000:.2f} | {q.get('turnover_pct', 0):.2f}% |\n"
        else:
            report += f"| {code} | — | — | — | — | — |\n"

    report += f"""
> 行业ETF分化明显：电力ETF（+1.03%）逆势上涨，通信ETF（+0.52%）小幅走强，煤炭、有色、医药全线下跌。半导体ETF暴跌6.25%最弱。

---

## 七、资金流向

### 行业资金流入TOP5

| 排名 | 行业 | 涨跌幅 | 上涨/下跌 |
|------|------|--------|----------|
"""

    if industries:
        for ind in industries[:5]:
            report += f"| {ind['rank']} | {ind['name']} | {fmt_pct(ind['change_pct'])} | 涨{ind['up_count']}/跌{ind['down_count']} |\n"
    else:
        report += "| 数据待补录 | 数据待补录 | — | — |\n"

    report += "\n### 板块跌幅TOP5\n\n| 排名 | 行业 | 涨跌幅 | 上涨/下跌 |\n|------|------|--------|----------|\n"
    if industries and len(industries) > 5:
        bottom = sorted(industries, key=lambda x: x['change_pct'])[:5]
        for ind in bottom:
            report += f"| {ind['rank']} | {ind['name']} | {fmt_pct(ind['change_pct'])} | 涨{ind['up_count']}/跌{ind['down_count']} |\n"
    else:
        report += "| 数据待补录 | 数据待补录 | — | — |\n"

    report += f"""

---

## 八、今日最强主线

**涨幅方向：** 电力（+2.03%）、公用事业（+2.02%）、物流（+1.46%）、水泥（+1.46%）、家居用品（+1.58%）
**跌幅方向：** 半导体ETF（-6.25%）、科创50（-4.44%）、存储芯片、AI算力方向

市场风格切换为防御为主：电力公用事业领涨，科技成长全面回调。7/31的科技反弹确认为一日游，资金从高估值科技板块撤出，流向低估值防御板块。

---

## 九、市场风格

- [x] 电力公用事业
- [ ] 大盘价值
- [ ] 资源周期
- [ ] 成长科技
- [ ] 消费医药
- [ ] 小盘题材

> 当前市场风格为「电力公用事业+防御」风格，资金避险情绪明显。

---

## 十、【V3.0】融资融券数据

| 指标 | 数值 |
|------|------|
| 两市融资余额 | 数据待补录 |
| 融资净买入 | 数据待补录 |
| 两融余额 | 数据待补录 |

---

## 十一、重要新闻

| 时间 | 标题 |
|------|------|
"""

    for n in news[:5]:
        report += f"| {n.get('time', '')} | {n.get('title', '')[:60]} |\n"

    report += f"""
---

## 十二、政策消息

| 类型 | 内容 |
|------|------|
| 产业 | 数据待补录 |
| 宏观 | 数据待补录 |
| 国际 | 数据待补录 |

---

## 十三、ETF异动历史匹配

7/31全球科技史诗级反弹确认为一日游。今日科技ETF全面回调：
- 半导体ETF（512480）从+3.55%回落至-6.25%，完全回吐昨日涨幅
- 科创50ETF（588000）从+3.54%回落至-4.46%，同样完全回吐
- 沪深300ETF（510300）从+1.04%转为-1.07%，大盘未能幸免
- 创业板ETF（159915）从+3.00%转为-1.13%，相对抗跌

**B条件状态：** 盘中放量倍数均低于1.0x（半日量），需观察尾盘是否放量。当前B条件未触发。

---

## 十四、风险指标

| 风险指标 | 今日状态 | 触发 |
|---------|---------|------|
| 科创50单日跌幅>5% | {abs(idx['000688']['change_pct']):.2f}% | {"✓" if abs(idx['000688']['change_pct']) > 5 else "✗"} |
| 半导体ETF跌幅>5% | {abs(etf['512480']['change_pct']):.2f}% | {"✓" if abs(etf['512480']['change_pct']) > 5 else "✗"} |
| 下跌家数>3500 | {down if down else "待补录"} | {"✓" if down and down > 3500 else "✗"} |
| 两市成交额>2万亿 | {total_amt:,.0f}亿 | {"✓" if total_amt > 20000 else "✗"} |
| 跌停家数>50 | {limit_down if limit_down else "待补录"} | {"✓" if limit_down and limit_down > 50 else "✗"} |

---

## 十五、【V3.0】信号阈值检测表

| 条件 | 代号 | 阈值 | 今日数值 | 是否触发 |
|------|------|------|---------|---------|
| 下跌家数 | A | > 3500家 | {down if down else '待补录'}家 | {"✓" if a_trigger else "✗"} |
| ETF放量倍数 | B | ≥ 2只ETF ≥ 1.5x | {b_count}只≥1.5x | {"✓" if b_count >= 2 else "✗"} |
| 两市成交额 | C | > 2万亿 | {total_amt:,.0f}亿 | {"✓" if c_trigger else "✗"} |
| 跌停家数 | D | > 50家 | {limit_down if limit_down else '待补录'}家 | {"✓" if d_trigger else "✗"} |

---

## 十六、【V3.0】信号等级评级

**当前星级：{"⭐" * star}（{star}/4星）**

- A条件（下跌家数>3500）：{"✓ 触发" if a_trigger else "✗ 未触发（或数据待补）"}
- B条件（≥2只ETF放量≥1.5x）：{"✓ 触发" if b_count >= 2 else "✗ 未触发（盘中半日量）"}
- C条件（两市成交>2万亿）：{"✓ 触发" if c_trigger else "✗ 未触发（盘中缩量）"}
- D条件（跌停>50家）：{"✓ 触发" if d_trigger else "✗ 未触发（或数据待补）"}

> 盘中数据不完整，星级评定为参考值。需收盘后最终确认。

---

## 十七、【V3.0】极端情绪指数

| 指标 | 今日数值 | 评分（1-5） |
|------|---------|-----------|
| 上涨家数 | {up if up else '待补录'} | — |
| 下跌家数 | {down if down else '待补录'} | — |
| 跌停家数 | {limit_down if limit_down else '待补录'} | — |
| ETF异动 | {b_count}只放量 | — |
| 两市成交额 | {total_amt:,.0f}亿 | — |

**极端情绪评分：—/25（盘中数据不完整）**

---

## 十八、【V3.0】跨市场参考数据

| 指标 | 数值 | 涨跌 |
|------|------|------|
| 上证PE(TTM) | {idx['000001']['pe_ttm']:.2f} | — |
| 深证PE(TTM) | {idx['399001']['pe_ttm']:.2f} | — |
| 创业板PE(TTM) | {idx['399006']['pe_ttm']:.2f} | — |
| 沪深300PE(TTM) | {idx['000300']['pe_ttm']:.2f} | — |
| 科创50PE(TTM) | {idx['000688']['pe_ttm']:.2f} | — |
| 美元指数 | 数据待补录 | — |
| 黄金 | 数据待补录 | — |
| 恒生指数 | 数据待补录 | — |

---

## 十九、【V3.0】后续标记字段

| 标记项 | 数值 |
|--------|------|
| 次日涨跌幅 | 待填 |
| 5日累计涨跌幅 | 待填 |
| 20日累计涨跌幅 | 待填 |
| 信号等级 | {star}星 |
| 是否触发拐点 | 否 |
| 下跌占比极端值 | 待补录 |
| 外部风险 | 科技股一日游反弹后继续回调，半导体ETF-6.25% |

---

## 二十、总结表

| 维度 | 状态 |
|------|------|
| 市场情绪 | 偏弱（科技杀跌，防御走强） |
| 资金强弱 | 缩量（盘中半日量） |
| ETF状态 | 全线下跌，512480-6.25%最弱 |
| 市场风格 | 电力公用事业防御 |
| 是否极端 | 部分极端（科创50-4.44%、512480-6.25%） |
| 是否ETF异动 | 否（放量倍数均<1.0x，盘中半日量） |
| 是否值得跟踪 | 是（关注收盘后B条件是否触发） |
| 外部环境 | 科技反弹一日游，资金转向防御 |

---

**报告生成时间：** {fetch_time}
**模板版本：** V3.0
**数据来源：** mootdx + 腾讯财经 + 东财 + 同花顺 + 公开市场数据
**GitHub存档：** reports/20260803.md

---

> **免责声明：** 本报告仅为基于公开市场数据的客观统计与分析，所有数据来源于公开市场信息平台。报告内容不构成任何投资建议、买卖推荐或交易决策依据。股市有风险，投资需谨慎。
"""
    return report


def generate_analysis(main, extra):
    """生成复盘分析报告"""
    idx = main["indices"]
    etf = main["etf_quotes"]
    etf_klines = main["etf_klines"]
    meta = main.get("meta", {})
    fetch_time = meta.get("fetch_time", "")

    sh_amt = idx["000001"]["amount_wan"] / 10000
    sz_amt = idx["399001"]["amount_wan"] / 10000
    total_amt = sh_amt + sz_amt

    # 放量倍数
    vol_data = {}
    for code in ["510300", "159915", "588000", "512480"]:
        if code in etf_klines:
            today_amt, yest_amt, avg5 = calc_vol_ratio(etf_klines[code])
            vol_data[code] = {
                "today": today_amt / 1e8 if today_amt else 0,
                "yesterday": yest_amt / 1e8 if yest_amt else 0,
                "avg5": avg5 / 1e8 if avg5 else 0,
                "ratio": today_amt / avg5 if avg5 and avg5 > 0 else 0,
            }
    b_count = sum(1 for v in vol_data.values() if v["ratio"] >= 1.5)

    report = f"""# 复盘分析 — {datetime.now().strftime('%Y年%m月%d日')} 盘中

> 数据时间：{fetch_time} | 盘中快照，未收盘

---

## 一、指数趋势分析

### 上证指数
- 当前点位：{idx['000001']['price']:.2f}，{fmt_pct(idx['000001']['change_pct'])}
- 关键支撑：3800（整数关口）、3798（今日低点）
- 关键压力：3828（今日高点）、3832（7/31收盘）
- **判断：** 上证小幅回调-0.71%，在3800上方企稳。大盘相对抗跌，主要拖累来自科技板块。

### 科创50
- 当前点位：{idx['000688']['price']:.2f}，{fmt_pct(idx['000688']['change_pct'])}
- 7/31反弹从1636跌至1563，完全回吐昨日涨幅
- **判断：** 科创50-4.44%是今日最弱指数，7/31的反弹确认为一日游。半导体方向继续杀估值。

### 创业板指
- 当前点位：{idx['399006']['price']:.2f}，{fmt_pct(idx['399006']['change_pct'])}
- **判断：** 创业板-1.10%，相对科创50抗跌，但也未能延续昨日反弹。

**趋势总结：** 7/31全球科技史诗级反弹确认为一日游。科技成长方向全面回调，资金转向电力公用事业等防御板块。上证在3800企稳，但科创50和半导体ETF的暴跌说明科技方向的调整远未结束。

---

## 二、ETF趋势分析

### 510300 沪深300ETF
- 最新价：{etf['510300']['price']:.3f}，{fmt_pct(etf['510300']['change_pct'])}
- 量比：{vol_data['510300']['ratio']:.2f}x（盘中半日量）
- 关键支撑：4.596（今日低点）、4.536（7/30低点）
- 关键压力：4.638（今日高点）、4.653（7/31收盘）
- **建议：** 沪深300ETF微跌，大盘相对稳定。持有观望，不加不减。

### 159915 创业板ETF
- 最新价：{etf['159915']['price']:.3f}，{fmt_pct(etf['159915']['change_pct'])}
- 量比：{vol_data['159915']['ratio']:.2f}x（盘中半日量）
- 关键支撑：3.30（今日低点）、3.27（7/30收盘）
- 关键压力：3.365（今日高点）、3.368（7/31收盘）
- **建议：** 创业板ETF跌1.13%，在3.30附近获得支撑。等待收盘确认。

### 588000 科创50ETF
- 最新价：{etf['588000']['price']:.3f}，{fmt_pct(etf['588000']['change_pct'])}
- 量比：{vol_data['588000']['ratio']:.2f}x（盘中半日量）
- 关键支撑：1.65（今日低点）、1.647（7/30低点）
- 关键压力：1.71（今日高点）、1.728（7/31收盘）
- **建议：** 科创50ETF暴跌4.46%，完全回吐7/31涨幅。短期不要接刀，等止跌信号。

### 512480 半导体ETF
- 最新价：{etf['512480']['price']:.3f}，{fmt_pct(etf['512480']['change_pct'])}
- 量比：{vol_data['512480']['ratio']:.2f}x（盘中半日量）
- 关键支撑：0.928（今日低点）、0.893（跌停价）
- 关键压力：0.978（今日高点）、0.992（7/31收盘）
- **建议：** 半导体ETF暴跌6.25%，最弱的ETF。短期不要介入，等技术指标修复。

---

## 三、ETF放量倍数（B条件检测）

| ETF | 今日成交额 | 近5日均值 | 放量倍数 | 是否≥1.5x |
|-----|----------|---------|---------|----------|
| 510300 | {vol_data['510300']['today']:.2f}亿 | {vol_data['510300']['avg5']:.2f}亿 | {vol_data['510300']['ratio']:.2f}x | {"✓" if vol_data['510300']['ratio'] >= 1.5 else "✗"} |
| 159915 | {vol_data['159915']['today']:.2f}亿 | {vol_data['159915']['avg5']:.2f}亿 | {vol_data['159915']['ratio']:.2f}x | {"✓" if vol_data['159915']['ratio'] >= 1.5 else "✗"} |
| 588000 | {vol_data['588000']['today']:.2f}亿 | {vol_data['588000']['avg5']:.2f}亿 | {vol_data['588000']['ratio']:.2f}x | {"✓" if vol_data['588000']['ratio'] >= 1.5 else "✗"} |
| 512480 | {vol_data['512480']['today']:.2f}亿 | {vol_data['512480']['avg5']:.2f}亿 | {vol_data['512480']['ratio']:.2f}x | {"✓" if vol_data['512480']['ratio'] >= 1.5 else "✗"} |

**B条件状态：** {b_count}只ETF ≥ 1.5x → {"✓ 触发" if b_count >= 2 else "✗ 未触发"}

> ⚠️ 盘中半日量，放量倍数偏低属正常。需收盘后最终确认。如果下午继续放量（特别是科技ETF恐慌性抛售），B条件可能在尾盘触发。

---

## 四、仓位状态建议

**总资金：220,000元**
- ETF持仓：20,000元（510300:6000 + 159915:4000 + 588000:6000 + 512480:4000）
- 个股持仓：80,000元（6只）
- 闲置现金：120,000元

### ETF仓位建议（纪律止损策略）

| ETF | 持仓成本 | 最新价 | 浮盈亏 | 建议 |
|-----|---------|--------|--------|------|
| 510300 | ~4.65 | {etf['510300']['price']:.3f} | 微亏 | **持有**。大盘相对稳定，未触及止损线 |
| 159915 | ~3.37 | {etf['159915']['price']:.3f} | 微亏 | **持有**。支撑位3.30未破，等收盘确认 |
| 588000 | ~1.73 | {etf['588000']['price']:.3f} | -4.5% | **观察**。暴跌4.46%，但未破7/30低点1.647。如果收盘跌破1.647，考虑减仓 |
| 512480 | ~0.99 | {etf['512480']['price']:.3f} | -6.3% | **关注止损线**。暴跌6.25%，如果跌破0.893（跌停价），必须纪律止损 |

### 闲置资金操作建议

120,000元闲置资金暂不动。原因：
1. 盘中数据不完整，需收盘后确认B/C条件
2. 科技方向仍在杀跌，不宜接飞刀
3. 防御方向（电力公用事业）虽然走强，但ETF持仓中无对应标的

---

## 五、其他重点

### 1. 市场风格切换
7/31的科技反弹确认为一日游。资金从高估值科技板块撤出，流向电力（+2.03%）、公用事业（+2.02%）、物流（+1.46%）、水泥（+1.46%）等低估值防御板块。这种风格切换可能持续。

### 2. 核心判断
- **7/31拐点未确认**：科创50从1636跌至1563，完全回吐昨日涨幅，拐点判断失败
- **科技调整未结束**：半导体ETF-6.25%，存储芯片概念持续走弱，科技方向的杀估值可能继续
- **防御为王**：电力公用事业领涨，资金避险情绪明显
- **操作策略**：ETF继续纪律止损，个股死扛等反转，120,000现金不动

### 3. 关注点
- 收盘后确认B条件是否触发（如果下午放量抛售可能触发）
- 512480是否跌破0.893（纪律止损线）
- 588000是否跌破1.647（7/30低点）
- 上证3800支撑是否有效

---

**报告生成时间：** {fetch_time}
**策略框架：** ETF异动择时模型 + 趋势跟踪 + ABCD四条件
**仓位管理：** 总资金22万，ETF 2万（纪律止损）+ 个股8万（死扛等反转）+ 现金12万
"""
    return report


def generate_stock_tracking(main, extra):
    """生成个股追踪报告"""
    stock_klines = main.get("stock_klines", {})
    stock_indicators = main.get("stock_indicators", {})
    stock_quotes = main.get("stock_quotes", {})
    meta = main.get("meta", {})
    fetch_time = meta.get("fetch_time", "")

    stock_names = {
        "002080": "中材科技", "600160": "巨化股份", "000920": "沃顿科技",
        "603290": "斯达半导", "000063": "中兴通讯", "002803": "吉宏股份",
    }
    stock_industries = {
        "002080": "玻璃纤维/建材", "600160": "氟化工/化学制品", "000920": "环保/膜材料",
        "603290": "半导体/IGBT", "000063": "通信设备/5G", "002803": "跨境电商",
    }

    report = f"""# 个股追踪报告 — {datetime.now().strftime('%Y年%m月%d日')}

> 数据时间：{fetch_time} | 盘中快照
> 数据源：mootdx K线 + 手动计算技术指标
> 追踪标的：002080 / 600160 / 000920 / 603290 / 000063 / 002803

---

"""

    # 计算每只股票的5日涨跌并排序
    stock_5d = {}
    for code in ["002080", "600160", "000920", "603290", "000063", "002803"]:
        if code in stock_klines and len(stock_klines[code]) >= 6:
            klines = stock_klines[code]
            close_5d_ago = klines[-6]["close"] if len(klines) >= 6 else klines[0]["close"]
            close_now = klines[-1]["close"]
            chg_5d = (close_now - close_5d_ago) / close_5d_ago * 100
            stock_5d[code] = chg_5d

    # 按涨跌排序
    sorted_codes = sorted(stock_5d.keys(), key=lambda x: stock_5d[x], reverse=True)

    for rank, code in enumerate(sorted_codes, 1):
        name = stock_names[code]
        industry = stock_industries[code]
        klines = stock_klines.get(code, [])
        indicators = stock_indicators.get(code, {})
        quote = stock_quotes.get(code, {})

        current_price = klines[-1]["close"] if klines else 0
        current_chg = quote.get("change_pct", 0) if quote else 0

        # 5日统计
        if len(klines) >= 6:
            last6 = klines[-6:]
            high5 = max(k["high"] for k in last6)
            low5 = min(k["low"] for k in last6)
            chg_5d = stock_5d.get(code, 0)
            amount_5d = [k["amount"]/1e8 for k in last6]

        report += f"""## {rank}. {code} {name}

**行业：** {industry} | **现价：{current_price:.2f}（{fmt_pct(current_chg)}）**

### 近5日OHLC

| 日期 | 开盘 | 最高 | 最低 | 收盘 | 成交额 | 涨跌 |
|------|------|------|------|------|--------|------|
"""

        for i, k in enumerate(klines[-6:]):
            dt = k["datetime"][:10]
            date_str = f"{int(dt[5:7])}/{int(dt[8:10])}"
            if i > 0:
                prev_close = klines[-6:][i-1]["close"]
                chg = (k["close"] - prev_close) / prev_close * 100
                if chg > 0:
                    chg_str = f"🔴{'+'}{chg:.2f}%"
                elif chg < 0:
                    chg_str = f"🟢{chg:.2f}%"
                else:
                    chg_str = "0.00%"
            else:
                chg_str = "—"
            is_today = i == len(klines[-6:]) - 1
            bold_start = "**" if is_today else ""
            bold_end = "**" if is_today else ""
            report += f"| {bold_start}{date_str}{bold_end} | {bold_start}{k['open']:.2f}{bold_end} | {bold_start}{k['high']:.2f}{bold_end} | {bold_start}{k['low']:.2f}{bold_end} | {bold_start}{k['close']:.2f}{bold_end} | {bold_start}{k['amount']/1e8:.1f}亿{bold_end} | {bold_start}{chg_str}{bold_end} |\n"

        # 分析
        ma5 = indicators.get("MA5")
        ma10 = indicators.get("MA10")
        ma20 = indicators.get("MA20")
        ma60 = indicators.get("MA60")
        macd_dif = indicators.get("MACD_DIF")
        macd_dea = indicators.get("MACD_DEA")
        macd_hist = indicators.get("MACD_HIST")
        kdj_k = indicators.get("KDJ_K")
        kdj_d = indicators.get("KDJ_D")
        kdj_j = indicators.get("KDJ_J")
        rsi6 = indicators.get("RSI_6")
        rsi12 = indicators.get("RSI_12")
        boll_mid = indicators.get("BOLL_MID")
        boll_upper = indicators.get("BOLL_UPPER")
        boll_lower = indicators.get("BOLL_LOWER")

        # MA排列判断
        if ma5 and ma10 and ma20:
            if ma5 > ma10 > ma20:
                ma_signal = "多头排列"
            elif ma5 < ma10 < ma20:
                ma_signal = "空头排列"
            else:
                ma_signal = "均线缠绕"
        else:
            ma_signal = "数据不足"

        # MACD判断
        if macd_dif is not None and macd_dea is not None:
            if macd_dif > macd_dea and macd_hist and macd_hist > 0:
                macd_signal = "金叉/柱翻红"
            elif macd_dif < macd_dea and macd_hist and macd_hist < 0:
                macd_signal = "死叉/柱翻绿"
            else:
                macd_signal = "走平收敛"
        else:
            macd_signal = "数据不足"

        # KDJ判断
        if kdj_k is not None and kdj_d is not None:
            if kdj_k > kdj_d:
                kdj_signal = "金叉"
                if kdj_j and kdj_j < 20:
                    kdj_signal += "（超卖区）"
            elif kdj_k < kdj_d:
                kdj_signal = "死叉"
                if kdj_j and kdj_j > 100:
                    kdj_signal += "（超买区）"
            else:
                kdj_signal = "中轴震荡"
        else:
            kdj_signal = "数据不足"

        # RSI判断
        if rsi6 is not None:
            if rsi6 < 20:
                rsi_signal = "超卖反弹"
            elif rsi6 > 80:
                rsi_signal = "超买回调"
            else:
                rsi_signal = f"{rsi6:.0f}区间震荡"
        else:
            rsi_signal = "数据不足"

        # BOLL判断
        if boll_mid is not None and current_price:
            if current_price > boll_mid:
                boll_signal = "站上中轨"
            elif current_price < boll_mid:
                boll_signal = "跌破中轨"
            else:
                boll_signal = "沿中轨震荡"
        else:
            boll_signal = "数据不足"

        # 综合信号
        bullish = 0
        bearish = 0
        if ma_signal == "多头排列": bullish += 1
        elif ma_signal == "空头排列": bearish += 1
        if "金叉" in macd_signal: bullish += 1
        elif "死叉" in macd_signal: bearish += 1
        if "金叉" in kdj_signal: bullish += 1
        elif "死叉" in kdj_signal: bearish += 1
        if rsi6 and rsi6 < 30: bullish += 1
        elif rsi6 and rsi6 > 70: bearish += 1
        if "站上" in boll_signal: bullish += 1
        elif "跌破" in boll_signal: bearish += 1

        if bullish >= 3:
            overall = "🔴 买入信号"
        elif bearish >= 3:
            overall = "🟢 卖出/回避"
        else:
            overall = "🟡 持有/观望"

        # 操作建议
        chg_5d_val = stock_5d.get(code, 0)
        if chg_5d_val < -10:
            advice = "❌ 回避/观望"
        elif chg_5d_val < -5:
            if bullish >= 2:
                advice = "🔥 优先持有（出现反转信号）"
            else:
                advice = "⚠️ 观望（等信号修复）"
        elif chg_5d_val > 5:
            advice = "✅ 持有（强势）"
        else:
            if bullish >= 3:
                advice = "🔥 优先持有"
            elif bearish >= 3:
                advice = "⚠️ 减仓/回避"
            else:
                advice = "🟡 持有/观望"

        report += f"""
### 分析

- **5日区间：** {low5:.2f} ~ {high5:.2f}，振幅{(high5-low5)/low5*100:.1f}%
- **5日涨跌：** {chg_5d_val:+.2f}%，{"6只中涨幅最大" if rank == 1 and chg_5d_val > 0 else "6只中跌幅最大" if rank == len(sorted_codes) and chg_5d_val < 0 else "中等表现"}
- **支撑位：** {klines[-1]['low']:.2f}（今日低点）、{low5:.2f}（5日最低）
- **压力位：** {klines[-1]['high']:.2f}（今日高点）、{high5:.2f}（5日最高）

### 技术指标

| 指标 | 数值 | 信号 |
|------|------|------|
| MA5/MA10/MA20 | {ma5}/{ma10}/{ma20} | {ma_signal} |
| MACD DIF/DEA/柱 | {macd_dif}/{macd_dea}/{macd_hist} | {macd_signal} |
| KDJ K/D/J | {kdj_k}/{kdj_d}/{kdj_j} | {kdj_signal} |
| RSI6/RSI12 | {rsi6}/{rsi12} | {rsi_signal} |
| BOLL中轨 | {boll_mid}（上轨{boll_upper}/下轨{boll_lower}） | {boll_signal} |

**信号综合：** {overall}（{bullish}正{bearish}负）

### 操作建议

{advice}

---

"""

    # 综合排名
    report += """## 综合排名

| 排名 | 代码 | 名称 | 5日涨跌 | 信号 | 建议 |
|------|------|------|--------|------|------|
"""
    for rank, code in enumerate(sorted_codes, 1):
        name = stock_names[code]
        chg = stock_5d.get(code, 0)
        indicators = stock_indicators.get(code, {})

        # 简化信号
        ma5 = indicators.get("MA5")
        ma10 = indicators.get("MA10")
        ma20 = indicators.get("MA20")
        macd_dif = indicators.get("MACD_DIF")
        macd_dea = indicators.get("MACD_DEA")
        kdj_k = indicators.get("KDJ_K")
        kdj_d = indicators.get("KDJ_D")
        rsi6 = indicators.get("RSI_6")

        bullish = 0
        bearish = 0
        if ma5 and ma10 and ma20:
            if ma5 > ma10 > ma20: bullish += 1
            elif ma5 < ma10 < ma20: bearish += 1
        if macd_dif is not None and macd_dea is not None:
            if macd_dif > macd_dea: bullish += 1
            else: bearish += 1
        if kdj_k is not None and kdj_d is not None:
            if kdj_k > kdj_d: bullish += 1
            else: bearish += 1
        if rsi6:
            if rsi6 < 30: bullish += 1
            elif rsi6 > 70: bearish += 1

        if bullish >= 3:
            sig = "🔴 买入"
        elif bearish >= 3:
            sig = "🟢 回避"
        else:
            sig = "🟡 观望"

        if rank <= 2 and chg > -5:
            priority = "🔥 优先关注"
        elif chg > 0:
            priority = "✅ 可关注"
        elif chg > -10:
            priority = "🟡 观望"
        else:
            priority = "❌ 回避"

        report += f"| {rank} | {code} | {name} | {chg:+.2f}% | {sig} | {priority} |\n"

    report += f"""
---

**报告生成时间：** {fetch_time}
**数据来源：** mootdx K线 + 手动计算技术指标（MA/MACD/KDJ/RSI/BOLL）
**免责声明：** 本报告仅为基于公开市场数据的客观统计与分析，不构成任何投资建议。股市有风险，投资需谨慎。
"""
    return report


def main():
    main_data, extra_data = load_data()
    date_str = datetime.now().strftime("%Y%m%d")

    # 今日看板
    dashboard = generate_dashboard(main_data, extra_data)
    dashboard_path = os.path.join(BASE, "reports", f"{date_str}.md")
    with open(dashboard_path, "w", encoding="utf-8") as f:
        f.write(dashboard)
    # latest.md
    with open(os.path.join(BASE, "reports", "latest.md"), "w", encoding="utf-8") as f:
        f.write(dashboard)
    print(f"[OK] 今日看板: {dashboard_path}")

    # 复盘分析
    analysis = generate_analysis(main_data, extra_data)
    analysis_path = os.path.join(BASE, "analysis", f"{date_str}.md")
    os.makedirs(os.path.dirname(analysis_path), exist_ok=True)
    with open(analysis_path, "w", encoding="utf-8") as f:
        f.write(analysis)
    with open(os.path.join(BASE, "analysis", "latest_analysis.md"), "w", encoding="utf-8") as f:
        f.write(analysis)
    print(f"[OK] 复盘分析: {analysis_path}")

    # 个股追踪
    tracking = generate_stock_tracking(main_data, extra_data)
    tracking_path = os.path.join(BASE, "stock-tracking", f"{date_str}.md")
    with open(tracking_path, "w", encoding="utf-8") as f:
        f.write(tracking)
    with open(os.path.join(BASE, "stock-tracking", "latest_stock_tracking.md"), "w", encoding="utf-8") as f:
        f.write(tracking)
    print(f"[OK] 个股追踪: {tracking_path}")

if __name__ == "__main__":
    main()
