# A股每日复盘 V3.0 — ETF异动择时模型

> 自动化 A 股收盘数据观测与复盘分析系统。每日 15:00 自动生成两份报告。

## 双模版体系

| 报告 | 说明 | 位置 |
|------|------|------|
| **模版1：今日看板** | 20章数据仪表盘，含指数/ETF/情绪/资金/信号等 | `reports/YYYYMMDD.md` |
| **模版2：复盘分析** | 基于模型的策略分析，含仓位建议/趋势判断 | `analysis/YYYYMMDD.md` |

## 触发方式

- **定时**：每个交易日 15:00 自动生成
- **手动**：在 WorkBuddy 中说「今日看板」手动触发
- 生成后自动推送到本仓库

## 仓库结构

```
index.html                # 首页（展示当日最新复盘数据）
latest.md                 # 固定入口：最新今日看板
latest_analysis.md        # 固定入口：最新复盘分析
trade_signal.md           # 交易策略文档
templates/                # 模版格式说明
├── daily-dashboard.md    # 模版1格式
└── review-analysis.md    # 模版2格式
reports/                  # 历史今日看板归档
├── 20260722.md
├── 20260723.md
├── 20260724.md
└── YYYYMMDD.md
analysis/                 # 历史复盘分析归档
└── YYYYMMDD.md
```

## 数据来源

- 通达信 MCP（行情/K线/资金流向）
- 腾讯自选股（市场数据）
- 公开市场数据

## 分析模型

### 信号阈值定义（ABCD 条件）
- **A**: 下跌家数 > 3500
- **B**: ETF 放量倍数 ≥ 1.5x（至少 2 只）
- **C**: 两市成交额 > 2 万亿
- **D**: 跌停家数 > 50

### 信号等级
- 0 星：无 ETF 放量
- 1 星：关注
- 2 星：警惕
- 3 星：重视
- 4 星：重点跟踪
- 5 星：极端拐点信号

### 观察 ETF 标的
| ETF | 代码 | 说明 |
|-----|------|------|
| 沪深300ETF | 510300 | 大盘价值风向标 |
| 创业板ETF | 159915 | 成长科技风向标 |
| 科创50ETF | 588000 | 硬科技风向标 |
| 半导体ETF | 512480 | 科技板块风向标 |

## 链接格式

| 用途 | 链接 |
|------|------|
| 带样式预览 | `https://zxcchen.github.io/a-stock-etf-daily-review/` |
| 最新看板（AI入口） | `https://zxcchen.github.io/a-stock-etf-daily-review/latest.txt` |
| 最新复盘（AI入口） | `https://raw.githubusercontent.com/zxcchen/a-stock-etf-daily-review/main/latest_analysis.md` |
| 历史报告 | `https://raw.githubusercontent.com/zxcchen/a-stock-etf-daily-review/main/reports/YYYYMMDD.md` |

## 免责声明

本报告仅提供客观数据统计，不构成任何投资建议。投资有风险，决策需谨慎。
