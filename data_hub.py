import asyncio
import logging
from typing import Dict, Any, Callable, List
from exchanges_websocket import BinanceUSWebSocket, KrakenWebSocket, CoinbaseWebSocket

class DataHub:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.connections = {}
        self.data_callbacks = []
    
    async def connect_all_exchanges(self):
        """Connect to all three US exchanges simultaneously"""
        self.logger.info("🔄 Connecting to all exchanges...")
        
        # Create instances for US exchanges
        binance_ws = BinanceUSWebSocket("btcusdt")
        kraken_ws = KrakenWebSocket("XBT/USD")
        coinbase_ws = CoinbaseWebSocket("BTC-USD")
        
        # Connect to all in parallel
        await asyncio.gather(
            self._safe_add_exchange("binance_us", binance_ws),
            self._safe_add_exchange("kraken", kraken_ws),
            self._safe_add_exchange("coinbase", coinbase_ws)
        )
        
        self.logger.info("✅ All exchange connections established")
    
    async def _safe_add_exchange(self, name: str, ws_instance):
        """Safely add an exchange with error handling"""
        try:
            await ws_instance.connect()
            self.connections[name] = ws_instance
            ws_instance.subscribe(self._process_incoming_data)
            self.logger.info(f"✅ {name} added to DataHub")
        except Exception as e:
            self.logger.error(f"❌ Failed to add {name}: {e}")
    
    def subscribe(self, callback: Callable):
        self.data_callbacks.append(callback)
    
    async def _process_incoming_data(self, data: Dict):
        """Process data from any exchange"""
        for callback in self.data_callbacks:
            try:
                await callback(data)
            except Exception as e:
                self.logger.error(f"Data callback error: {e}")
    
    async def start(self):
        self.logger.info("🚀 DataHub starting with 3 US exchanges...")
        await self.connect_all_exchanges()
    
    async def stop(self):
        self.logger.info("🛑 DataHub stopping...")
        # Cleanup logic here