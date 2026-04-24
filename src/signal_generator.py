import pandas as pd
import numpy as np
from tqdm import tqdm

class SignalGenerator:
    @staticmethod
    def generate_signals(df: pd.DataFrame, params: dict) -> pd.DataFrame:
        """
        根据波动率分位数生成初始信号
        """
        df = df.copy()
        
        # 初始信号：基于分位数的做多、做空、平仓
        # 这里的 q_low_risk, q_sig_vol_high 等已在 compute_rolling_quantiles 中计算
        
        # 做空逻辑：vol_level_smooth > q_sig_vol_high & vol_speed > speed_q_high & vol_trend > 0 (连续2期)
        short_cond = (
            (df['vol_level_smooth'] > df['q_sig_vol_high']) &
            (df['vol_speed'] > df['speed_q_high']) &
            (df['vol_trend'] > 0) &
            (df['vol_trend'].shift(1) > 0)
        )
        
        # 做多逻辑：vol_level_smooth < q_low_risk & vol_speed < speed_q_low & vol_trend < 0 (连续2期)
        long_cond = (
            (df['vol_level_smooth'] < df['q_low_risk']) &
            (df['vol_speed'] < df['speed_q_low']) &
            (df['vol_trend'] < 0) &
            (df['vol_trend'].shift(1) < 0)
        )
        
        df['raw_signal'] = 0
        df.loc[short_cond, 'raw_signal'] = -1
        df.loc[long_cond, 'raw_signal'] = 1
        
        # 市场状态划分与仓位限制
        conditions = [
            (df['vol_level_smooth'] < df['q_low_risk']),
            (df['vol_level_smooth'] >= df['q_low_risk']) & (df['vol_level_smooth'] <= df['q_neutral_high']),
            (df['vol_level_smooth'] > df['q_neutral_high'])
        ]
        choices = [1.2, 0.5, 1.0] # 仓位系数
        df['pos_limit'] = np.select(conditions, choices, default=0.0)
        
        return df

    @staticmethod
    def run_path_dependent_risk_control(df: pd.DataFrame, params: dict) -> pd.DataFrame:
        """
        执行带有持仓依赖的风控与仓位模拟
        """
        df = df.copy()
        n = len(df)
        closes = df['close'].values
        vol_levels = df['vol_level_smooth'].values
        vol_speeds = df['vol_speed'].values
        raw_signals = df['raw_signal'].values
        pos_limits = df['pos_limit'].values
        
        # 关键分位数
        q50s = df['q50'].values
        speed_q_risks = df['speed_q_risk'].values
        
        position = 0
        entry_price = 0.0
        consecutive_losses = 0
        loss_cooldown_counter = 0
        
        max_losses = params.get('max_consecutive_losses', 3)
        cooldown_bars = params.get('loss_cooldown_bars', 108)
        
        positions = np.zeros(n)
        weights = np.zeros(n)
        
        for i in range(1, n):
            # 冷却期处理
            if loss_cooldown_counter > 0:
                loss_cooldown_counter -= 1
            
            # --- 持仓风控检查 ---
            if position == 1: # 多头
                # 多头止损: vol_speed > 90%分位
                if vol_speeds[i] > speed_q_risks[i]:
                    if (closes[i] - entry_price) < 0:
                        consecutive_losses += 1
                    else:
                        consecutive_losses = 0
                    position = 0
                    entry_price = 0
            
            elif position == -1: # 空头
                # 空头止盈: vol_level_smooth < 50%分位 (q50)
                if vol_levels[i] < q50s[i]:
                    if (entry_price - closes[i]) < 0:
                        consecutive_losses += 1
                    else:
                        consecutive_losses = 0
                    position = 0
                    entry_price = 0
                    
            # --- 信号执行 (若无持仓或信号翻转) ---
            # 原逻辑：若有信号且不在冷却期，则执行
            curr_signal = raw_signals[i]
            if curr_signal != 0:
                if consecutive_losses >= max_losses:
                    consecutive_losses = 0
                    loss_cooldown_counter = cooldown_bars
                elif loss_cooldown_counter > 0:
                    pass
                else:
                    # 更新持仓
                    if curr_signal == 1:
                        position = 1
                        entry_price = closes[i]
                    elif curr_signal == -1:
                        position = -1
                        entry_price = closes[i]
                        
            positions[i] = position
            weights[i] = position * pos_limits[i]
            
        df['position'] = positions
        df['weight'] = weights
        return df
