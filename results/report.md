# Long-Volatility Strategy Research Report
Generated at: 2026-04-24 17:00:40

## 1. Strategy Overview
This project implements a **long-volatility timing proxy** for CGB Futures (T & TL) using 5-minute intraday data. The core idea is to capture trend expansion during volatility regime switches.

## 2. Performance Summary
| Contract | Annualized Return | Annualized Volatility | Sharpe Ratio | Max Drawdown | Calmar | Win Rate |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| T | 1.71% | 2.02% | -0.14 | 1.92% | 0.89 | 43.34% |
| TL | 10.06% | 4.95% | 1.63 | 3.38% | 2.98 | 46.32% |

## 3. Visual Analysis
### 3.1 10Y CGB Futures (T)
![NAV T](figures/nav_comparison_T.png)
![Drawdown T](figures/drawdown_T.png)
![Signals T](figures/volatility_signal_T.png)
![Position T](figures/position_T.png)

### 3.2 30Y CGB Futures (TL)
![NAV TL](figures/nav_comparison_TL.png)
![Drawdown TL](figures/drawdown_TL.png)
![Signals TL](figures/volatility_signal_TL.png)
![Position TL](figures/position_TL.png)

## 4. Methodology
- **Data Frequency**: 5-minute OHLC.
- **Indicators**: TA-Lib NATR (Normalized ATR) with SMA smoothing.
- **Backtest Start**: 2024-01-01.
- **Execution**: `shift(1)` applied to positions to prevent look-ahead bias.
- **Grid Search**: In-sample parameter optimization for each contract independently.

## 5. Disclaimer
This is a research framework and does not constitute investment advice. Past performance is not indicative of future results.
