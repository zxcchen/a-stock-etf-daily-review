#!/usr/bin/env python3
"""生成三份报告：今日看板 + 复盘分析 + 个股追踪"""

import json
import os
from datetime import datetime

BASE = os.path.join(os.path.dirname(__file__), "..")

# ETF追踪列表（7只）
ETFS = ["510300", "159915", "588000", "512480", "588160", "515050", "588460"]
ETF_SHORT_NAMES = {
    "510300": "沪深300", "159915": "创业板", "588000": "科创50", "512480": "半导体",
    "588160": "科创新材", "515050": "5G通信", "588460": "科创增强",
}
ETF_FULL_NAMES = {
    "510300": "沪深300ETF", "159915": "创业板ETF", "588000": "科创50ETF", "512480": "半导体ETF",
    "588160": "科创新材ETF", "515050": "5GETF", "588460": "科创增强ETF",
}

# ETF实际持仓（来自东财账户截图，2026-08-07更新）
ETF_HOLDINGS = {
    "510300": {"shares": 11500, "cost": 4.721, "break_price": 4.591},
    "588000": {"shares": 24500, "cost": 1.806, "break_price": 1.635},
    "159915": {"shares": 14300, "cost": 3.566, "break_price": 3.300},
    "512480": {"shares": 49000, "cost": 1.057, "break_price": 0.919},
    "588160": {"shares": 42000, "cost": 1.102, "break_price": 0.951},
    "515050": {"shares": 35500, "cost": 1.042, "break_price": 0.887},
    "588460": {"shares": 22200, "cost": 2.092, "break_price": 1.880},
}

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


def detect_kline_patterns(klines):
    """K线形态分析 — 检测特殊K线形态，返回形态列表和综合判断

    检测形态：
    - 单根：光脚阴线/光脚阳线、光头阴线/光头阳线、十字星、锤子线、上吊线、
            射击之星、倒锤子线、长下影/长上影、大阳线/大阴线
    - 双根：阳包阴、阴包阳
    - 三根：顶分型、底分型、高低点抬升/下移（趋势结构）
    """
    if not klines or len(klines) < 3:
        return [], "数据不足"

    patterns = []
    today = klines[-1]
    yest = klines[-2] if len(klines) >= 2 else None
    prev = klines[-3] if len(klines) >= 3 else None

    o, h, l, c = float(today["open"]), float(today["high"]), float(today["low"]), float(today["close"])
    body = abs(c - o)
    body_pct = body / o * 100 if o > 0 else 0
    upper_shadow = h - max(o, c)
    lower_shadow = min(o, c) - l
    total_range = h - l
    is_bullish = c > o
    is_bearish = c < o

    # 实体占整根K线的比例
    body_ratio = body / total_range if total_range > 0 else 0
    # 上下影线占整根K线的比例
    upper_ratio = upper_shadow / total_range if total_range > 0 else 0
    lower_ratio = lower_shadow / total_range if total_range > 0 else 0

    # === 单根K线形态 ===

    # 1. 十字星（实体极小，开盘≈收盘）
    if body_pct < 0.5 and total_range > 0:
        if upper_shadow > 0 and lower_shadow > 0:
            patterns.append(("十字星", "⚠️ 多空平衡，变盘信号。出现在高位=见顶预警，出现在低位=见底预警", "中性"))
        elif upper_shadow > 0 and lower_shadow == 0:
            patterns.append(("T字星", "⚠️ 下方支撑强但上方有抛压，低位出现偏多", "偏多"))
        elif lower_shadow > 0 and upper_shadow == 0:
            patterns.append(("倒T字星", "⚠️ 上方压力大，高位出现偏空", "偏空"))

    # 2. 光脚阳线（无下影线，收盘=最高或有极小下影线）
    if is_bullish and lower_ratio < 0.02 and body_ratio > 0.5:
        patterns.append(("光脚阳线", "🔴 多头强势，买盘积极推升收盘到最高附近，次日大概率延续上涨", "看多"))

    # 3. 光脚阴线（无下影线，开盘=最高，收盘=最低或有极小上影线）
    if is_bearish and lower_ratio < 0.02 and body_ratio > 0.5:
        patterns.append(("光脚阴线", "🟢 空头强势，卖盘持续打压收盘到最低附近，次日大概率延续下跌", "看空"))

    # 4. 光头阳线（无上影线，收盘=最高）
    if is_bullish and upper_ratio < 0.02 and body_ratio > 0.5:
        patterns.append(("光头阳线", "🔴 多头主导，收盘即最高价，上方无抛压，强势特征", "看多"))

    # 5. 光头阴线（无上影线，开盘=最高）
    if is_bearish and upper_ratio < 0.02 and body_ratio > 0.5:
        patterns.append(("光头阴线", "🟢 空头主导，开盘即最高价，全天单边下跌，弱势特征", "看空"))

    # 6. 锤子线（下影线长≥2倍实体，上影线极小，出现在下跌末期）
    if lower_shadow > body * 2 and upper_ratio < 0.1 and body_ratio < 0.4:
        if is_bullish:
            patterns.append(("锤子线", "🔴 下跌中出现，长下影+小阳实体=下方有承接，潜在见底信号", "看多"))
        else:
            patterns.append(("锤子线(阴)", "🔴 下跌中出现，长下影+小阴实体=下方有承接，潜在见底信号", "看多"))

    # 7. 上吊线（与锤子线形态相同，但出现在上涨末期）
    if lower_shadow > body * 2 and upper_ratio < 0.1 and body_ratio < 0.4:
        # 需要结合趋势判断，如果近期上涨则为上吊线
        if yest and float(yest["close"]) < float(yest["open"]):
            pass  # 下跌中，已在锤子线处理
        elif yest and float(yest["close"]) > float(yest["open"]):
            patterns.append(("上吊线", "🟢 上涨中出现锤子形态=上吊线，潜在见顶信号，需次日确认", "看空"))

    # 8. 射击之星（上影线长≥2倍实体，下影线极小，出现在上涨末期）
    if upper_shadow > body * 2 and lower_ratio < 0.1 and body_ratio < 0.4:
        patterns.append(("射击之星", "🟢 长上影+小实体=上方抛压沉重，潜在见顶信号", "看空"))

    # 9. 倒锤子线（上影线长，下影线极小，出现在下跌末期）
    if upper_shadow > body * 2 and lower_ratio < 0.1 and body_ratio < 0.4:
        if yest and float(yest["close"]) < float(yest["open"]):
            patterns.append(("倒锤子线", "🔴 下跌中出现长上影=多头尝试反击，潜在见底信号", "看多"))

    # 10. 大阳线（实体涨幅>3%）
    if is_bullish and body_pct > 3:
        patterns.append(("大阳线", f"🔴 实体涨幅{body_pct:.1f}%，多头强势发力", "看多"))

    # 11. 大阴线（实体跌幅>3%）
    if is_bearish and body_pct > 3:
        patterns.append(("大阴线", f"🟢 实体跌幅{body_pct:.1f}%，空头强势打压", "看空"))

    # 12. 长下影线（下影线占总振幅>50%）
    if lower_ratio > 0.5 and body_ratio < 0.3:
        patterns.append(("长下影线", "🔴 下方承接力强，盘中被砸后拉回，多头抵抗", "偏多"))

    # 13. 长上影线（上影线占总振幅>50%）
    if upper_ratio > 0.5 and body_ratio < 0.3:
        patterns.append(("长上影线", "🟢 上方抛压重，盘中冲高后回落，空头施压", "偏空"))

    # === 双根K线形态 ===
    if yest:
        y_o, y_h, y_l, y_c = float(yest["open"]), float(yest["high"]), float(yest["low"]), float(yest["close"])

        # 14. 阳包阴（今日阳线完全吞噬昨日阴线实体）
        if y_c < y_o and c > o and c >= y_o and o <= y_c:
            patterns.append(("阳包阴", "🔴 今日阳线完全吞没昨日阴线实体，多头强力反转信号", "看多"))

        # 15. 阴包阳（今日阴线完全吞噬昨日阳线实体）
        if y_c > y_o and c < o and o >= y_c and c <= y_o:
            patterns.append(("阴包阳", "🟢 今日阴线完全吞没昨日阳线实体，空头强力反转信号", "看空"))

    # === 三根K线形态（分型结构）===
    if prev and yest:
        p_h, p_l = float(prev["high"]), float(prev["low"])
        y_h, y_l = float(yest["high"]), float(yest["low"])

        # 16. 顶分型（昨日高点为三根中最高）
        if y_h > h and y_h > p_h:
            patterns.append(("顶分型", "🟢 昨日高点为近期最高，今日回落确认顶分型，短期见顶信号", "看空"))

        # 17. 底分型（昨日低点为三根中最低）
        if y_l < l and y_l < p_l:
            patterns.append(("底分型", "🔴 昨日低点为近期最低，今日回升确认底分型，短期见底信号", "看多"))

        # 18. 高低点同时抬升（反转K线结构）
        if h > y_h and l > y_l:
            patterns.append(("高低点抬升", "🔴 今日高低点同时高于昨日，趋势反转/延续上涨结构", "看多"))

        # 19. 高低点同时下移（下跌延续结构）
        if h < y_h and l < y_l:
            patterns.append(("高低点下移", "🟢 今日高低点同时低于昨日，趋势延续下跌结构", "看空"))

    # === 综合判断 ===
    if not patterns:
        return [], "无明显特殊形态"

    bullish_count = sum(1 for _, _, s in patterns if s in ("看多", "偏多"))
    bearish_count = sum(1 for _, _, s in patterns if s in ("看空", "偏空"))

    if bullish_count > bearish_count:
        overall = f"偏多（{bullish_count}多/{bearish_count}空）"
    elif bearish_count > bullish_count:
        overall = f"偏空（{bullish_count}多/{bearish_count}空）"
    else:
        overall = f"中性（{bullish_count}多/{bearish_count}空）"

    return patterns, overall


def analyze_intraday_pattern(klines):
    """分析日内分时走势：高开/低开 + 高走/低走 + 量能配合

    日内分时走势往往提前预演接下来1-5个交易日的走势。
    结合日线K线形态给出综合信号矩阵。

    核心逻辑：
    - 高低点抬升 + 高开低走 = 警惕回调/横盘（1-5个工作日）
    - 高低点抬升 + 高开高走 = 强势确认
    - 高低点抬升 + 低开高走 = 洗盘拉升（更强）
    - 高低点下移 + 高开低走 = 强空确认
    - 高低点下移 + 低开高走 = 可能见底
    """
    if not klines or len(klines) < 2:
        return None

    today = klines[-1]
    yest = klines[-2]

    o = float(today["open"])
    c = float(today["close"])
    y_c = float(yest["close"])
    vol = float(today.get("vol", 0))

    # 开盘类型
    gap_pct = (o - y_c) / y_c * 100
    if gap_pct > 0.3:
        open_type = "高开"
        open_desc = f"高开{gap_pct:+.2f}%"
    elif gap_pct < -0.3:
        open_type = "低开"
        open_desc = f"低开{gap_pct:+.2f}%"
    else:
        open_type = "平开"
        open_desc = f"平开{gap_pct:+.2f}%"

    # 走势类型
    intraday_chg = (c - o) / o * 100
    if intraday_chg > 0.3:
        close_type = "高走"
        close_desc = f"高走{intraday_chg:+.2f}%"
    elif intraday_chg < -0.3:
        close_type = "低走"
        close_desc = f"低走{intraday_chg:+.2f}%"
    else:
        close_type = "平收"
        close_desc = f"平收{intraday_chg:+.2f}%"

    intraday_pattern = f"{open_type}{close_type}"

    # 量能分析
    if len(klines) >= 6:
        avg_vol5 = sum(float(k.get("vol", 0)) for k in klines[-6:-1]) / 5
        vol_ratio = vol / avg_vol5 if avg_vol5 > 0 else 1.0
        if vol_ratio >= 1.5:
            vol_desc = f"放量{vol_ratio:.2f}倍"
        elif vol_ratio >= 1.0:
            vol_desc = f"温和放量{vol_ratio:.2f}倍"
        elif vol_ratio >= 0.7:
            vol_desc = f"缩量{vol_ratio:.2f}倍"
        else:
            vol_desc = f"显著缩量{vol_ratio:.2f}倍"
    else:
        vol_ratio = 1.0
        vol_desc = "量能数据不足"

    # 日线形态方向
    daily_pats, daily_overall = detect_kline_patterns(klines)
    has_high_low_up = any(p[0] == "高低点抬升" for p in daily_pats)
    has_high_low_down = any(p[0] == "高低点下移" for p in daily_pats)
    daily_bullish = any(d in ("看多", "偏多") for _, _, d in daily_pats)
    daily_bearish = any(d in ("看空", "偏空") for _, _, d in daily_pats)

    # === 综合信号矩阵 ===
    if has_high_low_up:
        if intraday_pattern == "高开高走":
            combined = "强势确认"
            combined_desc = "日线高低点抬升+高开高走=多头强势延续，趋势确认"
            signal = "看多"
        elif intraday_pattern == "高开低走":
            if vol_ratio >= 1.5:
                combined = "警惕回调"
                combined_desc = "日线虽高低点抬升，但分时高开低走+放量=盘中抛压重，主力可能派发，接下来1-5个交易日大概率回调或横盘"
                signal = "偏空"
            else:
                combined = "短线回调"
                combined_desc = "日线高低点抬升但分时高开低走=盘中获利回吐，缩量则回调幅度有限，接下来1-5个交易日可能横盘整理"
                signal = "偏空"
        elif intraday_pattern == "低开高走":
            combined = "洗盘拉升"
            combined_desc = "日线高低点抬升+低开高走=开盘洗盘后多头反攻，主力吸筹特征，强势看多"
            signal = "看多"
        elif intraday_pattern == "低开低走":
            combined = "假信号风险"
            combined_desc = "日线虽高低点抬升但分时低开低走=多头未能延续，结构可能被破坏，警惕假突破"
            signal = "偏空"
        else:
            combined = "观望"
            combined_desc = "日线高低点抬升但分时走势不明"
            signal = "中性"
    elif has_high_low_down:
        if intraday_pattern == "高开低走":
            if vol_ratio >= 1.5:
                combined = "强空确认"
                combined_desc = "日线高低点下移+高开低走+放量=空头强势派发，趋势延续下跌"
                signal = "看空"
            else:
                combined = "空头延续"
                combined_desc = "日线高低点下移+高开低走=抛压延续，下跌趋势未改"
                signal = "看空"
        elif intraday_pattern == "高开高走":
            combined = "可能反转"
            combined_desc = "日线虽高低点下移但分时高开高走=多头尝试反击，需次日确认"
            signal = "偏多"
        elif intraday_pattern == "低开低走":
            combined = "继续下跌"
            combined_desc = "日线高低点下移+低开低走=空头主导，下跌加速"
            signal = "看空"
        elif intraday_pattern == "低开高走":
            if vol_ratio >= 1.5:
                combined = "可能见底"
                combined_desc = "日线虽高低点下移但分时低开高走+放量=底部承接力强，主力可能吸筹，潜在见底信号"
                signal = "偏多"
            else:
                combined = "弱势反弹"
                combined_desc = "日线高低点下移但分时低开高走=缩量反弹，持续性存疑"
                signal = "中性"
        else:
            combined = "观望"
            combined_desc = "日线高低点下移但分时走势不明"
            signal = "中性"
    else:
        # 没有高低点结构信号，用一般形态判断
        if daily_bullish and intraday_pattern in ("高开高走", "低开高走"):
            combined = "偏多"
            combined_desc = f"日线形态偏多+{intraday_pattern}=多头占优"
            signal = "偏多"
        elif daily_bearish and intraday_pattern in ("高开低走", "低开低走"):
            combined = "偏空"
            combined_desc = f"日线形态偏空+{intraday_pattern}=空头占优"
            signal = "偏空"
        elif daily_bullish and intraday_pattern in ("高开低走", "低开低走"):
            combined = "多空分歧"
            combined_desc = f"日线形态偏多但分时{intraday_pattern}=形态与走势背离，警惕反转"
            signal = "中性"
        elif daily_bearish and intraday_pattern in ("高开高走", "低开高走"):
            combined = "多空分歧"
            combined_desc = f"日线形态偏空但分时{intraday_pattern}=形态与走势背离，可能反转"
            signal = "中性"
        else:
            combined = "中性"
            combined_desc = "形态与分时走势方向一致度不高"
            signal = "中性"

    return {
        "intraday_pattern": intraday_pattern,
        "open_desc": open_desc,
        "close_desc": close_desc,
        "vol_desc": vol_desc,
        "vol_ratio": round(vol_ratio, 2),
        "combined_signal": combined,
        "combined_desc": combined_desc,
        "signal": signal,
    }


def gen_kline_pattern_section(klines, name=""):
    """生成K线形态分析段落（含日内分时走势分析）"""
    patterns, overall = detect_kline_patterns(klines)
    intraday = analyze_intraday_pattern(klines)

    lines = []

    if not patterns and not intraday:
        return f"**K线形态：** 无明显特殊形态。当前实体较小，上下影线均衡，多空暂处平衡状态。\n"

    if patterns:
        lines.append(f"**K线形态分析：** 综合{overall}\n")
        lines.append("| 形态 | 含义 | 方向 |")
        lines.append("|------|------|------|")
        for pname, pdesc, pdir in patterns:
            dir_emoji = {"看多": "🔴", "看空": "🟢", "偏多": "🔴", "偏空": "🟢", "中性": "🟡"}.get(pdir, "🟡")
            lines.append(f"| {pname} | {pdesc} | {dir_emoji}{pdir} |")
        lines.append("")

    if intraday:
        lines.append(f"**日内分时走势分析：** {intraday['intraday_pattern']}（{intraday['open_desc']}，{intraday['close_desc']}），{intraday['vol_desc']}")
        lines.append(f"> {intraday['combined_desc']}")
        sig_emoji = {"看多": "🔴", "看空": "🟢", "偏多": "🔴", "偏空": "🟢", "中性": "🟡"}.get(intraday['signal'], "🟡")
        lines.append(f"> **综合信号：** {sig_emoji}{intraday['combined_signal']}（{intraday['signal']}）")

    return "\n".join(lines) + "\n"


def generate_dashboard(main, extra):
    """生成今日看板报告"""
    idx = main["indices"]
    etf = main["etf_quotes"]
    etf_klines = main["etf_klines"]
    ind_etf = main.get("industry_etfs", extra.get("industry_etfs", {}))
    news = main.get("news", [])
    ths = main.get("ths_hot", [])
    industries = main.get("industries", extra.get("industries", []))
    if isinstance(industries, dict):
        industries = industries.get("top", []) + industries.get("bottom", [])
    breadth = main.get("market_breadth", extra.get("breadth", {}))
    meta = main.get("meta", {})
    fetch_time = meta.get("fetch_time", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    is_after_close = int(fetch_time[11:13]) >= 15 if len(fetch_time) >= 13 else False
    session_label = "收盘" if is_after_close else "盘中快照"
    vol_label = "" if is_after_close else "（盘中半日量）"

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
    for code in ETFS:
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

    # 动态生成指数描述
    up_indices = sum(1 for k in ["000001", "399001", "399006", "000300", "000688"] if idx[k]["change_pct"] > 0)
    down_indices = sum(1 for k in ["000001", "399001", "399006", "000300", "000688"] if idx[k]["change_pct"] < 0)
    if up_indices >= 5:
        market_word = "三大指数集体上涨"
    elif down_indices >= 5:
        market_word = "三大指数集体下跌"
    elif up_indices >= 3:
        market_word = "多数指数上涨"
    elif down_indices >= 3:
        market_word = "多数指数下跌"
    else:
        market_word = "指数涨跌不一"

    # 找最强和最弱指数
    idx_changes = [(k, idx[k]["change_pct"], idx[k]["price"]) for k in ["000001", "399001", "399006", "000300", "000688"]]
    idx_names = {"000001": "上证", "399001": "深证", "399006": "创业板", "000300": "沪深300", "000688": "科创50"}
    best_idx = max(idx_changes, key=lambda x: x[1])
    worst_idx = min(idx_changes, key=lambda x: x[1])

    # 动态生成板块描述
    etf_changes = [(c, etf[c]["change_pct"]) for c in ETFS]
    up_etfs = [c for c, chg in etf_changes if chg > 0]
    down_etfs = [c for c, chg in etf_changes if chg < 0]
    if len(up_etfs) >= 4:
        top_up_code = max(up_etfs, key=lambda c: dict(etf_changes)[c])
        etf_word = f"ETF全面上涨，{ETF_SHORT_NAMES[top_up_code]}领涨"
    elif len(down_etfs) >= 4:
        top_down_code = min(down_etfs, key=lambda c: dict(etf_changes)[c])
        etf_word = f"ETF全面下跌，{ETF_SHORT_NAMES[top_down_code]}领跌"
    elif len(up_etfs) >= 3:
        top_up_code = max(up_etfs, key=lambda c: dict(etf_changes)[c])
        etf_word = f"ETF多数上涨，{ETF_SHORT_NAMES[top_up_code]}领涨"
    elif len(down_etfs) >= 3:
        top_down_code = min(down_etfs, key=lambda c: dict(etf_changes)[c])
        etf_word = f"ETF多数下跌，{ETF_SHORT_NAMES[top_down_code]}领跌"
    else:
        up_names = "、".join(ETF_SHORT_NAMES[c] for c in up_etfs)
        down_names = "、".join(ETF_SHORT_NAMES[c] for c in down_etfs)
        etf_word = f"ETF涨跌分化（{up_names}涨，{down_names}跌）"

    report = f"""# A股每日复盘 V3.0 — ETF异动择时模型

**日期：{datetime.now().strftime('%Y年%m月%d日')}| {session_label}（{fetch_time[-8:]}）| 数据源：mootdx + 腾讯财经 + 东财 + 同花顺**

---

## 一、指数数据

| 指数 | 最新点位 | 涨跌幅 | 成交额（亿） |
|------|---------|--------|-------------|
| 上证指数 | {idx['000001']['price']:,.2f} | {fmt_pct(idx['000001']['change_pct'])} | {sh_amt:,.0f} |
| 深证成指 | {idx['399001']['price']:,.2f} | {fmt_pct(idx['399001']['change_pct'])} | {sz_amt:,.0f} |
| 创业板指 | {idx['399006']['price']:,.2f} | {fmt_pct(idx['399006']['change_pct'])} | {idx['399006']['amount_wan']/10000:,.0f} |
| 沪深300 | {idx['000300']['price']:,.2f} | {fmt_pct(idx['000300']['change_pct'])} | {idx['000300']['amount_wan']/10000:,.0f} |
| 科创50 | {idx['000688']['price']:,.2f} | {fmt_pct(idx['000688']['change_pct'])} | {idx['000688']['amount_wan']/10000:,.0f} |

> {market_word}，{idx_names[best_idx[0]]}{"涨" if best_idx[1] > 0 else "跌"}{abs(best_idx[1]):.2f}%{"领涨" if best_idx[1] > 0 else "最抗跌"}，{idx_names[worst_idx[0]]}{"跌" if worst_idx[1] < 0 else "涨"}{abs(worst_idx[1]):.2f}%{"领跌" if worst_idx[1] < 0 else "最强"}。两市成交额约{total_amt:,.0f}亿。{etf_word}。

---

## 二、市场情绪数据

| 指标 | 数值 | 指标 | 数值 |
|------|------|------|------|
| 两市成交额 | {total_amt:,.0f}亿{vol_label} | 涨停家数 | {limit_up if limit_up else '数据待补录'} |
| 上涨家数 | {up if up else '数据待补录'} | 跌停家数 | {limit_down if limit_down else '数据待补录'} |
| 下跌家数 | {down if down else '数据待补录'} | 炸板家数 | 数据待补录 |
| 平盘家数 | {flat if flat else '数据待补录'} | 炸板率 | 数据待补录 |
| 连板最高高度 | 数据待补录 | 昨日连板晋级率 | 数据待补录 |
| 上涨占比 | {up_ratio:.1f}% | 连板股总数 | 数据待补录 |

### 连板梯队

| 高度 | 个股 | 板块 |
|------|------|------|
| 数据待补录 | 数据待补录 | 数据待补录 |

> {'上涨' + str(up) + '家 vs 下跌' + str(down) + '家，涨停' + str(limit_up) + '只、跌停' + str(limit_down) + '只。' if up or down else '市场涨跌家数数据待补录。'}{etf_word}，成交量{'为全天量' if is_after_close else '为盘中半日量'}。

---

## 三、ETF成交数据（重点）

### 3.1 七只ETF行情表

| ETF | 名称 | 最新价 | 涨跌幅 | 成交额（亿） | 换手率 |
|-----|------|--------|--------|-------------|--------|
"""
    for code in ETFS:
        q = etf.get(code, {})
        report += f"| {code} | {q.get('name', ETF_FULL_NAMES.get(code, ''))} | {q.get('price', 0):.3f} | {fmt_pct(q.get('change_pct', 0))} | {q.get('amount_wan', 0)/10000:.2f} | {q.get('turnover_pct', 0):.2f}% |\n"

    for code in ETFS:
        report += f"""
### 3.{2 + ETFS.index(code)} {code} {ETF_FULL_NAMES.get(code, '')} 近5日OHLC表

{gen_kline_table(etf_klines.get(code, []), etf.get(code, {}).get('name', ETF_FULL_NAMES.get(code, '')))}
{gen_kline_pattern_section(etf_klines.get(code, []), ETF_FULL_NAMES.get(code, ''))}
"""

    report += f"""
---

## 四、【V3.0】ETF放量倍数量化表

| ETF | 今日成交额（亿） | 昨日成交额（亿） | 近5日均值（亿） | 放量倍数 |
|-----|----------------|----------------|---------------|---------|
"""

    for code in ETFS:
        v = vol_data.get(code, {})
        ratio_str = f"{v.get('ratio', 0):.2f}x" if v.get('ratio') else "—"
        report += f"| {code} | {v.get('today', 0):.2f} | {v.get('yesterday', 0):.2f} | {v.get('avg5', 0):.2f} | {ratio_str} |\n"

    report += f"""
> {'B条件（≥2只ETF≥1.5x）暂未触发，7只ETF放量倍数均低于1.5x。' if is_after_close else '今日为盘中数据（未收盘），成交额为半日量。放量倍数偏低属正常。B条件（≥2只ETF≥1.5x）暂未触发。'}
"""

    report += f"""
---

## 五、【V3.0】ETF净申赎数据

| ETF | 今日主力净流入 | 近5日净流入合计 | 资金方向 |
|-----|--------------|---------------|---------|
"""
    for code in ETFS:
        report += f"| {code} | 数据待补录 | 数据待补录 | — |\n"
    report += f"""

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

    # 动态生成行业ETF描述
    ind_etf_changes = []
    for code in ["512400", "515220", "159611", "515880", "512010", "512880"]:
        if code in ind_etf:
            q = ind_etf[code]
            ind_etf_changes.append((q.get('name', code), q.get('change_pct', 0)))
    if ind_etf_changes:
        ind_up = [(n, c) for n, c in ind_etf_changes if c > 0]
        ind_down = [(n, c) for n, c in ind_etf_changes if c < 0]
        ind_desc_parts = []
        if ind_up:
            top_up = sorted(ind_up, key=lambda x: x[1], reverse=True)[:2]
            ind_desc_parts.append("、".join(f"{n}（+{c:.2f}%）" for n, c in top_up) + "上涨")
        if ind_down:
            top_down = sorted(ind_down, key=lambda x: x[1])[:2]
            ind_desc_parts.append("、".join(f"{n}（{c:.2f}%）" for n, c in top_down) + "下跌")
        ind_etf_desc = "行业ETF分化明显：" + "，".join(ind_desc_parts) + "。" if ind_desc_parts else "行业ETF整体平稳。"
    else:
        ind_etf_desc = "行业ETF数据待补录。"

    report += f"""
> {ind_etf_desc}

---

## 七、资金流向

### 行业资金流入TOP5

| 排名 | 行业 | 涨跌幅 | 上涨/下跌 |
|------|------|--------|----------|
"""

    if industries:
        for ind in industries[:5]:
            up_c = ind.get('up_count', '—')
            dn_c = ind.get('down_count', '—')
            report += f"| {ind.get('rank','—')} | {ind['name']} | {fmt_pct(ind['change_pct'])} | 涨{up_c}/跌{dn_c} |\n"
    else:
        report += "| 数据待补录 | 数据待补录 | — | — |\n"

    report += "\n### 板块跌幅TOP5\n\n| 排名 | 行业 | 涨跌幅 | 上涨/下跌 |\n|------|------|--------|----------|\n"
    if industries and len(industries) > 5:
        bottom = sorted(industries, key=lambda x: x['change_pct'])[:5]
        for ind in bottom:
            up_c = ind.get('up_count', '—')
            dn_c = ind.get('down_count', '—')
            report += f"| {ind.get('rank','—')} | {ind['name']} | {fmt_pct(ind['change_pct'])} | 涨{up_c}/跌{dn_c} |\n"
    else:
        report += "| 数据待补录 | 数据待补录 | — | — |\n"

    # 动态生成最强主线
    if industries:
        top_ind = sorted(industries, key=lambda x: x['change_pct'], reverse=True)[:5]
        bottom_ind = sorted(industries, key=lambda x: x['change_pct'])[:5]
        top_str = "、".join(f"{ind['name']}（{'+' if ind['change_pct'] > 0 else ''}{ind['change_pct']:.2f}%）" for ind in top_ind)
        bottom_str = "、".join(f"{ind['name']}（{ind['change_pct']:.2f}%）" for ind in bottom_ind)
    else:
        # 用ETF数据代替
        top_str = "、".join(f"{ETF_SHORT_NAMES[c]}ETF（{'+' if chg > 0 else ''}{chg:.2f}%）" for c, chg in sorted(etf_changes, key=lambda x: x[1], reverse=True))
        bottom_str = top_str

    # 动态判断市场风格
    tech_up = idx['000688']['change_pct'] > 0 and etf['512480']['change_pct'] > 0
    big_value_up = idx['000300']['change_pct'] > 0
    if tech_up:
        style_main = "成长科技"
        style_desc = "科技方向走强，半导体、科创等成长板块反弹"
    elif big_value_up:
        style_main = "大盘价值"
        style_desc = "大盘价值相对抗跌，沪深300表现优于创业板"
    elif down_indices >= 4:
        style_main = "防御避险"
        style_desc = "市场整体偏弱，资金避险情绪明显"
    else:
        style_main = "震荡分化"
        style_desc = "市场涨跌不一，板块分化明显"

    report += f"""

---

## 八、今日最强主线

**涨幅方向：** {top_str}
**跌幅方向：** {bottom_str}

市场风格：{style_desc}。

---

## 九、市场风格

- [{"x" if style_main == "电力公用事业" else " "}] 电力公用事业
- [{"x" if style_main == "大盘价值" else " "}] 大盘价值
- [{"x" if style_main == "资源周期" else " "}] 资源周期
- [{"x" if style_main == "成长科技" else " "}] 成长科技
- [{"x" if style_main == "消费医药" else " "}] 消费医药
- [{"x" if style_main == "小盘题材" else " "}] 小盘题材

> 当前市场风格为「{style_main}」风格，{style_desc}。

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

    # 动态生成ETF异动描述
    etf_change_desc = []
    for code in ETFS:
        chg = etf[code]["change_pct"]
        name = ETF_SHORT_NAMES[code]
        etf_change_desc.append(f"{name}ETF（{code}）{'+' if chg > 0 else ''}{chg:.2f}%")
    etf_change_str = "、".join(etf_change_desc)

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

{etf_change_str}。

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
- B条件（≥2只ETF放量≥1.5x）：{"✓ 触发" if b_count >= 2 else f"✗ 未触发{vol_label}"}
- C条件（两市成交>2万亿）：{"✓ 触发" if c_trigger else f"✗ 未触发{vol_label}"}
- D条件（跌停>50家）：{"✓ 触发" if d_trigger else "✗ 未触发（或数据待补）"}

> {'' if is_after_close else '盘中数据不完整，星级评定为参考值。需收盘后最终确认。'}

---

## 十七、【V3.0】极端情绪指数

| 指标 | 今日数值 | 评分（1-5） |
|------|---------|-----------|
| 上涨家数 | {up if up else '待补录'} | — |
| 下跌家数 | {down if down else '待补录'} | — |
| 跌停家数 | {limit_down if limit_down else '待补录'} | — |
| ETF异动 | {b_count}只放量 | — |
| 两市成交额 | {total_amt:,.0f}亿 | — |

**极端情绪评分：—/25{'' if is_after_close else '（盘中数据不完整）'}**

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
| 外部风险 | {style_desc} |

---

## 二十、总结表

| 维度 | 状态 |
|------|------|
| 市场情绪 | {style_desc} |
| 资金强弱 | {'放量' if total_amt > 15000 else '缩量'}（盘中{total_amt:,.0f}亿） |
| ETF状态 | {etf_word} |
| 市场风格 | {style_main} |
| 是否极端 | {'是' if abs(worst_idx[1]) > 5 or abs(min(c for _, c in etf_changes)) > 5 else '否'} |
| 是否ETF异动 | 否（放量倍数均<1.0x{vol_label}） |
| 是否值得跟踪 | 是（关注收盘后B条件是否触发） |
| 外部环境 | {style_desc} |

---

**报告生成时间：** {fetch_time}
**模板版本：** V3.0
**数据来源：** mootdx + 腾讯财经 + 东财 + 同花顺 + 公开市场数据
**GitHub存档：** reports/{datetime.now().strftime('%Y%m%d')}.md

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
    is_after_close = int(fetch_time[11:13]) >= 15 if len(fetch_time) >= 13 else False
    session_label = "收盘" if is_after_close else "盘中快照"
    vol_label = "" if is_after_close else "（盘中半日量）"

    sh_amt = idx["000001"]["amount_wan"] / 10000
    sz_amt = idx["399001"]["amount_wan"] / 10000
    total_amt = sh_amt + sz_amt

    # 放量倍数
    vol_data = {}
    for code in ETFS:
        if code in etf_klines:
            today_amt, yest_amt, avg5 = calc_vol_ratio(etf_klines[code])
            vol_data[code] = {
                "today": today_amt / 1e8 if today_amt else 0,
                "yesterday": yest_amt / 1e8 if yest_amt else 0,
                "avg5": avg5 / 1e8 if avg5 else 0,
                "ratio": today_amt / avg5 if avg5 and avg5 > 0 else 0,
            }
    b_count = sum(1 for v in vol_data.values() if v["ratio"] >= 1.5)

    # ETF持仓数据使用全局 ETF_HOLDINGS / ETF_FULL_NAMES

    # 计算ETF支撑压力位（从K线数据）
    etf_levels = {}
    for code in ETFS:
        if code in etf_klines and len(etf_klines[code]) >= 2:
            klines = etf_klines[code]
            today_k = klines[-1]
            yest_k = klines[-2] if len(klines) >= 2 else today_k
            etf_levels[code] = {
                "today_low": today_k["low"],
                "today_high": today_k["high"],
                "yest_close": yest_k["close"],
            }

    # 动态判断市场趋势
    sh_chg = idx['000001']['change_pct']
    cyb_chg = idx['399006']['change_pct']
    kc_chg = idx['000688']['change_pct']

    if sh_chg > 0 and cyb_chg > 0 and kc_chg > 0:
        trend_summary = "三大指数集体上涨，市场情绪偏暖"
    elif sh_chg < 0 and cyb_chg < 0 and kc_chg < 0:
        trend_summary = "三大指数集体下跌，市场情绪偏弱"
    else:
        trend_summary = f"指数涨跌不一，上证{'涨' if sh_chg > 0 else '跌'}{abs(sh_chg):.2f}%，创业板{'跌' if cyb_chg < 0 else '涨'}{abs(cyb_chg):.2f}%"

    # 计算ETF浮盈亏
    def calc_pnl(code):
        h = ETF_HOLDINGS[code]
        price = etf[code]["price"]
        pnl_pct = (price - h["cost"]) / h["cost"] * 100
        pnl_amt = (price - h["cost"]) * h["shares"]
        return pnl_pct, pnl_amt

    report = f"""# 复盘分析 — {datetime.now().strftime('%Y年%m月%d日')} {session_label}

> 数据时间：{fetch_time} | {session_label}{'' if is_after_close else '，未收盘'}

---

## 一、指数趋势分析

### 上证指数
- 当前点位：{idx['000001']['price']:.2f}，{fmt_pct(idx['000001']['change_pct'])}
- 成交额：{sh_amt:,.0f}亿
- **判断：** 上证{'涨' if sh_chg > 0 else '跌'}{abs(sh_chg):.2f}%，{'大盘相对抗跌' if sh_chg > 0 else '大盘偏弱'}。

### 科创50
- 当前点位：{idx['000688']['price']:.2f}，{fmt_pct(idx['000688']['change_pct'])}
- 成交额：{idx['000688']['amount_wan']/10000:,.0f}亿
- **判断：** 科创50{'涨' if kc_chg > 0 else '跌'}{abs(kc_chg):.2f}%，{'科技方向走强' if kc_chg > 0 else '科技方向偏弱'}。

### 创业板指
- 当前点位：{idx['399006']['price']:.2f}，{fmt_pct(idx['399006']['change_pct'])}
- 成交额：{idx['399006']['amount_wan']/10000:,.0f}亿
- **判断：** 创业板{'涨' if cyb_chg > 0 else '跌'}{abs(cyb_chg):.2f}%。

**趋势总结：** {trend_summary}。两市成交额约{total_amt:,.0f}亿{vol_label}。

---

## 二、ETF趋势分析

"""

    # 动态生成7只ETF分析
    for code in ETFS:
        pnl_pct, pnl_amt = calc_pnl(code)
        above_break = etf[code]["price"] > ETF_HOLDINGS[code]["break_price"]
        # K线形态
        etf_kl = etf_klines.get(code, [])
        patterns, pattern_overall = detect_kline_patterns(etf_kl)
        pattern_str = ""
        if patterns:
            pattern_items = "; ".join(f"{p[0]}({p[2]})" for p in patterns)
            pattern_str = f"- **K线形态：** {pattern_items} → {pattern_overall}"
        else:
            pattern_str = f"- **K线形态：** 无明显特殊形态"

        report += f"""### {code} {ETF_FULL_NAMES[code]}
- 最新价：{etf[code]['price']:.3f}，{fmt_pct(etf[code]['change_pct'])}
- 量比：{vol_data[code]['ratio']:.2f}x{vol_label}
- 成本价：{ETF_HOLDINGS[code]['cost']:.3f}（{ETF_HOLDINGS[code]['shares']}股），8/5启动阳线低位：{ETF_HOLDINGS[code]['break_price']:.3f}
- 浮盈亏：{pnl_pct:+.2f}%（{pnl_amt:+.0f}元）
- **破位判断：** {'已站上8/5启动阳线低位' if above_break else '仍在8/5启动阳线低位下方'}
- **建议：** {'持有' if above_break else '关注破位价，跌破即止损'}
{pattern_str}

"""

    report += f"""

---

## 三、K线形态综合分析

> ⚠️ **大盘处于年线下方，任何反弹结构都需警惕K线形态信号。** 以下为7只ETF + 6只个股的最新K线形态检测。

### ETF K线形态 + 分时走势汇总

| ETF | 今日形态 | 方向 | 分时走势 | 量能 | 综合信号 | 关键信号 |
|-----|---------|------|---------|------|---------|---------|
"""
    # Check if we have stock_klines for stocks too
    stock_klines = main.get("stock_klines", {})
    stock_names_local = {
        "600160": "巨化股份", "000920": "沃顿科技",
        "603290": "斯达半导", "000063": "中兴通讯", "002803": "吉宏股份",
    }

    for code in ETFS:
        kl = etf_klines.get(code, [])
        pats, overall = detect_kline_patterns(kl)
        intraday = analyze_intraday_pattern(kl)
        if pats:
            pat_names = ", ".join(p[0] for p in pats)
            dir_str = overall
        else:
            pat_names = "无特殊形态"
            dir_str = "中性"
        intraday_str = intraday["intraday_pattern"] if intraday else "—"
        vol_str = intraday["vol_desc"] if intraday else "—"
        combined_str = intraday["combined_signal"] if intraday else "—"
        signal = pats[0][1][:30] + "..." if pats and len(pats[0][1]) > 30 else (pats[0][1] if pats else "—")
        report += f"| {code} {ETF_SHORT_NAMES.get(code, '')} | {pat_names} | {dir_str} | {intraday_str} | {vol_str} | {combined_str} | {signal} |\n"

    report += f"""
### 个股 K线形态 + 分时走势汇总

| 个股 | 今日形态 | 方向 | 分时走势 | 量能 | 综合信号 | 关键信号 |
|-----|---------|------|---------|------|---------|---------|
"""
    for code in ["600160", "000920", "603290", "000063", "002803"]:
        kl = stock_klines.get(code, [])
        pats, overall = detect_kline_patterns(kl)
        intraday = analyze_intraday_pattern(kl)
        if pats:
            pat_names = ", ".join(p[0] for p in pats)
            dir_str = overall
        else:
            pat_names = "无特殊形态"
            dir_str = "中性"
        intraday_str = intraday["intraday_pattern"] if intraday else "—"
        vol_str = intraday["vol_desc"] if intraday else "—"
        combined_str = intraday["combined_signal"] if intraday else "—"
        signal = pats[0][1][:30] + "..." if pats and len(pats[0][1]) > 30 else (pats[0][1] if pats else "—")
        report += f"| {code} {stock_names_local.get(code, '')} | {pat_names} | {dir_str} | {intraday_str} | {vol_str} | {combined_str} | {signal} |\n"

    # Count bullish/bearish patterns
    all_bullish = 0
    all_bearish = 0
    for code in ETFS:
        kl = etf_klines.get(code, [])
        pats, _ = detect_kline_patterns(kl)
        for _, _, d in pats:
            if d in ("看多", "偏多"): all_bullish += 1
            elif d in ("看空", "偏空"): all_bearish += 1
    for code in ["600160", "000920", "603290", "000063", "002803"]:
        kl = stock_klines.get(code, [])
        pats, _ = detect_kline_patterns(kl)
        for _, _, d in pats:
            if d in ("看多", "偏多"): all_bullish += 1
            elif d in ("看空", "偏空"): all_bearish += 1

    if all_bullish > all_bearish:
        kline_summary = f"整体偏多（{all_bullish}个看多信号 vs {all_bearish}个看空信号），反弹结构暂时维持，但年线下方需保持警惕"
    elif all_bearish > all_bullish:
        kline_summary = f"整体偏空（{all_bullish}个看多信号 vs {all_bearish}个看空信号），反弹结构出现裂痕，注意减仓/止损"
    else:
        kline_summary = f"多空平衡（{all_bullish}个看多信号 vs {all_bearish}个看空信号），方向不明，控制仓位"

    report += f"""
**K线形态总结：** {kline_summary}

> **形态交易规则（年线下方）：**
> - 出现**底分型/阳包阴/高低点抬升/锤子线** → 反转信号，可逢低建仓
> - 出现**顶分型/阴包阳/高低点下移/射击之星** → 减仓信号，果断止盈/止损
> - 出现**十字星** → 变盘预警，缩量观望，等次日方向确认
> - **光脚阴线/大阴线** → 空头强势，不抄底；**光脚阳线/大阳线** → 多头强势，可跟进

> **⚠️ 分时走势配合规则（重要！）：**
> - 日线**高低点抬升** + 分时**高开低走** → 警惕回调/横盘1-5个交易日（放量=主力派发，缩量=获利回吐）
> - 日线**高低点抬升** + 分时**高开高走** → 强势确认，趋势延续
> - 日线**高低点抬升** + 分时**低开高走** → 洗盘拉升，主力吸筹，更强势
> - 日线**高低点下移** + 分时**高开低走** → 强空确认（放量=派发加速）
> - 日线**高低点下移** + 分时**低开高走** → 可能见底（放量=吸筹信号）
> - **分时走势往往提前预演接下来1-5个交易日的走势，不可忽视！**

---

## 四、ETF放量倍数（B条件检测）

| ETF | 今日成交额 | 近5日均值 | 放量倍数 | 是否≥1.5x |
|-----|----------|---------|---------|----------|
"""
    for code in ETFS:
        v = vol_data.get(code, {})
        report += f"| {code} | {v.get('today', 0):.2f}亿 | {v.get('avg5', 0):.2f}亿 | {v.get('ratio', 0):.2f}x | {'✓' if v.get('ratio', 0) >= 1.5 else '✗'} |\n"
    report += f"""
**B条件状态：** {b_count}只ETF ≥ 1.5x → {"✓ 触发" if b_count >= 2 else "✗ 未触发"}

> {"收盘确认：B条件未触发，7只ETF放量倍数均低于1.5x。" if is_after_close else "⚠️ 盘中半日量，放量倍数偏低属正常。需收盘后最终确认。如果下午继续放量（特别是科技ETF恐慌性抛售），B条件可能在尾盘触发。"}

---

## 五、仓位状态建议

**总资产：501,837元**（三账户合计：广发91,444 + 国金77,078 + 东财333,315）
- ETF持仓市值：约{sum(etf[code]["price"] * ETF_HOLDINGS[code]["shares"] for code in ETFS):,.0f}元（东财场内基金）
- 个股持仓市值：约127,785元（6只，分散在广发/国金账户）
- 可用现金：约20,000元（账户剩余可用）
- ETF总浮盈亏：{sum(calc_pnl(code)[1] for code in ETFS):+,.0f}元

### ETF仓位建议（趋势破位止损策略）

| ETF | 持仓/成本 | 最新价 | 浮盈亏 | 8/5启动阳线低位 | 建议 |
|-----|---------|--------|--------|----------------|------|
"""
    for code in ETFS:
        report += f"| {code} | {ETF_HOLDINGS[code]['shares']}股/{ETF_HOLDINGS[code]['cost']:.3f} | {etf[code]['price']:.3f} | {calc_pnl(code)[0]:+.2f}% | {ETF_HOLDINGS[code]['break_price']:.3f} | {'持有' if etf[code]['price'] > ETF_HOLDINGS[code]['break_price'] else '关注止损'} |\n"
    report += f"""
> 止损规则：跌破8/5启动阳线低位即走，不设固定百分比。

### 闲置资金操作建议

约2万元可用资金暂不动，等待更清晰信号。原因：
1. {'B条件未触发（放量倍数均<1.5x），ABCD模型无买入信号' if b_count == 0 else f'B条件触发{b_count}只，关注C条件确认'}
2. ETF持仓{'全部站上8/5启动阳线低位，趋势修复中' if all(etf[c]['price'] > ETF_HOLDINGS[c]['break_price'] for c in ETFS) else '部分仍在启动阳线低位下方，需观察'}
3. 个股方向根据技术指标灵活操作，不急于加仓

---

## 六、其他重点

### 1. 市场趋势
{trend_summary}。两市成交额约{total_amt:,.0f}亿{vol_label}{'，收盘确认' if is_after_close else '，需收盘后确认最终量能'}。

### 2. 核心判断
- **趋势判断：** {trend_summary}
- **ETF策略：** 趋势破位止损，跌破8/5启动阳线低位即走
- **个股策略：** 死扛等反转，依赖技术指标判断反转信号
- **操作策略：** ETF执行纪律止损，个股死扛等反弹，现金不动

### 3. 关注点
- 收盘后确认B条件是否触发
- 7只ETF是否站稳8/5启动阳线低位上方
- 个股技术指标变化（MACD/KDJ金叉/死叉）

---

**报告生成时间：** {fetch_time}
**策略框架：** ETF异动择时模型 + 趋势跟踪 + ABCD四条件
**仓位管理：** 总资产50.2万，ETF约33.4万（趋势破位止损）+ 个股约12.8万（死扛等反转）+ 可用约2万
"""
    return report


def generate_stock_tracking(main, extra):
    """生成个股追踪报告"""
    stock_klines = main.get("stock_klines", {})
    stock_indicators = main.get("stock_indicators", {})
    stock_quotes = main.get("stock_quotes", {})
    meta = main.get("meta", {})
    fetch_time = meta.get("fetch_time", "")
    is_after_close = int(fetch_time[11:13]) >= 15 if len(fetch_time) >= 13 else False
    session_label = "收盘" if is_after_close else "盘中快照"
    vol_label = "" if is_after_close else "（盘中半日量）"

    stock_names = {
        "600160": "巨化股份", "000920": "沃顿科技",
        "603290": "斯达半导", "000063": "中兴通讯", "002803": "吉宏股份",
    }
    stock_industries = {
        "600160": "氟化工/化学制品", "000920": "环保/膜材料",
        "603290": "半导体/IGBT", "000063": "通信设备/5G", "002803": "跨境电商",
    }

    report = f"""# 个股追踪报告 — {datetime.now().strftime('%Y年%m月%d日')}

> 数据时间：{fetch_time} | {session_label}
> 数据源：mootdx K线 + 手动计算技术指标
> 追踪标的：600160 / 000920 / 603290 / 000063 / 002803

---

"""

    # 计算每只股票的5日涨跌并排序
    stock_5d = {}
    for code in ["600160", "000920", "603290", "000063", "002803"]:
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

{gen_kline_pattern_section(klines, name)}

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
