#!/usr/bin/env python3
"""A股数据采集脚本 - 使用mootdx + 腾讯财经 + 百度股市通 + 东财"""

import json
import sys
import os
import time
import random
import urllib.request
import requests
from datetime import datetime, date

# ============================================================
# 1. 腾讯财经 - 指数/ETF/个股实时行情
# ============================================================

# 指数代码列表（需要sh前缀的指数）
INDEX_CODES = {"000001", "000300", "000688", "000016", "000905", "399001", "399006", "399005", "399300"}

def tencent_quote(codes):
    """批量拉取腾讯财经实时行情"""
    prefixed = []
    for c in codes:
        if c in INDEX_CODES:
            # 指数: 000001/000300/000688用sh, 399xxx用sz
            if c.startswith("3"):
                prefixed.append(f"sz{c}")
            else:
                prefixed.append(f"sh{c}")
        elif c.startswith(("5", "6", "9")):
            prefixed.append(f"sh{c}")  # ETF(5开头) + 上海股票(6开头)
        elif c.startswith("8"):
            prefixed.append(f"bj{c}")
        else:
            prefixed.append(f"sz{c}")  # 深圳股票(0/3开头) + 深圳ETF(1开头)

    url = "https://qt.gtimg.cn/q=" + ",".join(prefixed)
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "Mozilla/5.0")
    resp = urllib.request.urlopen(req, timeout=15)
    data = resp.read().decode("gbk")

    result = {}
    for line in data.strip().split(";"):
        if not line.strip() or "=" not in line or '"' not in line:
            continue
        key = line.split("=")[0].split("_")[-1]
        vals = line.split('"')[1].split("~") if '"' in line else []
        if len(vals) < 53:
            continue
        code = key[2:]
        try:
            result[code] = {
                "name":         vals[1],
                "price":        float(vals[3]) if vals[3] else 0,
                "last_close":   float(vals[4]) if vals[4] else 0,
                "open":         float(vals[5]) if vals[5] else 0,
                "change_amt":   float(vals[31]) if vals[31] else 0,
                "change_pct":   float(vals[32]) if vals[32] else 0,
                "high":         float(vals[33]) if vals[33] else 0,
                "low":          float(vals[34]) if vals[34] else 0,
                "amount_wan":   float(vals[37]) if vals[37] else 0,
                "turnover_pct": float(vals[38]) if vals[38] else 0,
                "pe_ttm":       float(vals[39]) if vals[39] else 0,
                "amplitude_pct":float(vals[43]) if vals[43] else 0,
                "mcap_yi":      float(vals[44]) if vals[44] else 0,
                "float_mcap_yi":float(vals[45]) if vals[45] else 0,
                "pb":           float(vals[46]) if vals[46] else 0,
                "limit_up":     float(vals[47]) if vals[47] else 0,
                "limit_down":   float(vals[48]) if vals[48] else 0,
                "vol_ratio":    float(vals[49]) if vals[49] else 0,
            }
        except (ValueError, IndexError):
            continue
    return result


# ============================================================
# 2. mootdx - K线数据
# ============================================================

def get_klines(code, count=10, category=4):
    """获取K线数据
    category: 4=日线, 5=周线, 6=月线
    返回: [{datetime, open, close, high, low, vol, amount}, ...]
    """
    from mootdx.quotes import Quotes
    client = Quotes.factory(market='std')

    # 判断市场: 6开头=上海(1), 其他=深圳(0)
    market = 1 if code.startswith(("6", "9")) else 0

    try:
        df = client.bars(symbol=code, category=category, offset=count)
        if df is None or len(df) == 0:
            return []

        klines = []
        for _, row in df.iterrows():
            klines.append({
                "datetime": str(row.get("datetime", "")),
                "open": float(row.get("open", 0)),
                "close": float(row.get("close", 0)),
                "high": float(row.get("high", 0)),
                "low": float(row.get("low", 0)),
                "vol": float(row.get("vol", 0)),
                "amount": float(row.get("amount", 0)),
            })
        return klines
    except Exception as e:
        print(f"[WARN] mootdx kline {code}: {e}")
        return []


# ============================================================
# 3. stockstats - 技术指标计算
# ============================================================

def calc_indicators(klines):
    """从K线数据计算技术指标（手动计算）
    返回: {MA5, MA10, MA20, MA60, MACD_DIF, MACD_DEA, MACD_HIST,
           KDJ_K, KDJ_D, KDJ_J, RSI_6, RSI_12, BOLL_MID, BOLL_UPPER, BOLL_LOWER}
    """
    if len(klines) < 10:
        return {}

    closes = [k["close"] for k in klines]
    highs = [k["high"] for k in klines]
    lows = [k["low"] for k in klines]
    n = len(closes)

    result = {}

    # --- MA均线 ---
    def sma(data, period):
        if len(data) < period:
            return None
        return round(sum(data[-period:]) / period, 2)

    result["MA5"] = sma(closes, 5)
    result["MA10"] = sma(closes, 10)
    result["MA20"] = sma(closes, 20)
    result["MA60"] = sma(closes, 60) if n >= 60 else None

    # --- MACD (12,26,9) ---
    def ema(data, period):
        """指数移动平均"""
        if len(data) < period:
            return None
        multiplier = 2 / (period + 1)
        ema_prev = sum(data[:period]) / period  # SMA as seed
        ema_values = [ema_prev]
        for i in range(period, len(data)):
            ema_prev = data[i] * multiplier + ema_prev * (1 - multiplier)
            ema_values.append(ema_prev)
        return ema_values[-1]

    ema12 = ema(closes, 12)
    ema26 = ema(closes, 26)
    if ema12 is not None and ema26 is not None:
        dif = round(ema12 - ema26, 4)
        result["MACD_DIF"] = dif
        # DEA = EMA(DIF, 9) - 需要历史DIF序列
        dif_series = []
        for i in range(26, n + 1):
            sub_closes = closes[:i]
            e12 = ema(sub_closes, 12)
            e26 = ema(sub_closes, 26)
            if e12 is not None and e26 is not None:
                dif_series.append(e12 - e26)
        if len(dif_series) >= 9:
            dea = ema(dif_series, 9)
            if dea is not None:
                result["MACD_DEA"] = round(dea, 4)
                result["MACD_HIST"] = round(2 * (dif - dea), 4)
            else:
                result["MACD_DEA"] = None
                result["MACD_HIST"] = None
        else:
            result["MACD_DEA"] = None
            result["MACD_HIST"] = None
    else:
        result["MACD_DIF"] = None
        result["MACD_DEA"] = None
        result["MACD_HIST"] = None

    # --- KDJ (9,3,3) ---
    if n >= 9:
        # RSV = (Close - LowestLow(9)) / (HighestHigh(9) - LowestLow(9)) * 100
        low9 = min(lows[-9:])
        high9 = max(highs[-9:])
        if high9 != low9:
            rsv = (closes[-1] - low9) / (high9 - low9) * 100
        else:
            rsv = 50

        # K = 2/3 * K_prev + 1/3 * RSV, D = 2/3 * D_prev + 1/3 * K, J = 3K - 2D
        # 初始化K=D=50
        k_prev, d_prev = 50.0, 50.0
        for i in range(max(0, n - 30), n):  # 回算最近30根
            period = min(9, i + 1)
            l = min(lows[i-period+1:i+1])
            h = max(highs[i-period+1:i+1])
            if h != l:
                rsv_i = (closes[i] - l) / (h - l) * 100
            else:
                rsv_i = 50
            k_prev = 2/3 * k_prev + 1/3 * rsv_i
            d_prev = 2/3 * d_prev + 1/3 * k_prev
        j = 3 * k_prev - 2 * d_prev
        result["KDJ_K"] = round(k_prev, 2)
        result["KDJ_D"] = round(d_prev, 2)
        result["KDJ_J"] = round(j, 2)
    else:
        result["KDJ_K"] = None
        result["KDJ_D"] = None
        result["KDJ_J"] = None

    # --- RSI (6, 12) ---
    def calc_rsi(data, period):
        if len(data) < period + 1:
            return None
        gains = []
        losses = []
        for i in range(-period, 0):
            change = data[i] - data[i-1]
            if change > 0:
                gains.append(change)
                losses.append(0)
            else:
                gains.append(0)
                losses.append(abs(change))
        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return round(100 - 100 / (1 + rs), 2)

    result["RSI_6"] = calc_rsi(closes, 6)
    result["RSI_12"] = calc_rsi(closes, 12)

    # --- BOLL (20, 2) ---
    if n >= 20:
        mid = sum(closes[-20:]) / 20
        std_dev = (sum((c - mid) ** 2 for c in closes[-20:]) / 20) ** 0.5
        result["BOLL_MID"] = round(mid, 2)
        result["BOLL_UPPER"] = round(mid + 2 * std_dev, 2)
        result["BOLL_LOWER"] = round(mid - 2 * std_dev, 2)
    else:
        result["BOLL_MID"] = None
        result["BOLL_UPPER"] = None
        result["BOLL_LOWER"] = None

    return result


# ============================================================
# 4. 东财 - 全球资讯 + 行业排名
# ============================================================

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

EM_SESSION = requests.Session()
EM_SESSION.headers.update({"User-Agent": UA})
EM_SESSION.trust_env = False  # 绕过系统代理，解决东财push2 API被阻断问题
EM_MIN_INTERVAL = 1.0
_em_last_call = [0.0]

def em_get(url, params=None, headers=None, timeout=15, **kwargs):
    wait = EM_MIN_INTERVAL - (time.time() - _em_last_call[0])
    if wait > 0:
        time.sleep(wait + random.uniform(0.1, 0.3))
    try:
        return EM_SESSION.get(url, params=params, headers=headers, timeout=timeout, **kwargs)
    finally:
        _em_last_call[0] = time.time()


def eastmoney_global_news(page_size=20):
    """东财全球资讯"""
    import uuid
    url = "https://np-weblist.eastmoney.com/comm/web/getFastNewsList"
    params = {
        "client": "web", "biz": "web_724",
        "fastColumn": "102", "sortEnd": "",
        "pageSize": str(page_size),
        "req_trace": str(uuid.uuid4()),
    }
    headers = {"User-Agent": UA, "Referer": "https://kuaixun.eastmoney.com/"}
    try:
        r = em_get(url, params=params, headers=headers, timeout=10)
        d = r.json()
        rows = []
        for item in d.get("data", {}).get("fastNewsList", []):
            rows.append({
                "title": item.get("title", ""),
                "summary": item.get("summary", "")[:150],
                "time": item.get("showTime", ""),
            })
        return rows
    except Exception as e:
        print(f"[WARN] eastmoney news: {e}")
        return []


def industry_comparison(top_n=20):
    """全行业涨跌幅排名（使用urllib绕过代理）"""
    import ssl
    base_url = "https://push2.eastmoney.com/api/qt/clist/get"
    params = "pn=1&pz=100&po=1&np=1&fltt=2&invt=2&fs=m:90+t:2&fields=f2,f3,f4,f12,f13,f14,f104,f105,f128,f136,f140,f141"
    url = f"{base_url}?{params}"
    headers = {"User-Agent": UA}
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        req = urllib.request.Request(url, headers=headers)
        resp = urllib.request.urlopen(req, timeout=15, context=ctx)
        d = json.loads(resp.read().decode("utf-8"))
        items = d.get("data", {}).get("diff", [])
        if not items:
            return {"top": [], "bottom": [], "total": 0}

        rows = []
        for i, item in enumerate(items):
            rows.append({
                "rank": i + 1,
                "name": item.get("f14", ""),
                "change_pct": item.get("f3", 0),
                "up_count": item.get("f104", 0),
                "down_count": item.get("f105", 0),
                "leader": item.get("f140", ""),
                "leader_change": item.get("f136", 0),
            })
        return {"top": rows[:top_n], "bottom": rows[-top_n:], "total": len(rows)}
    except Exception as e:
        print(f"[WARN] industry comparison: {e}")
        return {"top": [], "bottom": [], "total": 0}


def ths_hot_reason(date_str=None):
    """同花顺当日强势股"""
    if date_str is None:
        date_str = date.today().strftime("%Y-%m-%d")
    url = f"http://zx.10jqka.com.cn/event/api/getharden/date/{date_str}/orderby/date/orderway/desc/charset/GBK/"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/117.0.0.0 Safari/537.36"}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        data = r.json()
        if data.get("errocode", 0) != 0:
            return []
        rows = data.get("data") or []
        result = []
        for r in rows[:15]:
            result.append({
                "code": r.get("code", ""),
                "name": r.get("name", ""),
                "change_pct": r.get("zhangfu", "") or r.get("zhangdie_pct", ""),
                "reason": r.get("reason", ""),
            })
        return result
    except Exception as e:
        print(f"[WARN] ths hot: {e}")
        return []


# ============================================================
# 5. 市场涨跌家数
# ============================================================

def get_market_breadth():
    """获取市场涨跌家数 - 通过东财全市场列表（使用urllib绕过代理）"""
    import ssl
    base_url = "https://push2.eastmoney.com/api/qt/clist/get"
    headers = {"User-Agent": UA}

    try:
        # 获取总数
        params1 = "pn=1&pz=1&po=1&np=1&fltt=2&invt=2&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23&fields=f2,f3,f4,f12,f14"
        url1 = f"{base_url}?{params1}"
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        req1 = urllib.request.Request(url1, headers=headers)
        resp1 = urllib.request.urlopen(req1, timeout=15, context=ctx)
        d = json.loads(resp1.read().decode("utf-8"))
        total = d.get("data", {}).get("total", 0)

        # 拉取所有股票涨跌统计
        up = down = flat = 0
        limit_up = limit_down = 0
        params2 = "pn=1&pz=5000&po=1&np=1&fltt=2&invt=2&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23&fields=f2,f3,f4,f6,f8,f12,f14"
        url2 = f"{base_url}?{params2}"
        req2 = urllib.request.Request(url2, headers=headers)
        resp2 = urllib.request.urlopen(req2, timeout=15, context=ctx)
        d2 = json.loads(resp2.read().decode("utf-8"))
        items = d2.get("data", {}).get("diff", [])
        for item in items:
            pct_raw = item.get("f3", 0)
            try:
                pct = float(pct_raw) if pct_raw else 0
            except (ValueError, TypeError):
                pct = 0
            if pct > 0:
                up += 1
            elif pct < 0:
                down += 1
            else:
                flat += 1
            code = str(item.get("f12", ""))
            if code.startswith(("300", "688")):
                if pct >= 19.5:
                    limit_up += 1
                elif pct <= -19.5:
                    limit_down += 1
            else:
                if pct >= 9.9:
                    limit_up += 1
                elif pct <= -9.9:
                    limit_down += 1

        return {
            "total": total,
            "up": up,
            "down": down,
            "flat": flat,
            "limit_up": limit_up,
            "limit_down": limit_down,
        }
    except Exception as e:
        print(f"[WARN] market breadth: {e}")
        return {"total": 0, "up": 0, "down": 0, "flat": 0, "limit_up": 0, "limit_down": 0}


# ============================================================
# MAIN: 采集所有数据并输出 JSON
# ============================================================

def main():
    output = {}

    # --- 1. 指数行情 ---
    print("[1/8] 拉取指数行情...")
    indices = ["000001", "399001", "399006", "000300", "000688"]
    idx_quotes = tencent_quote(indices)
    output["indices"] = idx_quotes
    for code in indices:
        if code in idx_quotes:
            q = idx_quotes[code]
            print(f"  {q['name']}: {q['price']} ({'+' if q['change_pct']>0 else ''}{q['change_pct']}%)")

    # --- 2. ETF行情 ---
    print("[2/8] 拉取ETF行情...")
    etfs = ["510300", "159915", "588000", "512480"]
    etf_quotes = tencent_quote(etfs)
    output["etf_quotes"] = etf_quotes
    for code in etfs:
        if code in etf_quotes:
            q = etf_quotes[code]
            print(f"  {q['name']}: {q['price']} ({'+' if q['change_pct']>0 else ''}{q['change_pct']}%) 成交额={q['amount_wan']/10000:.2f}亿")

    # --- 3. 行业ETF异动 ---
    print("[3/8] 拉取行业ETF行情...")
    industry_etfs = ["512400", "515220", "159611", "515880", "512010", "512880"]
    ind_etf_quotes = tencent_quote(industry_etfs)
    output["industry_etfs"] = ind_etf_quotes

    # --- 4. ETF K线 ---
    print("[4/8] 拉取ETF K线...")
    output["etf_klines"] = {}
    for code in etfs:
        klines = get_klines(code, count=8)
        if klines:
            output["etf_klines"][code] = klines
            print(f"  {code}: {len(klines)}根K线, 最新={klines[-1]['datetime']}")
        else:
            print(f"  {code}: 获取失败")

    # --- 5. 个股K线 + 技术指标 ---
    print("[5/8] 拉取个股K线和技术指标...")
    stocks = ["002080", "600160", "000920", "603290", "000063", "002803"]
    stock_names = {
        "002080": "中材科技", "600160": "巨化股份", "000920": "沃顿科技",
        "603290": "斯达半导", "000063": "中兴通讯", "002803": "吉宏股份",
    }
    output["stock_quotes"] = tencent_quote(stocks)
    output["stock_klines"] = {}
    output["stock_indicators"] = {}

    for code in stocks:
        klines = get_klines(code, count=65)  # 多拉一些用于计算MA60
        if klines:
            output["stock_klines"][code] = klines[-8:]  # 只保留最近8根用于展示
            # 计算技术指标
            indicators = calc_indicators(klines)
            output["stock_indicators"][code] = indicators
            print(f"  {code} {stock_names[code]}: {len(klines)}根K线, 最新={klines[-1]['datetime']}")
            if indicators:
                print(f"    MA5={indicators.get('MA5')} MA10={indicators.get('MA10')} MA20={indicators.get('MA20')}")
                print(f"    MACD: DIF={indicators.get('MACD_DIF')} DEA={indicators.get('MACD_DEA')} HIST={indicators.get('MACD_HIST')}")
                print(f"    KDJ: K={indicators.get('KDJ_K')} D={indicators.get('KDJ_D')} J={indicators.get('KDJ_J')}")
                print(f"    RSI6={indicators.get('RSI_6')} BOLL_MID={indicators.get('BOLL_MID')}")
        else:
            print(f"  {code}: 获取失败")

    # --- 6. 市场涨跌家数 ---
    print("[6/8] 拉取市场涨跌家数...")
    breadth = get_market_breadth()
    output["market_breadth"] = breadth
    print(f"  上涨={breadth['up']} 下跌={breadth['down']} 平盘={breadth['flat']}")
    print(f"  涨停={breadth['limit_up']} 跌停={breadth['limit_down']}")

    # --- 7. 行业排名 ---
    print("[7/8] 拉取行业板块排名...")
    industries = industry_comparison(15)
    output["industries"] = industries
    if industries["top"]:
        print(f"  TOP5涨幅:")
        for r in industries["top"][:5]:
            print(f"    {r['name']}: {r['change_pct']}%")
        print(f"  BOTTOM5跌幅:")
        for r in industries["bottom"][-5:]:
            print(f"    {r['name']}: {r['change_pct']}%")

    # --- 8. 新闻 ---
    print("[8/8] 拉取新闻资讯...")
    news = eastmoney_global_news(10)
    output["news"] = news
    for n in news[:5]:
        print(f"  {n['time']} | {n['title'][:50]}")

    # 同花顺热点
    ths = ths_hot_reason()
    output["ths_hot"] = ths
    if ths:
        print(f"  同花顺强势股: {len(ths)}只")
        for s in ths[:5]:
            print(f"    {s['name']}({s['code']}): {s['change_pct']}% - {s['reason'][:40]}")

    # 输出JSON
    output["meta"] = {
        "fetch_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "today": date.today().strftime("%Y%m%d"),
    }

    json_path = os.path.join(os.path.dirname(__file__), "..", "data", "market_data.json")
    os.makedirs(os.path.dirname(json_path), exist_ok=True)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n[OK] 数据已保存到 {json_path}")
    print(f"     采集时间: {output['meta']['fetch_time']}")

if __name__ == "__main__":
    main()
