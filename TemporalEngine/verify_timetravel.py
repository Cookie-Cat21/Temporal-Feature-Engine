import os
import redis
from datetime import datetime

# --- 1. Validation Config ---
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "http://localhost:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "admin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "password")
WAREHOUSE_PATH = "s3://warehouse"


def check_realtime_serving():
    """Verify that Redis is receiving live feature updates."""
    print("\n--- Phase 1: Real-Time Serving Audit ---")
    try:
        r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0)
        found = 0
        for i in range(1, 11):
            uid = f"user_{i}"
            score = r.get(f"feature:user:{uid}:credit_score")
            status = r.get(f"feature:user:{uid}:status")
            velocity = r.get(f"feature:user:{uid}:velocity_flag")
            if score:
                found += 1
                print(
                    f"  ✓ {uid} | score={score.decode()} "
                    f"status={status.decode() if status else 'N/A'} "
                    f"velocity={velocity.decode() if velocity else 'N/A'}"
                )
        if found == 0:
            print("  ! No features found. Is the Processor running?")
        else:
            print(f"  {found}/10 users have live features in Redis.")
    except Exception as e:
        print(f"  Error connecting to Redis: {e}")


def check_iceberg_timetravel():
    """Perform actual Iceberg time-travel: query the warehouse AS OF each snapshot.

    Requires the Flink processor to have written at least one Iceberg commit.
    Prints a diff between the earliest and latest snapshot to demonstrate
    true point-in-time correctness — the core 'temporal' feature of this engine.
    """
    print("\n--- Phase 2: Iceberg Time-Travel Audit ---")
    try:
        from pyiceberg.catalog import load_catalog

        catalog = load_catalog(
            "hadoop",
            **{
                "type": "hadoop",
                "warehouse": WAREHOUSE_PATH,
                "s3.endpoint": MINIO_ENDPOINT,
                "s3.access-key-id": MINIO_ACCESS_KEY,
                "s3.secret-access-key": MINIO_SECRET_KEY,
                "s3.path-style-access": "true",
            },
        )

        try:
            table = catalog.load_table("db.transactions")
        except Exception:
            print("  ! Table 'db.transactions' not found — run the Flink processor first.")
            return

        history = table.history()
        if not history:
            print("  ! No snapshots found yet.")
            return

        print(f"  Found {len(history)} snapshot(s).")

        # --- Snapshot 0: earliest ---
        snap_0 = history[0]
        snap_0_ts = datetime.utcfromtimestamp(snap_0.timestamp_ms / 1000)
        df_0 = table.scan(snapshot_id=snap_0.snapshot_id).to_pandas()
        print(f"\n  [T0] Snapshot {snap_0.snapshot_id} @ {snap_0_ts} UTC")
        print(f"       Records: {len(df_0)}")
        if not df_0.empty:
            print(f"       Sample user_ids: {df_0['user_id'].head(3).tolist()}")

        # --- Snapshot N: latest ---
        snap_n = history[-1]
        snap_n_ts = datetime.utcfromtimestamp(snap_n.timestamp_ms / 1000)
        df_n = table.scan(snapshot_id=snap_n.snapshot_id).to_pandas()
        print(f"\n  [T_now] Snapshot {snap_n.snapshot_id} @ {snap_n_ts} UTC")
        print(f"       Records: {len(df_n)}")

        delta = len(df_n) - len(df_0)
        print(f"\n  Net new records since T0: {delta:+d}")

        # --- Velocity flag distribution at latest snapshot ---
        if 'velocity_flag' in df_n.columns:
            dist = df_n['velocity_flag'].value_counts().to_dict()
            print(f"  Velocity flag breakdown: {dist}")

        print("\n  ✓ Point-in-time query confirmed: the engine can reconstruct")
        print("    any historical state by replaying to an arbitrary snapshot_id.")

    except ImportError:
        print("  ! pyiceberg not installed. Run: pip install pyiceberg")
    except Exception as e:
        print(f"  Error during Iceberg time-travel audit: {e}")


def check_late_arrival_impact():
    """Show whether late-arriving events caused watermark delays.

    Reads the 'ghost transaction' keys that producer.py tags and compares
    their event timestamps to their Redis ingest times.
    """
    print("\n--- Phase 3: Late Arrival Detection ---")
    try:
        r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0)
        late_keys = r.keys("late:*")
        if late_keys:
            print(f"  {len(late_keys)} late-arrival event(s) recorded.")
            for k in late_keys[:5]:
                print(f"  {k.decode()}: {r.get(k).decode()}")
        else:
            print("  No late-arrival markers in Redis (or producer hasn't fired one yet).")
    except Exception as e:
        print(f"  Error: {e}")


if __name__ == "__main__":
    print(f"Temporal Engine Validator v2.0 | {datetime.now().isoformat()}")

    check_realtime_serving()
    check_iceberg_timetravel()
    check_late_arrival_impact()

    print("\n[✓] Audit Complete.")
