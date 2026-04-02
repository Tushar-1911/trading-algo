import os
import sys
import pandas as pd
from typing import Dict, Any, Optional, List, Tuple
from dotenv import load_dotenv
from dhanhq import dhanhq, marketfeed
from brokers.base import BrokerBase
from logger import logger
import threading
import time

load_dotenv()

class DhanBroker(BrokerBase):
    def __init__(self):
        super().__init__()
        self.client_id = os.getenv('BROKER_ID')
        self.access_token = os.getenv('BROKER_API_KEY') # For Dhan, API key is often the access token

        if not self.client_id or not self.access_token:
            raise Exception("Missing Dhan BROKER_ID or BROKER_API_KEY (access token) in environment variables.")

        self.dhan = dhanhq(self.client_id, self.access_token)
        self.authenticated = True
        self.feed = None
        self.instruments_df = pd.DataFrame()
        self.on_ticks = None
        self.on_connect = None

    def authenticate(self) -> Optional[str]:
        # Dhan uses a permanent access token, so we just verify it
        profile = self.dhan.get_fund_limits()
        if profile.get('status') == 'success':
            logger.info("Dhan authenticated successfully")
            return self.access_token
        else:
            logger.error(f"Dhan authentication failed: {profile}")
            return None

    def get_quote(self, symbol: str) -> Dict[str, Any]:
        """
        Dhan quote_data expects a dict of {exchange: [symbols]} or {exchange: [security_ids]}
        """
        # Handle exchange prefix (e.g., 'NFO:NIFTY25JAN24300PE')
        clean_symbol = symbol.split(':')[-1] if ':' in symbol else symbol

        # We need to map symbol string to security_id and exchange_segment
        # For simplicity, let's assume we have instruments_df loaded
        if self.instruments_df.empty:
            self.download_instruments()

        row = self.instruments_df[self.instruments_df['tradingsymbol'] == clean_symbol]
        if row.empty:
            logger.error(f"Symbol {clean_symbol} not found in Dhan instruments")
            return {}

        security_id = str(row.iloc[0]['SEM_SMST_SECURITY_ID'])
        exchange_segment = row.iloc[0]['SEM_EXCH_ID'] # Map this to Dhan segment

        # Dhan API quote_data
        data = {
            exchange_segment: [security_id]
        }
        resp = self.dhan.quote_data(data)
        if resp.get('status') == 'success':
            # Format to match the expected output format in survivor.py
            # survivor.py expects {symbol: {'last_price': value, ...}}
            quote = resp['data'][security_id]
            return {
                symbol: {
                    'last_price': quote['lastPrice'],
                    'instrument_token': security_id,
                    # add other fields if necessary
                }
            }
        return {}

    def place_order(self, symbol, quantity, price, transaction_type, order_type, variety, exchange, product, tag="Unknown"):
        # Handle exchange prefix
        clean_symbol = symbol.split(':')[-1] if ':' in symbol else symbol

        if self.instruments_df.empty:
            self.download_instruments()

        row = self.instruments_df[self.instruments_df['tradingsymbol'] == clean_symbol]
        if row.empty:
            logger.error(f"Symbol {clean_symbol} not found in Dhan instruments")
            return -1

        security_id = str(row.iloc[0]['SEM_SMST_SECURITY_ID'])

        # Map parameters to Dhan constants
        dhan_transaction_type = self.dhan.BUY if transaction_type == "BUY" else self.dhan.SELL
        dhan_order_type = self.dhan.MARKET if order_type == "MARKET" else self.dhan.LIMIT

        # Dhan exchange segments mapping might be needed
        # exchange in survivor.py is 'NFO'
        dhan_segment = self.dhan.NSE_FNO if exchange == 'NFO' else self.dhan.NSE

        # product mapping
        # survivor.py uses 'NRML'
        dhan_product = self.dhan.CNC # Default
        if product == 'NRML':
            dhan_product = self.dhan.MARGIN
        elif product == 'MIS':
            dhan_product = self.dhan.INTRA

        resp = self.dhan.place_order(
            security_id=security_id,
            exchange_segment=dhan_segment,
            transaction_type=dhan_transaction_type,
            quantity=quantity,
            order_type=dhan_order_type,
            product_type=dhan_product,
            price=price if price else 0,
            tag=tag
        )

        if resp.get('status') == 'success':
            order_id = resp['data']['orderId']
            logger.info(f"Dhan Order placed: {order_id}")
            return order_id
        else:
            logger.error(f"Dhan Order placement failed: {resp}")
            return -1

    def download_instruments(self):
        # Dhan provides CSV URLs for security lists
        # We'll use FNO list for NIFTY options
        fno_url = "https://images.dhan.co/api-data/api-scrip-master-csv/NSE_FNO.csv"
        try:
            df = pd.read_csv(fno_url)
            # Map column names for compatibility with survivor.py
            df['tradingsymbol'] = df['SEM_TRADING_SYMBOL']
            df['strike'] = df['SEM_STRIKE_PRICE']
            df['instrument_type'] = df['SEM_OPTION_TYPE']
            df['segment'] = "NFO-OPT" # For survivor.py logic
            self.instruments_df = df
            logger.info(f"Downloaded {len(self.instruments_df)} Dhan FNO instruments")
        except Exception as e:
            logger.error(f"Failed to download Dhan instruments: {e}")

    def connect_websocket(self, instruments_to_subscribe: List[Tuple[int, str]]):
        """
        instruments_to_subscribe: List of (exchange_segment, security_id)
        """
        # DhanFeed expects:
        # instruments = [(segment, security_id), (segment, security_id)]

        self.feed = marketfeed.DhanFeed(
            self.client_id,
            self.access_token,
            instruments_to_subscribe,
            version='v2'
        )

        # We define on_message outside to avoid potential scope issues
        def on_message(message):
            if self.on_ticks:
                # Map Dhan message to survivor.py expected format
                # survivor.py expects a list of dicts with last_price
                tick = {
                    'last_price': message.get('LTP'),
                    'instrument_token': message.get('security_id'),
                    'tradingsymbol': message.get('symbol') # If symbol is in message
                }
                # Check for alternative keys if LTP/security_id not present
                if not tick['last_price'] and 'last_price' in message:
                    tick['last_price'] = message['last_price']

                self.on_ticks(None, [tick])

        # For DhanHQ SDK version 2, we use on_message or specific process methods
        # Most SDKs expect to override these methods
        self.feed.on_ticks = on_message

        # Start in thread
        t = threading.Thread(target=self.feed.run_forever)
        t.daemon = True
        t.start()

        if self.on_connect:
            self.on_connect(None, "Connected")

    def subscribe(self, symbols: List[Any]):
        """
        Subscribe to market data for the given symbols.
        Expects a list of symbols (strings) or security_ids (ints)
        """
        if not self.feed:
            logger.warning("Market feed not initialized. Cannot subscribe.")
            return

        instruments_to_add = []
        for sym in symbols:
            if isinstance(sym, str):
                # Handle exchange prefix
                clean_sym = sym.split(':')[-1] if ':' in sym else sym
                if self.instruments_df.empty:
                    self.download_instruments()

                row = self.instruments_df[self.instruments_df['tradingsymbol'] == clean_sym]
                if not row.empty:
                    security_id = int(row.iloc[0]['SEM_SMST_SECURITY_ID'])
                    exchange_segment = int(row.iloc[0]['SEM_EXCH_ID'])
                    instruments_to_add.append((exchange_segment, security_id))
            elif isinstance(sym, (int, float)):
                # Default segment to NSE_FNO for integers? (risky, but often used for security_ids)
                # Ideally, the caller should provide the segment.
                # Assuming F&O segment (NSE_FNO = 1)
                instruments_to_add.append((self.dhan.NSE_FNO, int(sym)))

        if instruments_to_add:
            try:
                # We'll use the documented subscribe_instruments from our dir() check earlier
                self.feed.subscribe_instruments(instruments_to_add)
                logger.info(f"Dhan subscribed to: {instruments_to_add}")
            except Exception as e:
                logger.error(f"Failed to subscribe on Dhan: {e}")
