import pandas as pd
import numpy as np
from sklearn.model_selection import ParameterGrid
from joblib import Parallel, delayed
from typing import Dict, List, Tuple, Optional
import sys
import io
import builtins

from src.volatility_calculator import VolatilityCalculator
from src.signal_generator import SignalGenerator
from src.backtest import Backtester

class GridSearch:
    def __init__(self, df_base: pd.DataFrame, start_date: str = "2024-01-01"):
        self.df_base = df_base
        self.start_date = start_date

    def _evaluate_params(self, params: dict) -> dict:
        """评估单组参数"""
        try:
            # 1. 计算指标 (全样本用于 warm-up)
            df = VolatilityCalculator.compute_indicators(self.df_base, vol_smooth_period=params.get('vol_smooth_period', 5))
            
            # 2. 计算滚动分位数
            window = params.get('window_days', 60) * 54
            df = VolatilityCalculator.compute_rolling_quantiles(df, window, params)
            
            # 3. 生成信号与风控
            df = SignalGenerator.generate_signals(df, params)
            df = SignalGenerator.run_path_dependent_risk_control(df, params)
            
            # 4. 回测 (截取 start_date)
            backtester = Backtester()
            perf_df = backtester.calculate_performance(df, start_date=self.start_date)
            
            if perf_df.empty:
                return {'sharpe_ratio': -999, **params}
            
            metrics = backtester.get_metrics(perf_df)
            return {**metrics, **params}
            
        except Exception as e:
            return {'sharpe_ratio': -999, 'error': str(e), **params}

    def run(self, param_grid: dict, n_jobs: int = -1) -> Tuple[pd.DataFrame, dict]:
        grid = list(ParameterGrid(param_grid))
        print(f"Running grid search with {len(grid)} combinations...")
        
        # 禁用 print 以保持输出整洁
        original_print = builtins.print
        builtins.print = lambda *args, **kwargs: None
        
        try:
            results = Parallel(n_jobs=n_jobs, verbose=0)(
                delayed(self._evaluate_params)(p) for p in grid
            )
        finally:
            builtins.print = original_print
            
        df_results = pd.DataFrame(results)
        df_results = df_results[df_results['sharpe_ratio'] != -999].sort_values('sharpe_ratio', ascending=False)
        df_results.reset_index(drop=True, inplace=True)
        
        best_params = {}
        if not df_results.empty:
            # 提取非指标列作为参数
            metric_cols = {"total_return", "annualized_return", "annualized_volatility", "sharpe_ratio", 
                           "max_drawdown", "calmar_ratio", "win_rate", "turnover", "long_ratio", 
                           "short_ratio", "flat_ratio", "error"}
            best_row = df_results.iloc[0]
            best_params = {k: v for k, v in best_row.items() if k not in metric_cols}
            
            # 还原整型
            int_fields = {'window_days', 'vol_smooth_period', 'max_consecutive_losses', 'loss_cooldown_bars'}
            best_params = {k: (int(v) if k in int_fields else v) for k, v in best_params.items()}
            
        return df_results, best_params
