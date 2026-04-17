"""
Prometheus metrics exporter for TemporalEngine Python services.

Reads counters written to Redis by the Flink processor and ring_hunter,
then exposes them as Prometheus gauges/counters on port 8000.

Prometheus scrapes this on the 'temporal_engine' job (prometheus.yml).

Run standalone:  python metrics_server.py
Docker service:  see docker-compose.yml → metrics_server
"""

import os
import time
import redis
from prometheus_client import start_http_server, Gauge, Info

REDIS_HOST   = os.getenv("REDIS_HOST",   "redis")
REDIS_PORT   = int(os.getenv("REDIS_PORT", "6379"))
METRICS_PORT = int(os.getenv("METRICS_PORT", "8000"))
SCRAPE_INTERVAL = int(os.getenv("SCRAPE_INTERVAL", "10"))  # seconds

# ---------------------------------------------------------------------------
# Metric definitions
# ---------------------------------------------------------------------------

EVENTS_PROCESSED = Gauge(
    "temporal_engine_events_processed_total",
    "Total enriched transaction events processed by the Flink pipeline",
)
VELOCITY_HIGH = Gauge(
    "temporal_engine_velocity_high_total",
    "Total events where velocity_flag=HIGH (potential burst fraud)",
)
VIOLATIONS = Gauge(
    "temporal_engine_governance_violations_total",
    "Total data governance contract violations detected",
)
PII_MASKS = Gauge(
    "temporal_engine_pii_masks_total",
    "Total PII fields masked by the Presidio shield",
)
FRAUD_RINGS = Gauge(
    "temporal_engine_fraud_rings_detected_total",
    "Total fraud rings identified by the RingHunter WCC scan",
)
AGENT_INVESTIGATIONS = Gauge(
    "temporal_engine_agent_investigations_total",
    "Total autonomous agent investigations triggered by RingHunter",
)
DLQ_EVENTS = Gauge(
    "temporal_engine_dlq_events_total",
    "Total malformed events routed to the Dead Letter Queue",
)
ACTIVE_USERS = Gauge(
    "temporal_engine_active_users",
    "Number of distinct users with live features in Redis",
)

BUILD_INFO = Info(
    "temporal_engine_build",
    "TemporalEngine service metadata",
)
BUILD_INFO.info({"version": "1.0", "env": os.getenv("ENV", "development")})


def collect_metrics(r: redis.Redis) -> None:
    """Read all counters from Redis and update Prometheus gauges."""
    def _int(key: str) -> int:
        val = r.get(key)
        return int(val) if val else 0

    EVENTS_PROCESSED.set(_int("metrics:events_processed_total"))
    VELOCITY_HIGH.set(_int("metrics:velocity_high_total"))
    VIOLATIONS.set(_int("metrics:violations_total"))
    PII_MASKS.set(_int("metrics:pii_masks_total"))
    FRAUD_RINGS.set(_int("metrics:fraud_rings_detected_total"))
    AGENT_INVESTIGATIONS.set(_int("metrics:agent_investigations_total"))
    DLQ_EVENTS.set(_int("metrics:dlq_events_total"))

    # Count distinct user feature keys
    active = len(r.keys("feature:user:*:status"))
    ACTIVE_USERS.set(active)


def main():
    print(f"Starting metrics server on :{METRICS_PORT} (scrape every {SCRAPE_INTERVAL}s)")
    start_http_server(METRICS_PORT)

    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0, decode_responses=True)

    while True:
        try:
            collect_metrics(r)
        except Exception as exc:
            print(f"[metrics_server] Error collecting metrics: {exc}")
        time.sleep(SCRAPE_INTERVAL)


if __name__ == "__main__":
    main()
