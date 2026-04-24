import os
import json
import pandas as pd
from datetime import datetime

class ReportGenerator:
    def __init__(self, output_dir: str):
        self.output_dir = output_dir

    def save_best_params(self, best_params: dict, contract: str):
        path = os.path.join(self.output_dir, "tables", f"best_params_{contract}.json")
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(best_params, f, indent=4, ensure_ascii=False)
        print(f"Best params for {contract} saved to {path}")

    def save_summary_table(self, metrics: dict, contract: str):
        path = os.path.join(self.output_dir, "tables", f"backtest_summary_{contract}.csv")
        df = pd.DataFrame([metrics])
        df.to_csv(path, index=False, encoding='utf-8-sig')
        return df

    def generate_final_report(self, summaries: dict):
        # summaries: { 'T': metrics_dict, 'TL': metrics_dict }
        report_path = os.path.join(self.output_dir, "report.md")
        
        content = f"""# Long-Volatility Strategy Research Report
Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## 1. Strategy Overview
This project implements a **long-volatility timing proxy** for CGB Futures (T & TL) using 5-minute intraday data. The core idea is to capture trend expansion during volatility regime switches.

## 2. Performance Summary
| Contract | Annualized Return | Annualized Volatility | Sharpe Ratio | Max Drawdown | Calmar | Win Rate |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
"""
        for contract, m in summaries.items():
            content += f"| {contract} | {m.get('annualized_return', 0):.2%} | {m.get('annualized_volatility', 0):.2%} | {m.get('sharpe_ratio', 0):.2f} | {m.get('max_drawdown', 0):.2%} | {m.get('calmar_ratio', 0):.2f} | {m.get('win_rate', 0):.2%} |\n"

        content += """
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
"""
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"Final report generated at {report_path}")
