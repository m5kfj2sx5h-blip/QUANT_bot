import time
import logging
from collections import deque
logger = logging.getLogger(__name__)

class HealthMonitor:
    def __init__(self, window_size=20):
        self.cycle_times = deque(maxlen=window_size)
        self.api_errors = deque(maxlen=50)
        self.fill_rates = deque(maxlen=30)
        self.mode = "HIGH_LATENCY"
    def adjust_cycle_time(self, last_cycle_time, current_mode):
        self.cycle_times.append(last_cycle_time)
        self.mode = current_mode
        avg_time = sum(self.cycle_times) / len(self.cycle_times) if self.cycle_times else last_cycle_time
        if self.mode == "LOW_LATENCY":
            base_sleep = max(0.5, 2.0 - avg_time)
        else:
            base_sleep = max(5.0, 30.0 - avg_time)
        return base_sleep
    def log_api_error(self, exchange_name):
        self.api_errors.append((time.time(), exchange_name))
        error_rate = len([e for e in self.api_errors if time.time() - e[0] < 300]) / 5.0
        if error_rate > 0.5:
            logger.warning(f"⚠️  High API error rate detected: {error_rate:.1f}/min")