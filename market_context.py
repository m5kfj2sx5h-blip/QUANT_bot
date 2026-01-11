import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional, List, Tuple

class MarketPhase(Enum):
    ACCUMULATION = "accumulation"
    MARKUP = "markup"
    DISTRIBUTION = "distribution" 
    MARKDOWN = "markdown"
    UNKNOWN = "unknown"

class AuctionState(Enum):
    ACCEPTING = "price_acceptance"
    REJECTING = "price_rejection"
    BALANCED = "balanced"
    IMBALANCED_BUYING = "imbalance_buying"
    IMBALANCED_SELLING = "imbalance_selling"

class MacroSignal(Enum):
    BTC = "btc"
    GOLD = "gold"
    NEUTRAL = "neutral"

@dataclass
class MarketContext:
    timestamp: float = field(default_factory=time.time)
    primary_symbol: str = "BTCUSDT"
    
    # Auction Context
    auction_state: AuctionState = AuctionState.BALANCED
    auction_imbalance_score: float = 0.0
    key_resistance: Optional[float] = None
    key_support: Optional[float] = None
    
    # Volume DNA
    cumulative_delta: int = 0
    volume_poc: Optional[float] = None
    volume_strength: float = 0.0
    
    # Cycle & Phase
    market_phase: MarketPhase = MarketPhase.UNKNOWN
    cycle_bias: float = 0.0
    
    # Psychology
    market_sentiment: float = 0.0
    crowd_behavior: str = "neutral"
    
    # Execution
    execution_confidence: float = 0.0
    macro_signal: MacroSignal = MacroSignal.NEUTRAL
    
    # Portfolio State
    portfolio_value: float = 0.0
    btc_allocation: float = 0.0
    gold_allocation: float = 0.0
    usd_allocation: float = 0.0
    
    def to_dict(self) -> Dict:
        return {
            "timestamp": self.timestamp,
            "symbol": self.primary_symbol,
            "auction": self.auction_state.value,
            "auction_score": round(self.auction_imbalance_score, 3),
            "phase": self.market_phase.value,
            "sentiment": round(self.market_sentiment, 3),
            "confidence": round(self.execution_confidence, 1),
            "crowd": self.crowd_behavior,
            "macro": self.macro_signal.value,
            "btc_alloc": round(self.btc_allocation, 3),
            "gold_alloc": round(self.gold_allocation, 3)
        }