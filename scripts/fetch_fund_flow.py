#!/usr/bin/env python3
"""资金流向数据采集脚本 — 为每日复盘的资金流向分析模块提供数据

数据源:
1. 东财push2 ulist.np  — 主要指数资金流(主力/超大/大/中/小单净流入)
2. 同花顺hsgtApi       — 北向资金(沪股通/深股通当日净流入) + 本地缓存历史
3. 东财push2 clist     — 行业板块资金流TOP流入/流出
4. mootdx + 腾讯财经   — 指数成交额与5日均量对比(放量倍数)

输出: 写入 data/market_data.json 的 "fund_flow" 字段
用法: python scripts/fetch_fund_flow.py
"""

import json
import os
import sys
import time
import random
import ssl
import urllib.request
from datetime import date, datetime

import requests

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

EM_SESSION = requests.Session()
EM_SESSION.headers.update({"User-Agent": UA})
EM_SESSION.trust_env = False  # 绕过系统代理，解决东财push2被阻断问题
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


# ============================================================
# 1. 主要指数资金流（东财 push2 ulist.np）
# ============================================================
# secid: 1.=上海, 0.=深圳
# f62=主力净流入(元) f66=超大单净流入 f72=大单净流入 f78=中单净流入 f84=小单净流入 f184=主力净占比(%)
INDEX_SECIDS = {
    "000001": ("1.000001", "上证指数"),
    "399001": ("0.399001", "深证成指"),
    "399006": ("0.399006", "创业板指"),
    "000300": ("1.000300", "沪深300"),
    "000688": ("1.000688", "科创50"),
    "000016": ("1.000016", "上证50"),
}


def get_index_fund_flow():
    """拉取主要指数当日资金流（东财push2，带重试）"""
    secids = ",".join(v[0] for v in INDEX_SECIDS.values())
    url = "https://push2.eastmoney.com/api/qt/ulist.np/get"
    params = {
        "secids": secids,
        "fields": "f2,f3,f12,f14,f62,f66,f72,f78,f84,f184",
        "fltt": "2", "invt": "2",
    }
    headers = {"User-Agent": UA, "Referer": "https://quote.eastmoney.com/"}

    # 东财push2偶发断连（间歇性风控），重试5次、指数退避
    d = None
    for attempt in range(5):
        try:
            r = em_get(url, params=params, headers=headers, timeout=12)
            d = r.json()
            if d.get("data") and d["data"].get("diff"):
                break
        except Exception as e:
            print(f"[WARN] index fund flow attempt {attempt+1}: {e}")
        time.sleep(2 + attempt * 2)

    if d is None or not d.get("data") or not d["data"].get("diff"):
        return {"indices": {}, "market": {}, "market_all6": {}}

    items = d["data"]["diff"]
    result = {}
    total = {"main": 0.0, "super": 0.0, "large": 0.0, "mid": 0.0, "small": 0.0}
    for it in items:
        code = str(it.get("f12", ""))
        if code not in INDEX_SECIDS:
            continue
        main_net = (it.get("f62") or 0) / 1e8      # 亿元
        super_net = (it.get("f66") or 0) / 1e8
        large_net = (it.get("f72") or 0) / 1e8
        mid_net = (it.get("f78") or 0) / 1e8
        small_net = (it.get("f84") or 0) / 1e8
        result[code] = {
            "name": INDEX_SECIDS[code][1],
            "change_pct": it.get("f3", 0),
            "main_net_yi": round(main_net, 2),
            "super_net_yi": round(super_net, 2),
            "large_net_yi": round(large_net, 2),
            "mid_net_yi": round(mid_net, 2),
            "small_net_yi": round(small_net, 2),
            "main_ratio": round(it.get("f184") or 0, 2),
        }
        total["main"] += main_net
        total["super"] += super_net
        total["large"] += large_net
        total["mid"] += mid_net
        total["small"] += small_net

    # 大盘汇总口径: 仅上证指数(000001)+深证成指(399001)两个交易所，避免成分重叠
    market = {"main": 0.0, "super": 0.0, "large": 0.0, "mid": 0.0, "small": 0.0}
    for ex_code in ("000001", "399001"):
        if ex_code in result:
            for k in market:
                market[k] += result[ex_code][f"{'main' if k == 'main' else 'super' if k == 'super' else 'large' if k == 'large' else 'mid' if k == 'mid' else 'small'}_net_yi"]
    return {
        "indices": result,
        "market": {k: round(v, 2) for k, v in market.items()},
        "market_all6": {k: round(v, 2) for k, v in total.items()},
    }


# ============================================================
# 2. 北向资金（同花顺 hsgtApi）+ 本地缓存历史
# ============================================================

def get_northbound():
    """拉取北向资金当日净流入 + 写入/读取本地缓存历史"""
    url = "https://data.hexin.cn/market/hsgtApi/method/dayChart/"
    headers = {
        "User-Agent": UA,
        "Host": "data.hexin.cn",
        "Referer": "https://data.hexin.cn/",
    }
    try:
        r = requests.get(url, headers=headers, timeout=10)
        d = r.json()
        times = d.get("time", [])
        hgt = d.get("hgt", [])
        sgt = d.get("sgt", [])
        if not times:
            return {"date": "", "hgt_yi": None, "sgt_yi": None, "total_yi": None, "history": []}

        # 取最后一个非空值；sgt绝对值>300亿视为累计值异常，置None（当日净流入不会超过此量级）
        hgt_last = None
        sgt_last = None
        for v in reversed(hgt):
            if v is not None and v != "-":
                hgt_last = float(v)
                break
        for v in reversed(sgt):
            if v is not None and v != "-" and abs(float(v)) <= 300:
                sgt_last = float(v)
                break

        today = date.today().strftime("%Y-%m-%d")

        # 写入缓存
        cache_path = os.path.join(os.path.dirname(__file__), "..", "data", "northbound_cache.csv")
        cache_path = os.path.abspath(cache_path)
        rows = {}
        if os.path.exists(cache_path):
            for line in open(cache_path, encoding="utf-8").read().strip().split("\n")[1:]:
                parts = line.split(",")
                if len(parts) == 3:
                    rows[parts[0]] = line
        if hgt_last is not None or sgt_last is not None:
            rows[today] = f"{today},{hgt_last if hgt_last is not None else ''},{sgt_last if sgt_last is not None else ''}"
        with open(cache_path, "w", encoding="utf-8") as f:
            f.write("date,hgt_yi,sgt_yi\n")
            for d_key in sorted(rows.keys()):
                f.write(rows[d_key] + "\n")

        # 读取最近20日历史
        history = []
        for d_key in sorted(rows.keys())[-20:]:
            parts = rows[d_key].split(",")
            history.append({
                "date": parts[0],
                "hgt_yi": float(parts[1]) if parts[1] else None,
                "sgt_yi": float(parts[2]) if parts[2] else None,
            })

        total = None
        if hgt_last is not None and sgt_last is not None:
            total = round(hgt_last + sgt_last, 2)

        return {
            "date": today,
            "hgt_yi": round(hgt_last, 2) if hgt_last is not None else None,
            "sgt_yi": round(sgt_last, 2) if sgt_last is not None else None,
            "total_yi": total,
            "history": history,
        }
    except Exception as e:
        print(f"[WARN] northbound: {e}")
        return {"date": "", "hgt_yi": None, "sgt_yi": None, "total_yi": None, "history": []}


# ============================================================
# 3. 行业板块资金流（东财 push2 clist, m:90+t:2）
# ============================================================

def get_industry_fund_flow(top_n=10):
    """行业板块主力资金净流入/流出TOP"""
    url = "https://push2.eastmoney.com/api/qt/clist/get"
    params = {
        "pn": "1", "pz": "100", "po": "1", "np": "1",
        "fltt": "2", "invt": "2", "fs": "m:90+t:2",
        "fields": "f2,f3,f12,f14,f62,f66,f72,f78,f84,f184",
    }
    headers = {"User-Agent": UA, "Referer": "https://quote.eastmoney.com/"}
    try:
        r = em_get(url, params=params, headers=headers, timeout=12)
        d = r.json()
        items = d.get("data", {}).get("diff", [])
        if not items:
            return {"in_top": [], "out_top": []}

        rows = []
        for it in items:
            rows.append({
                "name": it.get("f14", ""),
                "change_pct": it.get("f3", 0),
                "main_net_yi": round((it.get("f62") or 0) / 1e8, 2),
                "super_net_yi": round((it.get("f66") or 0) / 1e8, 2),
                "main_ratio": round(it.get("f184") or 0, 2),
            })
        rows.sort(key=lambda x: x["main_net_yi"], reverse=True)
        return {
            "in_top": rows[:top_n],
            "out_top": list(reversed(rows[-top_n:])),
        }
    except Exception as e:
        print(f"[WARN] industry fund flow: {e}")
        return {"in_top": [], "out_top": []}


# ============================================================
# 4. 指数成交量（腾讯实时行情 vol_ratio 字段49）
# ============================================================

def get_tencent_quote(codes):
    """腾讯实时行情完整字段（指数）"""
    prefixed = []
    for c in codes:
        if c.startswith("3"):
            prefixed.append(f"sz{c}")
        else:
            prefixed.append(f"sh{c}")
    url = "https://qt.gtimg.cn/q=" + ",".join(prefixed)
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "Mozilla/5.0")
    resp = urllib.request.urlopen(req, timeout=10)
    data = resp.read().decode("gbk")
    result = {}
    for line in data.strip().split(";"):
        if '"' not in line:
            continue
        key = line.split("=")[0].split("_")[-1]
        vals = line.split('"')[1].split("~")
        if len(vals) < 50:
            continue
        code = key[2:]
        result[code] = {
            "name": vals[1],
            "price": float(vals[3]) if vals[3] else 0,
            "change_pct": float(vals[32]) if vals[32] else 0,
            "amount_yi": round(float(vals[37]) / 10000, 1),  # 万→亿
            "vol_ratio": float(vals[49]) if vals[49] else None,  # 量比(相对5日同时段)
        }
    return result


def get_index_volume_ratio():
    """主要指数量比 + 成交额（腾讯实时 vol_ratio 字段）
    vol_ratio>1.3=放量, 0.9-1.3=平量, <0.9=缩量
    """
    codes = ["000001", "399001", "399006", "000300", "000688", "000016"]
    q = get_tencent_quote(codes)
    result = {}
    for code, v in q.items():
        ratio = v.get("vol_ratio")
        result[code] = {
            "name": v["name"],
            "change_pct": v["change_pct"],
            "amount_yi": v["amount_yi"],
            "ratio_5d": ratio,
            "vol_note": f"放量{ratio:.1f}倍" if ratio and ratio >= 1.3 else
                        ("平量" if ratio and ratio >= 0.9 else
                         (f"缩量至{ratio:.2f}倍" if ratio else "数据不足")),
        }
    return result


def get_total_amount():
    """两市总成交额（上证+深成，腾讯财经，亿元）"""
    q = get_tencent_quote(["000001", "399001"])
    return round(sum(v["amount_yi"] for v in q.values()), 1)


# ============================================================
# MAIN
# ============================================================

def main():
    output = {}

    print("[1/4] 拉取指数资金流...")
    flow = get_index_fund_flow()
    output["indices"] = flow["indices"]
    output["market"] = flow["market"]
    if output["market"]:
        m = output["market"]
        print(f"  主力净流入合计: {m['main']:.1f}亿 (超大单{m['super']:.1f}亿/中单{m['mid']:.1f}亿/散户{m['small']:.1f}亿)")

    print("[2/4] 拉取北向资金...")
    nb = get_northbound()
    output["northbound"] = nb
    print(f"  沪股通={nb.get('hgt_yi')}亿 深股通={nb.get('sgt_yi')}亿 合计={nb.get('total_yi')}亿 历史{len(nb.get('history', []))}天")

    print("[3/4] 拉取行业板块资金流...")
    ind_flow = get_industry_fund_flow(10)
    output["industry_flow"] = ind_flow
    print(f"  流入TOP5: {', '.join(i['name'] for i in ind_flow['in_top'][:5])}")
    print(f"  流出TOP5: {', '.join(i['name'] for i in ind_flow['out_top'][:5])}")

    print("[4/4] 拉取指数成交量...")
    vol = get_index_volume_ratio()
    output["volume"] = vol
    for code, v in vol.items():
        print(f"  {v['name']}: 量比{v['ratio_5d']}x {v['vol_note']} 成交额{v['amount_yi']}亿")
    output["total_amount_yi"] = get_total_amount()
    print(f"  两市总成交额: {output['total_amount_yi']}亿")

    output["fetch_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 写入 market_data.json
    json_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "market_data.json"))
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)
    data["fund_flow"] = output
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\n[OK] fund_flow 已写入 {json_path}")


if __name__ == "__main__":
    main()
