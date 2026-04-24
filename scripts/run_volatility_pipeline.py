import sys
import os
import argparse
import pandas as pd
from datetime import datetime

# Add root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data_loader import DataLoader
from src.volatility_calculator import VolatilityCalculator
from src.signal_generator import SignalGenerator
from src.backtest import Backtester
from src.grid_search import GridSearch
from src.visualization import Visualizer
from src.report_generator import ReportGenerator
from src.utils import setup_cn_font, ensure_dir

CONTRACT_CONFIGS = {
    "T": {
        "name": "10Y CGB Futures",
        "file": "10年国债期货_5min_3年.xlsx",
        "sheet_name": "Sheet1",
    },
    "TL": {
        "name": "30Y CGB Futures",
        "file": "30年国债期货_5min_2年.xlsx",
        "sheet_name": "Sheet1",
    },
}

DEFAULT_PARAM_GRID = {
    'window_days':      [40, 60, 80],
    'vol_smooth_period': [3, 5, 8],
    'q_low_risk':       [0.2, 0.3, 0.4],
    'q_neutral_high':   [0.70, 0.80, 0.90],
    'sig_vol_high':     [0.80, 0.90],
    'sig_speed_high':   [0.80, 0.90],
    'sig_speed_low':    [0.30, 0.40],
    'risk_speed_cap':   [0.80, 0.90],
}

DEFAULT_PARAMS = {
    'window_days': 60,
    'vol_smooth_period': 5,
    'q_low_risk': 0.3,
    'q_neutral_high': 0.8,
    'sig_vol_high': 0.9,
    'sig_speed_high': 0.9,
    'sig_speed_low': 0.4,
    'risk_speed_cap': 0.9,
    'max_consecutive_losses': 3,
    'loss_cooldown_bars': 108
}

def run_contract_pipeline(contract_code, args):
    print(f"\n{'='*20} Processing {contract_code} {'='*20}")
    config = CONTRACT_CONFIGS[contract_code]
    
    # 1. Load Data
    loader = DataLoader(config['file'], sheet_name=config.get('sheet_name'))
    df_base = loader.load_data()
    
    # 2. Grid Search (Optional)
    params = DEFAULT_PARAMS.copy()
    if args.run_grid_search:
        gs = GridSearch(df_base, start_date=args.start_date)
        df_grid, best_params = gs.run(DEFAULT_PARAM_GRID)
        params.update(best_params)
        
        # Save grid search results
        grid_path = os.path.join("results", "tables", f"grid_search_{contract_code}.csv")
        df_grid.to_csv(grid_path, index=False, encoding='utf-8-sig')
        
        # Save best params
        ReportGenerator("results").save_best_params(params, contract_code)
    
    # 3. Final Run with Best/Default Params
    # Indicator calculation on full data
    df = VolatilityCalculator.compute_indicators(df_base, vol_smooth_period=params['vol_smooth_period'])
    window = params['window_days'] * 54
    df = VolatilityCalculator.compute_rolling_quantiles(df, window, params)
    
    # Signal and position
    df = SignalGenerator.generate_signals(df, params)
    df = SignalGenerator.run_path_dependent_risk_control(df, params)
    
    # Save processed data
    processed_path = os.path.join("data", "processed", f"volatility_{contract_code}_intraday.csv")
    df.to_csv(processed_path, index=False, encoding='utf-8-sig')
    
    # 4. Backtest
    backtester = Backtester()
    perf_df = backtester.calculate_performance(df, start_date=args.start_date)
    metrics = backtester.get_metrics(perf_df)
    
    # Save NAV
    nav_path = os.path.join("results", "tables", f"strategy_nav_{contract_code}.csv")
    perf_df[['datetime', 'nav_strat', 'nav_bh', 'nav_excess']].to_csv(nav_path, index=False)
    
    # Save Summary
    ReportGenerator("results").save_summary_table(metrics, contract_code)
    
    # 5. Visualization
    viz = Visualizer("results/figures")
    viz.plot_vol_analysis(df[df['datetime'] >= pd.to_datetime(args.start_date)], config['name'], f"volatility_signal_{contract_code}.png")
    viz.plot_nav_comparison(perf_df, f"NAV: {config['name']} Strategy vs Benchmark", f"nav_comparison_{contract_code}.png")
    viz.plot_drawdown(perf_df, f"Drawdown: {config['name']}", f"drawdown_{contract_code}.png")
    viz.plot_position(df[df['datetime'] >= pd.to_datetime(args.start_date)], f"Position: {config['name']}", f"position_{contract_code}.png")
    
    return metrics

def main():
    parser = argparse.ArgumentParser(description="Long-Volatility Strategy for CGB Futures Pipeline")
    parser.add_argument("--contract", type=str, default="ALL", choices=["T", "TL", "ALL"], help="Contract to run")
    parser.add_argument("--start-date", type=str, default="2024-01-01", help="Backtest start date")
    parser.add_argument("--run-grid-search", action="store_true", help="Run grid search for parameter optimization")
    args = parser.parse_args()
    
    setup_cn_font()
    ensure_dir("results/tables")
    ensure_dir("results/figures")
    ensure_dir("data/processed")
    
    contracts = ["T", "TL"] if args.contract == "ALL" else [args.contract]
    summaries = {}
    
    for c in contracts:
        try:
            summaries[c] = run_contract_pipeline(c, args)
        except Exception as e:
            print(f"Error processing {c}: {e}")
            import traceback
            traceback.print_exc()
            
    if summaries:
        # Generate summary CSV
        summary_df = pd.DataFrame(summaries).T
        summary_df.index.name = "Contract"
        summary_df.to_csv("results/tables/summary_T_TL.csv", encoding='utf-8-sig')
        
        # Generate Final Report
        rg = ReportGenerator("results")
        rg.generate_final_report(summaries)
        
        print("\nPipeline completed successfully.")
    else:
        print("\nNo contracts were processed.")

if __name__ == "__main__":
    main()
