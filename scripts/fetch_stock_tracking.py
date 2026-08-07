#!/usr/bin/env python3
"""个股追踪数据拉取脚本 - 使用mootdx获取K线 + 手动计算技术指标"""

import json
import sys
import os
from datetime import datetime, date

# 添加父目录到path以导入fetch_data模块
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from fetch_data import get_klines, calc_indicators

STOCKS = [
    ("002080", "中材科技", 0, "玻璃纤维/建材"),
    ("600160", "巨化股份", 1, "氟化工/化学制品"),
    ("000920", "沃顿科技", 0, "环保/膜材料"),
    ("603290", "斯达半导", 1, "半导体/IGBT"),
    ("000063", "中兴通讯", 0, "通信设备/5G"),
    ("002803", "吉宏股份", 0, "跨境电商"),
]

def main():
    output = {}
    today_str = date.today().strftime("%Y%m%d")

    # Step 1: 确认交易日 - 查600160近3根日线
    print("=" * 60)
    print("Step 1: 确认交易日 (600160 近3根日线)")
    print("=" * 60)
    klines_check = get_klines("600160", count=3, category=4)
    if not klines_check:
        print("[ERROR] 无法获取600160 K线数据")
        output["trading_day"] = False
        output["error"] = "无法获取600160 K线数据"
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return

    latest_date = klines_check[-1]["datetime"][:10].replace("-", "")
    print(f"  最新K线日期: {latest_date}")
    print(f"  今日日期: {today_str}")
    is_trading_day = (latest_date == today_str)
    output["trading_day"] = is_trading_day
    output["latest_date"] = latest_date
    output["today"] = today_str

    if not is_trading_day:
        print(f"  [非交易日] 最新日期{latest_date} != 今日{today_str}")
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return

    print(f"  [交易日确认通过]")

    # Step 2: 并行拉取6只个股K线 (65根用于MA60) + 技术指标
    print("\n" + "=" * 60)
    print("Step 2: 拉取6只个股K线 + 技术指标")
    print("=" * 60)

    output["stocks"] = {}
    for code, name, setcode, industry in STOCKS:
        print(f"\n  [{code} {name}] 拉取65根日线...")
        klines = get_klines(code, count=65, category=4)
        if not klines:
            print(f"    [ERROR] 获取失败")
            output["stocks"][code] = {"error": "获取K线失败"}
            continue

        latest = klines[-1]["datetime"][:10].replace("-", "")
        print(f"    共{len(klines)}根K线, 最新日期={latest}")

        # 近6日K线用于展示
        recent_6 = klines[-6:]
        print(f"    近6日收盘: {[k['close'] for k in recent_6]}")

        # 计算技术指标
        indicators = calc_indicators(klines)
        if indicators:
            print(f"    MA5={indicators.get('MA5')} MA10={indicators.get('MA10')} MA20={indicators.get('MA20')} MA60={indicators.get('MA60')}")
            print(f"    MACD: DIF={indicators.get('MACD_DIF')} DEA={indicators.get('MACD_DEA')} HIST={indicators.get('MACD_HIST')}")
            print(f"    KDJ: K={indicators.get('KDJ_K')} D={indicators.get('KDJ_D')} J={indicators.get('KDJ_J')}")
            print(f"    RSI6={indicators.get('RSI_6')} RSI12={indicators.get('RSI_12')}")
            print(f"    BOLL: MID={indicators.get('BOLL_MID')} UPPER={indicators.get('BOLL_UPPER')} LOWER={indicators.get('BOLL_LOWER')}")

        # 5日涨跌计算
        if len(klines) >= 6:
            close_5d_ago = klines[-6]["close"]
            close_today = klines[-1]["close"]
            change_5d = round((close_today - close_5d_ago) / close_5d_ago * 100, 2)
        else:
            change_5d = None

        # 今日涨跌
        if len(klines) >= 2:
            close_yesterday = klines[-2]["close"]
            close_today = klines[-1]["close"]
            change_today = round((close_today - close_yesterday) / close_yesterday * 100, 2)
        else:
            change_today = None

        output["stocks"][code] = {
            "name": name,
            "setcode": setcode,
            "industry": industry,
            "klines_6d": recent_6,
            "indicators": indicators,
            "change_5d_pct": change_5d,
            "change_today_pct": change_today,
            "latest_date": latest,
        }

    # 输出JSON
    output["fetch_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    json_path = os.path.join(os.path.dirname(__file__), "..", "data", "stock_tracking_data.json")
    os.makedirs(os.path.dirname(json_path), exist_ok=True)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n{'=' * 60}")
    print(f"[OK] 数据已保存到 {json_path}")
    print(f"     采集时间: {output['fetch_time']}")

    # 同时输出到stdout供解析
    print("\n---JSON_START---")
    print(json.dumps(output, ensure_ascii=False, default=str))
    print("---JSON_END---")

if __name__ == "__main__":
    main()
