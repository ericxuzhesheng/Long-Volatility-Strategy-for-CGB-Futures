import matplotlib.pyplot as plt
import os
import pandas as pd
from src.utils import ensure_dir

class Visualizer:
    def __init__(self, save_dir: str):
        self.save_dir = save_dir
        ensure_dir(save_dir)

    def plot_vol_analysis(self, df: pd.DataFrame, title: str, fname: str):
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(16, 10), sharex=True)
        
        ax1.plot(df['datetime'], df['close'], label='Close Price')
        ax1.set_title(f"{title} - Price")
        ax1.legend()
        ax1.grid(True, alpha=0.3)
        
        ax2.plot(df['datetime'], df['vol_level_smooth'], label='Vol Level Smooth', color='blue')
        ax2.plot(df['datetime'], df['q_low_risk'], '--', label='Low Risk Q', color='green', alpha=0.7)
        ax2.plot(df['datetime'], df['q_neutral_high'], '--', label='Neutral High Q', color='orange', alpha=0.7)
        ax2.plot(df['datetime'], df['q_sig_vol_high'], '--', label='Sig Vol High Q', color='red', alpha=0.7)
        
        ax2.fill_between(df['datetime'], df['q_low_risk'], df['q_neutral_high'], color='gray', alpha=0.1, label='Neutral Zone')
        ax2.set_title(f"{title} - Volatility Analysis")
        ax2.legend(loc='upper left')
        ax2.grid(True, alpha=0.3)
        
        plt.tight_layout()
        plt.savefig(os.path.join(self.save_dir, fname), dpi=200, bbox_inches='tight')
        plt.close()

    def plot_nav_comparison(self, perf_df: pd.DataFrame, title: str, fname: str):
        fig, ax = plt.subplots(figsize=(16, 6))
        ax.plot(perf_df['datetime'], perf_df["nav_strat"], label="Strategy NAV", linewidth=1.6, color='red')
        ax.plot(perf_df['datetime'], perf_df["nav_bh"], label="Benchmark NAV", linewidth=1.6, color='gray', alpha=0.7)
        ax.plot(perf_df['datetime'], perf_df["nav_excess"], label="Excess NAV", linewidth=1.6, color='blue', linestyle='--')

        ax.set_title(title)
        ax.grid(True, alpha=0.25)
        ax.legend(loc="upper left")
        
        plt.tight_layout()
        plt.savefig(os.path.join(self.save_dir, fname), dpi=200, bbox_inches='tight')
        plt.close()

    def plot_drawdown(self, perf_df: pd.DataFrame, title: str, fname: str):
        fig, ax = plt.subplots(figsize=(16, 5))
        nav = perf_df['nav_strat']
        dd = (nav.cummax() - nav) / nav.cummax()
        ax.fill_between(perf_df['datetime'], 0, -dd, color='red', alpha=0.3)
        ax.set_title(title)
        ax.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.savefig(os.path.join(self.save_dir, fname), dpi=200, bbox_inches='tight')
        plt.close()

    def plot_position(self, df: pd.DataFrame, title: str, fname: str):
        fig, ax = plt.subplots(figsize=(16, 5))
        ax.plot(df['datetime'], df['close'], color='black', alpha=0.3, label='Close')
        ax.fill_between(df['datetime'], df['close'].min(), df['close'].max(), where=df['position'] == 1, color='red', alpha=0.2, label='Long')
        ax.fill_between(df['datetime'], df['close'].min(), df['close'].max(), where=df['position'] == -1, color='green', alpha=0.2, label='Short')
        ax.set_title(title)
        ax.legend()
        ax.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.savefig(os.path.join(self.save_dir, fname), dpi=200, bbox_inches='tight')
        plt.close()
