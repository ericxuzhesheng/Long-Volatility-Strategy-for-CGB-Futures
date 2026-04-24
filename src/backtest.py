import pandas as pd
import numpy as np
from typing import Dict

class Backtester:
    def __init__(self, periods_per_year: int = 252 * 54):
        self.periods_per_year = periods_per_year

    def calculate_performance(self, df: pd.DataFrame, start_date: str = "2024-01-01") -> pd.DataFrame:
        """
        计算回测指标。必须确保 shift(1) 防止未来函数。
        """
        df = df.copy()
        
        # 截取起始日期
        if start_date:
            df = df[df['datetime'] >= pd.to_datetime(start_date)].copy()
        
        if df.empty:
            return pd.DataFrame()

        # 基准收益率
        df['ret_bh'] = df['close'].pct_change().fillna(0.0)
        
        # 策略收益率 = 上一期权重 * 本期收益率
        # 注意：df['weight'] 已经是当前 5min bar 结束后的持仓权重
        # 交易执行发生在下一根 bar 开盘，或者等效于在本根 bar 收益率上应用上一根 bar 的权重
        df['ret_strat'] = df['weight'].shift(1).fillna(0.0) * df['ret_bh']
        
        # 累计收益
        df['nav_bh'] = (1.0 + df['ret_bh']).cumprod()
        df['nav_strat'] = (1.0 + df['ret_strat']).cumprod()
        
        # 超额收益
        df['ret_excess'] = df['ret_strat'] - df['ret_bh']
        df['nav_excess'] = (1.0 + df['ret_excess']).cumprod()
        
        return df

    def get_metrics(self, perf_df: pd.DataFrame) -> Dict:
        """
        汇总绩效指标
        """
        if perf_df.empty:
            return {}

        total_ret = perf_df['nav_strat'].iloc[-1] - 1
        ann_ret = (1 + total_ret) ** (self.periods_per_year / len(perf_df)) - 1
        
        vol = perf_df['ret_strat'].std() * np.sqrt(self.periods_per_year)
        sharpe = (ann_ret - 0.02) / vol if vol != 0 else 0.0
        
        # 最大回撤
        nav = perf_df['nav_strat']
        dd = (nav.cummax() - nav) / nav.cummax()
        max_dd = dd.max()
        
        calmar = ann_ret / max_dd if max_dd != 0 else 0.0
        
        # 胜率 (仅统计非空仓时段的收益)
        active_ret = perf_df[perf_df['weight'].shift(1) != 0]['ret_strat']
        win_rate = (active_ret > 0).mean() if not active_ret.empty else 0.0
        
        # 换手率 (权重绝对值变化之和)
        turnover = perf_df['weight'].diff().abs().sum() / 2 # 简化计算
        
        # 仓位比例
        long_ratio = (perf_df['weight'] > 0).mean()
        short_ratio = (perf_df['weight'] < 0).mean()
        flat_ratio = (perf_df['weight'] == 0).mean()
        
        return {
            "total_return": total_ret,
            "annualized_return": ann_ret,
            "annualized_volatility": vol,
            "sharpe_ratio": sharpe,
            "max_drawdown": max_dd,
            "calmar_ratio": calmar,
            "win_rate": win_rate,
            "turnover": turnover,
            "long_ratio": long_ratio,
            "short_ratio": short_ratio,
            "flat_ratio": flat_ratio
        }
