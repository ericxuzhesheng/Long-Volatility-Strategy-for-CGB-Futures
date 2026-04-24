# 做多波动率国债期货择时策略 | Long-Volatility Strategy for CGB Futures

<p align="center">
  <a href="#zh"><img src="https://img.shields.io/badge/LANGUAGE-%E4%B8%AD%E6%96%87-E84D3D?style=for-the-badge&labelColor=3B3F47" alt="LANGUAGE 中文"></a>
  <a href="#en"><img src="https://img.shields.io/badge/LANGUAGE-ENGLISH-2F73C9?style=for-the-badge&labelColor=3B3F47" alt="LANGUAGE ENGLISH"></a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.8%2B-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.8+">
  <img src="https://img.shields.io/badge/Asset-CGB%20Futures-F2C94C?style=for-the-badge" alt="CGB Futures">
  <img src="https://img.shields.io/badge/Strategy-Long%20Volatility%20Timing-7AC943?style=for-the-badge" alt="Long Volatility Timing">
</p>

<a id="zh"></a>

## 简体中文

当前语言：中文 | [Switch to English](#en)

### 1. 项目简介
本项目是一个基于国债期货（10年期 T 和 30年期 TL）5分钟高频数据的**做多波动率择时策略**。策略的核心逻辑是利用实现波动率（Realized Volatility）及其变动趋势来识别市场的情绪切换或趋势加速阶段，通过期货方向性仓位间接获取波动率扩张带来的收益。

### 2. 策略原理
本项目并非期权意义上的 Delta 中性做多波动率，而是基于期货方向仓位的 **Long-Volatility Timing Proxy**。
- **核心逻辑**：当市场进入波动率扩张状态（Realized Volatility 显著上升且处于低位起始）时，往往伴随着资金面冲击、政策预期变化或拥挤交易的释放，此时价格趋势更容易形成连续行情。
- **因子构建**：使用 TA-Lib 计算 NATR（归一化 ATR），并对其进行 SMA 平滑、求一阶差分（Trend）和二阶差分（Speed）。
- **信号生成**：
  - **做多**：波动率处于低分位（q30以下）且速度向下（speed < speed_q_low），代表市场极度平稳后可能出现的转向或底部。
  - **做空**：波动率处于高分位（q80以上）且速度向上（speed > speed_q_high），代表波动率剧烈扩张，市场进入高风险/高波动区间。
- **风控**：引入最大连续亏损限制和冷却期机制。

### 3. 快速开始
1. 安装依赖：`pip install -r requirements.txt`
2. 运行完整 Pipeline：
   ```bash
   python scripts/run_volatility_pipeline.py --contract ALL --start-date 2024-01-01 --run-grid-search
   ```

### 4. 结果展示
*注：以下结果为回测示例，具体绩效请运行 pipeline 后查看 `results/report.md`。*

| 合约 | 年化收益 | 年化波动 | 夏普比率 | 最大回撤 | 胜率 |
| :--- | :---: | :---: | :---: | :---: | :---: |
| T | 1.71% | 2.02% | -0.14 | 1.92% | 43.34% |
| TL | 10.06% | 4.95% | 1.63 | 3.38% | 46.32% |

---

<a id="en"></a>

## English

Current language: English | [切换到中文](#zh)

### 1. Project Overview
This project implements a **Long-Volatility Timing Strategy** for China Government Bond (CGB) Futures (10Y T and 30Y TL) using 5-minute intraday data. The strategy identifies market regime shifts or trend acceleration by analyzing realized volatility and its dynamics.

### 2. Strategy Intuition
This project is **not** a Delta-neutral long volatility portfolio in the options sense. It is a **Long-Volatility Timing Proxy** based on directional futures positions.
- **Core Idea**: When market volatility expands (Realized Volatility rises significantly from low levels), it often signifies liquidity shocks, policy expectation shifts, or crowded trade unwinding. Price trends are more likely to be persistent during these phases.
- **Factor Construction**: Calculated using TA-Lib NATR (Normalized ATR), followed by SMA smoothing, first-order derivative (Trend), and second-order derivative (Speed).
- **Signal Logic**:
  - **Long**: Volatility at low quantiles (below q30) and speed is negative, indicating a potential reversal or base after extreme calmness.
  - **Short**: Volatility at high quantiles (above q80) and speed is positive, indicating rapid volatility expansion and high-risk regimes.
- **Risk Management**: Includes maximum consecutive loss limits and cooldown periods.

### 3. Quick Start
1. Install dependencies: `pip install -r requirements.txt`
2. Run full Pipeline:
   ```bash
   python scripts/run_volatility_pipeline.py --contract ALL --start-date 2024-01-01 --run-grid-search
   ```

### 4. Results
| Contract | Annualized Return | Annualized Volatility | Sharpe Ratio | Max Drawdown | Win Rate |
| :--- | :---: | :---: | :---: | :---: | :---: |
| T | 1.71% | 2.02% | -0.14 | 1.92% | 43.34% |
| TL | 10.06% | 4.95% | 1.63 | 3.38% | 46.32% |

---

## Disclaimer
This project is for research purposes only and does not constitute investment advice. Backtest results do not guarantee future performance.
