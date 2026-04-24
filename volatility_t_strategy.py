"""
基于波动率因子的国债期货 T 合约多空择时策略系统

策略逻辑：
1. 核心因子：
   - vol_level：NATR_14 (归一化ATR)
   - vol_trend：一阶差分
   - vol_speed：二阶差分

2. 信号生成：
   - 做空：vol_level > 90%分位 & vol_speed > 90%分位 & vol_trend > 0 (持续2周期)
   - 做多：vol_level < 40%分位 & vol_speed < 40%分位 & vol_trend < 0 (持续2周期)

3. 风控机制：
   - 多头止损：vol_speed > 90%分位
   - 空头止盈：vol_level < 30%分位
   - 连续亏损限制：3次

"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Dict, List, Tuple
import os
import re
import sys
import io
import builtins
import warnings
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib as mpl
from tqdm import tqdm
from joblib import Parallel, delayed
from sklearn.model_selection import ParameterGrid
import talib

warnings.filterwarnings('ignore')

# =========================
# 0) 解决 matplotlib 中文显示
# =========================
def setup_cn_font():
    mpl.rcParams["font.sans-serif"] = [
        "Microsoft YaHei",
        "SimHei",
        "Arial Unicode MS",
        "DejaVu Sans",
    ]
    mpl.rcParams["axes.unicode_minus"] = False

@dataclass
class VolatilityParams:
    window_days: int = 60
    bars_per_day: int = 54
    winsorize_limits: Tuple[float, float] = (0.01, 0.01)
    
    # 分位数参数
    q_low_risk: float = 0.30        # 做多：波动率低于该分位时视为低风险区域
    q_neutral_high: float = 0.80    # 做空：波动率高于该分位时视为高风险区域
    q_high_risk: float = 0.80       # 划分高风险区
    
    # 信号阈值
    sig_vol_high: float = 0.90       # 做空：波动率高于该分位才允许开空
    sig_speed_high: float = 0.90    # 做空：波动率加速度高于该分位才允许开空
    sig_vol_low: float = 0.40       # 空头止盈：波动率低于该分位时平空
    sig_speed_low: float = 0.40     # 做多：波动率加速度低于该分位才允许开多
    
    # 数据预处理参数
    vol_smooth_period: int = 5      # 波动率平滑周期 (SMA)
      
    # 风控阈值
    risk_speed_cap: float = 0.90    # 多头止损
    risk_vol_exit: float = 0.30     # 空头止盈
    max_consecutive_losses: int = 3   # 连续亏损上限
    loss_cooldown_bars: int = 108  # 冷却期

class VolatilityStrategy:
    def __init__(self, excel_path: str, sheet_name: Optional[str] = None):
        self.excel_path = excel_path
        self.sheet_name = sheet_name
        self.df_5m: Optional[pd.DataFrame] = None
        self.result_df: Optional[pd.DataFrame] = None

    # =========================
    # 1) Excel读取（自动找表头）
    # =========================
    @staticmethod
    def _to_str(x) -> str:
        return "" if pd.isna(x) else str(x).strip()

    @staticmethod
    def _norm(x: str) -> str:
        return "".join(str(x).lower().split())

    @staticmethod
    def _find_header_row(
        raw: pd.DataFrame, keywords: List[str], search_rows: int = 50
    ) -> Optional[int]:
        kset = set([VolatilityStrategy._norm(k) for k in keywords])
        n = min(search_rows, len(raw))
        for i in range(n):
            row = [
                VolatilityStrategy._norm(VolatilityStrategy._to_str(v))
                for v in raw.iloc[i].tolist()
            ]
            if kset.issubset(set(row)):
                return i
        return None

    @staticmethod
    def _standardize_columns(cols: List[str]) -> Dict[str, str]:
        mapping = {}
        for c in cols:
            cn = VolatilityStrategy._norm(c)
            if cn in ("time", "datetime") or ("时间" in c):
                mapping[c] = "datetime"
            elif cn == "open" or ("开盘" in c):
                mapping[c] = "open"
            elif cn == "high" or ("最高" in c):
                mapping[c] = "high"
            elif cn == "low" or ("最低" in c):
                mapping[c] = "low"
            elif cn == "close" or ("收盘" in c) or ("结算" in c):
                mapping[c] = "close"
            elif cn in ("natr_14", "natr") or ("波动率" in c):
                mapping[c] = "vol_level" # 假设直接读取 NATR
        return mapping

    def load_excel(self) -> pd.DataFrame:
        print(f"Loading data from {self.excel_path}...")
        raw = pd.read_excel(self.excel_path, sheet_name=self.sheet_name, header=None)
        if raw.empty:
            raise ValueError("Excel读取为空。")

        header_row = self._find_header_row(
            raw, ["time", "close"], search_rows=50
        )

        if header_row is not None:
            header = [self._to_str(x) for x in raw.iloc[header_row].tolist()]
            data = raw.iloc[header_row + 1 :].copy()
            data.columns = header
        else:
            data = pd.read_excel(self.excel_path, sheet_name=self.sheet_name)

        data = data.dropna(axis=1, how="all")
        col_map = self._standardize_columns(
            [self._to_str(c) for c in list(data.columns)]
        )
        data = data.rename(columns=col_map)
        
        # 特殊处理：如果列名里没有 vol_level，尝试找 NATR_14
        if "vol_level" not in data.columns:
            # 尝试找名为 NATR_14 的列
            for c in data.columns:
                if "NATR_14" in str(c).upper():
                    data.rename(columns={c: "vol_level"}, inplace=True)
                    break
        
        need = {"datetime", "close", "vol_level"}
        missing = need - set(data.columns)
        if missing:
            raise ValueError(
                f"缺少关键字段：{sorted(missing)}；当前列：{list(data.columns)}"
            )

        data["datetime"] = pd.to_datetime(data["datetime"], errors="coerce")
        data = data.dropna(subset=["datetime"]).sort_values("datetime")
        # 去重
        data = data.drop_duplicates(subset=["datetime"], keep="last")
        
        for c in ["open", "high", "low", "close"]:
            if c in data.columns:
                data[c] = pd.to_numeric(data[c], errors="coerce")

        # 使用 TA-Lib 实时计算波动率指标，覆盖原有数据或新增
        print("Calculating volatility indicators using TA-Lib...")
        # TRANGE
        data['TRANGE'] = talib.TRANGE(data['high'], data['low'], data['close'])
        # ATR_14
        data['ATR_14'] = talib.ATR(data['high'], data['low'], data['close'], timeperiod=14)
        # NATR_14 -> vol_level
        data['NATR_14'] = talib.NATR(data['high'], data['low'], data['close'], timeperiod=14)
        data['vol_level'] = data['NATR_14']
        
        # 补充：计算 MA 均线用于趋势过滤
        data['ma_short'] = talib.SMA(data['close'], timeperiod=20)
        data['ma_long'] = talib.SMA(data['close'], timeperiod=60)

        self.df_5m = data.reset_index(drop=True)
        print(f"Data loaded. Shape: {self.df_5m.shape}")
        return self.df_5m

    # =========================
    # 2) 因子计算与处理
    # =========================
    def compute_factors(self, p: VolatilityParams) -> pd.DataFrame:
        if self.df_5m is None:
            raise RuntimeError("请先 load_excel()。")
            
        df = self.df_5m.copy()
        
        print("Calculating factors and thresholds...")
        
        # 1. 基础因子处理
        # 移除 Winsorize，避免过度平滑导致波动率变成一条直线
        # 仅保留轻度 SMA 平滑，减少随机噪音干扰
        
        # 注意：这里我们生成一个新的 'vol_level_smooth' 用于后续所有计算
        df['vol_level_smooth'] = talib.SMA(df['vol_level'].values, timeperiod=p.vol_smooth_period)
        # 填充 NaN (前几个值)
        df['vol_level_smooth'] = df['vol_level_smooth'].fillna(df['vol_level'])
        
        # 基于平滑后的波动率计算趋势和速度
        df['vol_trend'] = df['vol_level_smooth'].diff()
        df['vol_speed'] = df['vol_trend'].diff()
        
        # 2. 动态分位数阈值
        window_size = p.window_days * p.bars_per_day
        min_periods = window_size // 2
        
        # 使用 vol_level_smooth 计算滚动分位数
        roller = df['vol_level_smooth'].rolling(window=window_size, min_periods=min_periods)
        
        df['q30'] = roller.quantile(p.q_low_risk)
        df['q50'] = roller.quantile(0.50) # for risk control
        df['q70'] = roller.quantile(p.q_neutral_high)
        df['q80'] = roller.quantile(p.sig_vol_high) # for signal
        
        # vol_speed 的滚动分位数 (也基于平滑后的数据)
        speed_roller = df['vol_speed'].rolling(window=window_size, min_periods=min_periods)
        df['speed_q30'] = speed_roller.quantile(p.sig_speed_low)
        df['speed_q80'] = speed_roller.quantile(p.sig_speed_high)
        df['speed_q90'] = speed_roller.quantile(p.risk_speed_cap)
        
        # 3. 市场状态标记 (基于平滑值)
        conditions = [
            (df['vol_level_smooth'] < df['q30']),
            (df['vol_level_smooth'] >= df['q30']) & (df['vol_level_smooth'] <= df['q70']),
            (df['vol_level_smooth'] > df['q70'])
        ]
        choices = [1.2, 0.5, 1.0] # 仓位系数
        states = ['Low Risk', 'Neutral', 'High Risk']
        
        df['market_state'] = np.select(conditions, states, default='Unknown')
        df['pos_limit'] = np.select(conditions, choices, default=0.0)
        
        self.result_df = df
        return df

    # =========================
    # 3) 信号生成与风控执行
    # =========================
    def run_strategy(self, p: VolatilityParams) -> pd.DataFrame:
        if self.result_df is None:
            raise RuntimeError("请先 compute_factors()。")
            
        df = self.result_df.copy()
        print("Running signal generation and risk control...")
        
        # 1. 初始信号生成
        # 做空条件：
        # vol_level_smooth > 90%分位 & vol_speed > 90%分位 & vol_trend > 0 (持续2周期)
        short_cond = (
            (df['vol_level_smooth'] > df['q80']) &
            (df['vol_speed'] > df['speed_q80']) &
            (df['vol_trend'] > 0) &
            (df['vol_trend'].shift(1) > 0)
        )
        
        # 做多条件：
        # vol_level_smooth < 40%分位 & vol_speed < 40%分位 & vol_trend < 0 (持续2周期)
        long_cond = (
            (df['vol_level_smooth'] < df['q30']) &
            (df['vol_speed'] < df['speed_q30']) &
            (df['vol_trend'] < 0) &
            (df['vol_trend'].shift(1) < 0)
        )
        
        df['raw_signal'] = 0
        df.loc[short_cond, 'raw_signal'] = -1
        df.loc[long_cond, 'raw_signal'] = 1
        
        # 2. 风控与持仓模拟 (Path Dependent)
        # 转换为 numpy 加速
        n = len(df)
        closes = df['close'].values
        vol_levels = df['vol_level_smooth'].values # 使用平滑后的波动率
        vol_speeds = df['vol_speed'].values
        raw_signals = df['raw_signal'].values
        
        q50s = df['q50'].values
        speed_q90s = df['speed_q90'].values
        pos_limits = df['pos_limit'].values
        
        position = 0
        entry_price = 0.0
        consecutive_losses = 0
        loss_cooldown_counter = 0 # 冷却计数器
        
        positions = np.zeros(n)
        weights = np.zeros(n)
        
        for i in tqdm(range(1, n)):
            curr_signal = raw_signals[i]
            curr_close = closes[i]
            
            # 冷却期逻辑
            if loss_cooldown_counter > 0:
                loss_cooldown_counter -= 1
            
            # --- 风控检查 ---
            if position == 1: # 多头持仓
                # 止损: vol_speed > 90%分位
                if vol_speeds[i] > speed_q90s[i]:
                    if (curr_close - entry_price) < 0:
                        consecutive_losses += 1
                    else:
                        consecutive_losses = 0
                    position = 0
                    entry_price = 0
                    
            elif position == -1: # 空头持仓
                # 止盈: vol_level_smooth < 30%分位
                if vol_levels[i] < q50s[i]:
                    if (entry_price - curr_close) < 0:
                        consecutive_losses += 1
                    else:
                        consecutive_losses = 0
                    position = 0
                    entry_price = 0
            
            # --- 信号执行 (若无持仓) ---
            if curr_signal != 0:
                if consecutive_losses >= p.max_consecutive_losses:
                    # 触发最大连续亏损限制，进入冷却期
                    consecutive_losses = 0 # 重置计数
                    loss_cooldown_counter = p.loss_cooldown_bars # 设置冷却时间
                elif loss_cooldown_counter > 0:
                    # 冷却中，不开仓
                    pass
                else:
                    # 执行开仓/翻转
                    if curr_signal == 1:
                        position = 1
                        entry_price = curr_close
                    elif curr_signal == -1:
                        position = -1
                        entry_price = curr_close
            
            positions[i] = position
            weights[i] = position * pos_limits[i]
            
        df['position'] = positions
        df['weight'] = weights
        
        self.result_df = df
        return df

    # =========================
    # 4) 绩效计算
    # =========================
    @staticmethod
    def calc_excess_return(close: pd.Series, position: pd.Series, weight: Optional[pd.Series] = None) -> pd.DataFrame:
        df = pd.DataFrame({"close": close, "pos": position}).dropna(subset=["close"])
        if weight is not None:
            df['weight'] = weight
        else:
            df['weight'] = df['pos'] # 默认权重=持仓方向
            
        df["ret_bh"] = df["close"].pct_change()
        
        # 策略收益 = 上一期权重 * 本期收益率
        df["ret_strat"] = df["weight"].shift(1).fillna(0.0) * df["ret_bh"]
        
        df["ret_excess"] = df["ret_strat"] - df["ret_bh"]
        
        df["nav_bh"] = (1.0 + df["ret_bh"].fillna(0.0)).cumprod()
        df["nav_strat"] = (1.0 + df["ret_strat"].fillna(0.0)).cumprod()
        df["nav_excess"] = (1.0 + df["ret_excess"].fillna(0.0)).cumprod()
        
        return df

    # =========================
    # 5) 可视化模块 (参考 QRS)
    # =========================
    @staticmethod
    def _safe_filename(s: str) -> str:
        return re.sub(r'[\\/:*?"<>|]+', "_", s)

    @staticmethod
    def plot_vol_analysis(
        df: pd.DataFrame,
        title: str = "Volatility Analysis",
        save_dir: Optional[str] = None,
        fname: Optional[str] = None
    ):
        """
        绘制波动率因子、动态阈值与价格的对比
        """
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(16, 10), sharex=True)
        
        # 上图：价格
        ax1.plot(df.index, df['close'], label='Close Price')
        ax1.set_title(f"{title} - Price")
        ax1.legend()
        ax1.grid(True, alpha=0.3)
        
        # 下图：波动率 + 阈值
        ax2.plot(df.index, df['vol_level_smooth'], label='Vol Level Smooth', color='blue', linewidth=1)
        ax2.plot(df.index, df['q30'], '--', label='30% Q', color='green', alpha=0.7)
        ax2.plot(df.index, df['q70'], '--', label='70% Q', color='orange', alpha=0.7)
        ax2.plot(df.index, df['q80'], '--', label='80% Q', color='red', alpha=0.7)
        
        # 填充中性区
        ax2.fill_between(df.index, df['q30'], df['q70'], color='gray', alpha=0.1, label='Neutral Zone')
        
        ax2.set_title(f"{title} - Volatility Factor & Thresholds")
        ax2.legend(loc='upper left')
        ax2.grid(True, alpha=0.3)
        
        plt.tight_layout()
        
        if save_dir:
            os.makedirs(save_dir, exist_ok=True)
            if fname is None:
                fname = "vol_analysis.png"
            plt.savefig(os.path.join(save_dir, fname), dpi=200, bbox_inches='tight')
            
        plt.show()

    @staticmethod
    def plot_nav_compare(
        perf_df: pd.DataFrame,
        title: str = "NAV: Strategy vs Benchmark",
        save_dir: Optional[str] = None,
        fname: Optional[str] = None,
    ):
        fig, ax = plt.subplots(figsize=(16, 6))
        ax.plot(perf_df.index, perf_df["nav_strat"], label="Strategy NAV", linewidth=1.6, color='red')
        ax.plot(perf_df.index, perf_df["nav_bh"], label="Benchmark NAV", linewidth=1.6, color='gray', alpha=0.7)
        ax.plot(perf_df.index, perf_df["nav_excess"], label="Excess NAV", linewidth=1.6, color='blue', linestyle='--')

        ax.set_title(title)
        ax.grid(True, alpha=0.25)
        ax.legend(loc="upper left", frameon=False)
        
        if save_dir:
            os.makedirs(save_dir, exist_ok=True)
            if fname is None:
                fname = "nav_compare.png"
            plt.savefig(os.path.join(save_dir, fname), dpi=200, bbox_inches='tight')

        plt.show()

    @staticmethod
    def plot_price_with_signals(
        df: pd.DataFrame,
        title: str = "Price with Signals",
        save_dir: Optional[str] = None,
        fname: Optional[str] = None
    ):
        """
        绘制价格曲线及多空信号点
        """
        fig, ax = plt.subplots(figsize=(16, 6))
        ax.plot(df.index, df['close'], label='Close', color='black', alpha=0.6)
        
        # 提取信号点
        # raw_signal: 1 (Long), -1 (Short)
        long_idx = df[df['raw_signal'] == 1].index
        short_idx = df[df['raw_signal'] == -1].index
        
        ax.scatter(long_idx, df.loc[long_idx, 'close'], marker='^', color='red', s=80, label='Long Signal', zorder=5)
        ax.scatter(short_idx, df.loc[short_idx, 'close'], marker='v', color='green', s=80, label='Short Signal', zorder=5)
        
        # 绘制持仓区间背景
        # position: 1 (Long), -1 (Short)
        # 这是一个比较慢的操作，如果有大量点。使用 fill_between 或者 span
        # 这里简化：只画信号点，背景色用 Position
        
        # 辅助函数：绘制背景
        def plot_shade(mask, color, label):
            # 简单实现：找到连续区间
            # 为了性能，这里不逐个画，只画 alpha 覆盖
            ax.fill_between(df.index, df['close'].min(), df['close'].max(), where=mask, color=color, alpha=0.15, label=label)

        plot_shade(df['position'] == 1, 'red', 'Long Position')
        plot_shade(df['position'] == -1, 'green', 'Short Position')

        ax.set_title(title)
        ax.legend()
        ax.grid(True, alpha=0.3)
        
        if save_dir:
            os.makedirs(save_dir, exist_ok=True)
            if fname is None:
                fname = "price_signals.png"
            plt.savefig(os.path.join(save_dir, fname), dpi=200, bbox_inches='tight')
            
        plt.show()


# =========================
# Grid Search 辅助函数
# =========================
def _evaluate_params(params_dict: dict, df_base: pd.DataFrame) -> dict:
    """在静默模式下评估一组参数，返回绩效指标字典。"""
    try:
        strat = VolatilityStrategy(excel_path="", sheet_name="")
        strat.df_5m = df_base.copy()
        p = VolatilityParams(**params_dict)

        # 静默输出
        original_print = builtins.print
        builtins.print = lambda *args, **kwargs: None
        old_stderr = sys.stderr
        sys.stderr = io.StringIO()
        try:
            strat.compute_factors(p)
            df_res = strat.run_strategy(p)
            perf_df = strat.calc_excess_return(
                close=df_res['close'],
                position=df_res['position'],
                weight=df_res['weight']
            )
        finally:
            sys.stderr = old_stderr
            builtins.print = original_print

        total_ret = perf_df['nav_strat'].iloc[-1] - 1
        if len(perf_df) > 0:
            ann_ret   = (1 + total_ret) ** (252 * 54 / len(perf_df)) - 1
            vol       = perf_df['ret_strat'].std() * np.sqrt(252 * 54)
            sharpe    = (ann_ret - 0.02) / vol if vol != 0 else 0.0
        else:
            ann_ret = sharpe = total_ret = 0.0

        return {'sharpe': sharpe, 'ann_ret': ann_ret, 'total_ret': total_ret, **params_dict}
    except Exception:
        return {'sharpe': -999, 'ann_ret': -999, 'total_ret': -999, **params_dict}


def run_grid_search(
    df_base: pd.DataFrame,
    param_grid: Optional[dict] = None,
    save_path: Optional[str] = None,
    n_jobs: int = -1
) -> Tuple[pd.DataFrame, dict]:
    """
    执行网格搜索，返回 (排序后的结果 DataFrame, 最优参数 dict)。
    同时将完整结果保存至 save_path（CSV）。
    """
    if param_grid is None:
        param_grid = {
            'window_days':      [40, 60, 80],
            'vol_smooth_period': [3, 5, 8],
            'q_low_risk':       [0.2, 0.3, 0.4],
            'q_neutral_high':   [0.70, 0.80, 0.90],
            'sig_vol_high':     [0.80, 0.90],
            'sig_speed_high':   [0.80, 0.90],
            'sig_speed_low':    [0.30, 0.40],
            'risk_speed_cap':   [0.80, 0.90],
        }

    grid = list(ParameterGrid(param_grid))
    print(f"Grid search: {len(grid)} 组参数组合，使用 {n_jobs} 个进程...")

    results = Parallel(n_jobs=n_jobs, verbose=5)(
        delayed(_evaluate_params)(p, df_base) for p in grid
    )

    df_res = pd.DataFrame(results)
    df_res = df_res[df_res['sharpe'] != -999].sort_values('sharpe', ascending=False)
    df_res.reset_index(drop=True, inplace=True)

    if save_path:
        df_res.to_csv(save_path, index=False, encoding='utf-8-sig')
        print(f"Grid search 结果已保存至: {save_path}")

    best_params = {k: v for k, v in df_res.iloc[0].items()
                   if k not in ('sharpe', 'ann_ret', 'total_ret')}
    # 确保整数字段还原为 int（ParameterGrid 默认 float/int 混合）
    int_fields = {'window_days', 'bars_per_day', 'vol_smooth_period', 'max_consecutive_losses', 'loss_cooldown_bars'}
    best_params = {k: (int(v) if k in int_fields else v) for k, v in best_params.items()}

    print("\n=== Top 5 参数组合 ===")
    for i in range(min(5, len(df_res))):
        row = df_res.iloc[i]
        print(f"  Rank {i+1}: Sharpe={row['sharpe']:.2f}  AnnRet={row['ann_ret']:.2%}  TotalRet={row['total_ret']:.2%}")

    return df_res, best_params


def main():
    # =========================
    # 配置区
    # =========================
    EXCEL_PATH = r"D:\Python\浙商证券固收\CTA择时 因子复现\Talib Volatility\10年国债期货_5min_波动率指标.xlsx"
    SHEET_NAME = "Sheet1"
    SAVE_DIR = os.path.dirname(os.path.abspath(__file__))
    START_DATE = "2025-01-01"  # 仅用于展示/图表区间截取

    # ---------- 是否运行 Grid Search ----------
    # True  → 先跑网格搜索，用最优参数运行策略
    # False → 直接用下方手动指定的 params
    RUN_GRID_SEARCH = True

    setup_cn_font()

    # 1. 加载数据（grid search 也需要同一份基础数据）
    strategy = VolatilityStrategy(EXCEL_PATH, SHEET_NAME)
    df_base = strategy.load_excel()

    # 2. Grid Search（可选）
    if RUN_GRID_SEARCH:
        grid_save_path = os.path.join(SAVE_DIR, "grid_search_results.csv")
        _, best_params = run_grid_search(
            df_base=df_base,
            param_grid=None,       # None → 使用内置默认网格
            save_path=grid_save_path,
            n_jobs=-1
        )
        print(f"\n最优参数: {best_params}")
        params = VolatilityParams(**best_params)
    else:
        # 手动指定参数
        params = VolatilityParams(
            window_days=40,
            bars_per_day=54,
            vol_smooth_period=3,
            q_low_risk=0.4,
            q_neutral_high=0.9,
            sig_vol_high=0.8,
            sig_speed_high=0.9,
            sig_speed_low=0.4,
            risk_speed_cap=0.9,
            max_consecutive_losses=3
        )

    # 3. 用选定参数计算因子 & 运行策略
    strategy.compute_factors(params)
    df_res = strategy.run_strategy(params)

    # 4. 输出每日多空信号 CSV
    # raw_signal 列：做多 +1，做空 -1，空仓 0
    # position  列：当前实际持仓状态（含风控过滤后）
    signal_cols = [
        'datetime', 'close',
        'vol_level', 'vol_level_smooth', 'vol_trend', 'vol_speed',
        'raw_signal', 'position', 'weight'
    ]
    signal_cols_exist = [c for c in signal_cols if c in df_res.columns]
    df_signals = df_res[signal_cols_exist].copy()
    df_signals['signal_label'] = df_signals['raw_signal'].map(
        {1: 'Long', -1: 'Short', 0: 'Flat'}
    ).fillna('Flat')

    signal_save_path = os.path.join(SAVE_DIR, "daily_signals.csv")
    df_signals.to_csv(signal_save_path, index=False, encoding='utf-8-sig')
    print(f"每日信号已保存至: {signal_save_path}")

    # 5. 截取展示区间（图表）
    if START_DATE:
        df_plot = df_res.loc[
            df_res['datetime'] >= pd.to_datetime(START_DATE)
        ].copy()
        df_plot.set_index('datetime', inplace=True)
    else:
        df_plot = df_res.set_index('datetime').copy()

    # 6. 可视化分析
    print("Plotting results...")

    strategy.plot_vol_analysis(
        df_plot,
        title="Volatility Factor Analysis",
        save_dir=SAVE_DIR,
        fname="vol_analysis.png"
    )

    strategy.plot_price_with_signals(
        df_plot,
        title="Price, Signals & Positions",
        save_dir=SAVE_DIR,
        fname="signals_positions.png"
    )

    # 7. 绩效计算 & 净值图
    perf_df = strategy.calc_excess_return(
        close=df_plot['close'],
        position=df_plot['position'],
        weight=df_plot['weight']
    )

    strategy.plot_nav_compare(
        perf_df,
        title="Strategy NAV vs Benchmark",
        save_dir=SAVE_DIR,
        fname="nav_performance.png"
    )

    # 8. 打印统计指标
    total_ret = perf_df['nav_strat'].iloc[-1] - 1
    if len(perf_df) > 0:
        ann_ret = (1 + total_ret) ** (252 * 54 / len(perf_df)) - 1
        vol = perf_df['ret_strat'].std() * np.sqrt(252 * 54)
        sharpe = (ann_ret - 0.02) / vol if vol != 0 else 0
    else:
        ann_ret = sharpe = 0

    print(f"\nPerformance Summary ({START_DATE} to End):")
    print(f"  Total Return   : {total_ret:.2%}")
    print(f"  Annualized Ret : {ann_ret:.2%}")
    print(f"  Sharpe Ratio   : {sharpe:.2f}")


if __name__ == "__main__":
    main()

