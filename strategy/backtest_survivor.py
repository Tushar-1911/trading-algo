import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class SurvivorBacktester:
    def __init__(self, initial_capital=1000000, lot_size=75):
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.lot_size = lot_size

        # Strategy Parameters
        self.pe_gap = 50
        self.ce_gap = 50
        self.pe_reset_gap = 50
        self.ce_reset_gap = 50
        self.pe_quantity = 75
        self.ce_quantity = 75
        self.pe_symbol_gap = 200
        self.ce_symbol_gap = 200
        self.sl_pct = 50
        self.tp_pct = 80
        self.max_pe_positions = 10
        self.max_ce_positions = 10

        # State
        self.nifty_pe_last_value = 0
        self.nifty_ce_last_value = 0
        self.pe_reset_gap_flag = False
        self.ce_reset_gap_flag = False

        self.open_positions = [] # List of dicts
        self.trades_history = []

    def download_data(self, period="1y", interval="1d"):
        logger.info(f"Downloading NIFTY 50 data (Period: {period}, Interval: {interval})")
        df = yf.download("^NSEI", period=period, interval=interval)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df

    def run(self, df):
        logger.info("Starting backtest...")

        # Initialize references with first close
        first_price = df.iloc[0]['Close']
        self.nifty_pe_last_value = first_price
        self.nifty_ce_last_value = first_price

        for date, row in df.iterrows():
            current_price = row['Close']

            # 1. Manage Existing Positions
            self._manage_positions(current_price, date)

            # 2. Reset Logic
            self._reset_reference_values(current_price)

            # 3. Handle Trades
            self._handle_pe_trade(current_price, date)
            self._handle_ce_trade(current_price, date)

        return self._get_results()

    def _manage_positions(self, current_index_price, current_date):
        remaining_positions = []
        for pos in self.open_positions:
            entry_index_price = pos['entry_index_price']
            strike = pos['strike']
            option_type = pos['type']
            entry_premium = pos['entry_premium']

            # Intrinsic
            intrinsic = 0
            if option_type == "PE":
                intrinsic = max(0, strike - current_index_price)
            else:
                intrinsic = max(0, current_index_price - strike)

            # Extrinsic (decaying)
            days_held = (current_date - pos['entry_date']).days
            extrinsic = max(0, entry_premium * (1 - days_held/5))

            # Realistically limit the premium in backtest
            current_premium = intrinsic + extrinsic
            pos['current_premium'] = current_premium

            profit_pct = (entry_premium - current_premium) / entry_premium * 100

            if profit_pct >= self.tp_pct:
                self._close_position(pos, current_premium, current_date, "Take Profit")
            elif profit_pct <= -self.sl_pct:
                # Capping Stop Loss at 100% loss of premium to simulate 2x premium exit
                exit_price = min(current_premium, entry_premium * 2)
                self._close_position(pos, exit_price, current_date, "Stop Loss")
            elif days_held >= 5:
                self._close_position(pos, current_premium, current_date, "Time Exit")
            else:
                remaining_positions.append(pos)

        self.open_positions = remaining_positions

    def _handle_pe_trade(self, current_price, date):
        if current_price <= self.nifty_pe_last_value:
            return

        price_diff = current_price - self.nifty_pe_last_value
        if price_diff > self.pe_gap:
            if self._count_open("PE") >= self.max_pe_positions:
                return

            multiplier = int(price_diff / self.pe_gap)
            self.nifty_pe_last_value += self.pe_gap * multiplier

            strike = current_price - self.pe_symbol_gap
            entry_premium = 40

            pos = {
                'type': 'PE',
                'entry_date': date,
                'entry_index_price': current_price,
                'strike': strike,
                'entry_premium': entry_premium,
                'quantity': self.pe_quantity * multiplier,
                'side': 'SELL'
            }
            self.open_positions.append(pos)
            self.pe_reset_gap_flag = True

    def _handle_ce_trade(self, current_price, date):
        if current_price >= self.nifty_ce_last_value:
            return

        price_diff = self.nifty_ce_last_value - current_price
        if price_diff > self.ce_gap:
            if self._count_open("CE") >= self.max_ce_positions:
                return

            multiplier = int(price_diff / self.ce_gap)
            self.nifty_ce_last_value -= self.ce_gap * multiplier

            strike = current_price + self.ce_symbol_gap
            entry_premium = 40

            pos = {
                'type': 'CE',
                'entry_date': date,
                'entry_index_price': current_price,
                'strike': strike,
                'entry_premium': entry_premium,
                'quantity': self.ce_quantity * multiplier,
                'side': 'SELL'
            }
            self.open_positions.append(pos)
            self.ce_reset_gap_flag = True

    def _reset_reference_values(self, current_price):
        if (self.nifty_pe_last_value - current_price) > self.pe_reset_gap and self.pe_reset_gap_flag:
            self.nifty_pe_last_value = current_price + self.pe_reset_gap

        if (current_price - self.nifty_ce_last_value) > self.ce_reset_gap and self.ce_reset_gap_flag:
            self.nifty_ce_last_value = current_price - self.ce_reset_gap

    def _close_position(self, pos, exit_premium, exit_date, reason):
        pnl = (pos['entry_premium'] - exit_premium) * pos['quantity']
        self.capital += pnl

        trade = {
            'entry_date': pos['entry_date'],
            'exit_date': exit_date,
            'type': pos['type'],
            'pnl': pnl,
            'pnl_pct': (pos['entry_premium'] - exit_premium) / pos['entry_premium'] * 100,
            'reason': reason
        }
        self.trades_history.append(trade)

    def _count_open(self, opt_type):
        return sum(1 for p in self.open_positions if p['type'] == opt_type)

    def _get_results(self):
        if not self.trades_history:
            return {"Error": "No trades executed."}

        df_trades = pd.DataFrame(self.trades_history)
        total_pnl = df_trades['pnl'].sum()
        win_rate = (df_trades['pnl'] > 0).mean() * 100
        max_drawdown = self._calculate_max_drawdown()

        df_trades['month'] = df_trades['exit_date'].dt.to_period('M')
        monthly_pnl = df_trades.groupby('month')['pnl'].sum()

        return {
            'Initial Capital': self.initial_capital,
            'Final Capital': self.capital,
            'Total P&L': total_pnl,
            'ROI (%)': (total_pnl / self.initial_capital) * 100,
            'Win Rate (%)': win_rate,
            'Total Trades': len(df_trades),
            'Max Drawdown (%)': max_drawdown,
            'Profit Factor': abs(df_trades[df_trades['pnl'] > 0]['pnl'].sum() / df_trades[df_trades['pnl'] < 0]['pnl'].sum()) if any(df_trades['pnl'] < 0) else float('inf'),
            'Monthly P&L': monthly_pnl
        }

    def _calculate_max_drawdown(self):
        df_trades = pd.DataFrame(self.trades_history)
        if df_trades.empty: return 0
        cum_pnl = df_trades['pnl'].cumsum() + self.initial_capital
        peak = cum_pnl.expanding(min_periods=1).max()
        drawdown = (cum_pnl - peak) / peak * 100
        return abs(drawdown.min())

if __name__ == "__main__":
    backtester = SurvivorBacktester()
    data = backtester.download_data(period="1y", interval="1d")
    if not data.empty:
        results = backtester.run(data)
        print("\n" + "="*40)
        print("SURVIVOR STRATEGY BACKTEST RESULTS")
        print("="*40)
        for k, v in results.items():
            if k == 'Monthly P&L': continue
            if isinstance(v, float):
                print(f"{k:25}: {v:.2f}")
            else:
                print(f"{k:25}: {v}")
        print("-" * 40)
        print("Monthly P&L:")
        print(results['Monthly P&L'])
        print("="*40)
