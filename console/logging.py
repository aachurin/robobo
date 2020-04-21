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


def setup_logging():
    logging.config.dictConfig({
        "version": 1,
        "disable_existing_loggers": True,
        "filters": {
            "rate_limit": {
                '()': RateLimitingFilter
            },
        },
        "formatters": {
            "standard": {
                "format": "%(asctime)s [%(name)s] %(message)s"
            }
        },
        "handlers": {
            "console": {
                "level": "INFO",
                "formatter": "standard",
                "class": "logging.StreamHandler",
                "filters": ["rate_limit"]
            },
        },
        "root": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False
        },
        "loggers": {
            "console": {
                "handlers": ["console"],
                "level": "INFO",
                "propagate": False
            }
        }
    })
