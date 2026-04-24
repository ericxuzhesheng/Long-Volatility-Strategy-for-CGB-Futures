import pandas as pd
import numpy as np
import talib
from typing import Tuple

class VolatilityCalculator:
    @staticmethod
    def compute_indicators(df: pd.DataFrame, vol_smooth_period: int = 5) -> pd.DataFrame:
        """
        计算波动率指标：NATR, TRANGE, ATR, MA
        """
        df = df.copy()
        
        # 使用 TA-Lib 计算基础波动率指标
        # NATR_14
        df['vol_level'] = talib.NATR(df['high'], df['low'], df['close'], timeperiod=14)
        # TRANGE
        df['TRANGE'] = talib.TRANGE(df['high'], df['low'], df['close'])
        # ATR_14
        df['ATR_14'] = talib.ATR(df['high'], df['low'], df['close'], timeperiod=14)
        
        # 波动率平滑
        df['vol_level_smooth'] = talib.SMA(df['vol_level'].values, timeperiod=vol_smooth_period)
        df['vol_level_smooth'] = df['vol_level_smooth'].fillna(df['vol_level'])
        
        # 趋势与速度
        df['vol_trend'] = df['vol_level_smooth'].diff()
        df['vol_speed'] = df['vol_trend'].diff()
        
        # 补充：计算 MA 均线用于趋势过滤
        df['ma_short'] = talib.SMA(df['close'], timeperiod=20)
        df['ma_long'] = talib.SMA(df['close'], timeperiod=60)
        
        return df

    @staticmethod
    def compute_rolling_quantiles(df: pd.DataFrame, window: int, params: dict) -> pd.DataFrame:
        """
        计算滚动分位数阈值
        """
        df = df.copy()
        min_periods = window // 2
        
        # 波动率水平分位数
        vol_roller = df['vol_level_smooth'].rolling(window=window, min_periods=min_periods)
        df['q_low_risk'] = vol_roller.quantile(params.get('q_low_risk', 0.30))
        df['q_neutral_high'] = vol_roller.quantile(params.get('q_neutral_high', 0.80))
        df['q_sig_vol_high'] = vol_roller.quantile(params.get('sig_vol_high', 0.90))
        df['q_exit_low'] = vol_roller.quantile(params.get('risk_vol_exit', 0.30))
        df['q50'] = vol_roller.quantile(0.50)
        
        # 波动率速度分位数
        speed_roller = df['vol_speed'].rolling(window=window, min_periods=min_periods)
        df['speed_q_low'] = speed_roller.quantile(params.get('sig_speed_low', 0.40))
        df['speed_q_high'] = speed_roller.quantile(params.get('sig_speed_high', 0.90))
        df['speed_q_risk'] = speed_roller.quantile(params.get('risk_speed_cap', 0.90))
        
        return df
