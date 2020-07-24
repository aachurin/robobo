import logging
import logging.config
from time import time


class Bucket:
    def __init__(self, burst):
        self.burst = burst
        self.allowance = burst
        self.last_check = 0

    def consume(self, rate):
        now = time()
        delta = now - self.last_check
        self.last_check = now
        self.allowance = min(self.allowance + delta * rate, self.burst)
        if self.allowance < 1:
            return False
        self.allowance -= 1
        return True


class RateLimitingFilter(logging.Filter):
    def __init__(self, burst=1):
        super().__init__()
        self.burst = burst
        self.buckets = {}

    def filter(self, record):
        rate = getattr(record, "rate", None)
        if rate is not None:
            key = record.filename, record.lineno
            if key in self.buckets:
                bucket = self.buckets[key]
            else:
                self.buckets[key] = bucket = Bucket(self.burst)
            return bucket.consume(rate)
        return True


def setup_logging(handler="logging.StreamHandler", params=None, format=None):
    format = format or "%(asctime)s [%(name)s] %(message)s"
    params = params or {}
    handler = {
        "level": "INFO",
        "formatter": "default",
        "class": handler,
        "filters": ["rate_limit"]
    }
    handler.update(params)
    logging.config.dictConfig({
        "version": 1,
        "disable_existing_loggers": True,
        "filters": {
            "rate_limit": {
                '()': RateLimitingFilter
            },
        },
        "formatters": {
            "default": {
                "format": format
            }
        },
        "handlers": {
            "default": handler
        },
        "root": {
            "handlers": ["default"],
            "level": "INFO",
            "propagate": False
        },
        "loggers": {
            "console": {
                "handlers": ["default"],
                "level": "INFO",
                "propagate": False
            }
        }
    })
