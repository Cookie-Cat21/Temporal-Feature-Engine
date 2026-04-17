"""
One-time setup script — run this BEFORE starting the Flink processor.

Creates the Iceberg database and `db.enriched_transactions` table in MinIO.
The Flink IcebergSink will append to this table during normal operation,
enabling true time-travel queries via verify_timetravel.py.

Usage:
    python create_iceberg_tables.py

Environment variables (or defaults):
    MINIO_ENDPOINT    http://localhost:9000
    MINIO_ACCESS_KEY  admin
    MINIO_SECRET_KEY  password
"""

import os
from pyiceberg.catalog import load_catalog
from pyiceberg.schema import Schema
from pyiceberg.types import (
    NestedField, StringType, DoubleType, LongType, TimestampType,
)
from pyiceberg.partitioning import PartitionSpec, PartitionField
from pyiceberg.transforms import DayTransform

MINIO_ENDPOINT   = os.getenv("MINIO_ENDPOINT",   "http://localhost:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "admin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "password")


def main():
    print(f"Connecting to MinIO at {MINIO_ENDPOINT}...")

    catalog = load_catalog(
        "hadoop",
        **{
            "type":                 "hadoop",
            "warehouse":            "s3://warehouse",
            "s3.endpoint":          MINIO_ENDPOINT,
            "s3.access-key-id":     MINIO_ACCESS_KEY,
            "s3.secret-access-key": MINIO_SECRET_KEY,
            "s3.path-style-access": "true",
        },
    )

    # Create namespace
    try:
        catalog.create_namespace("db")
        print("Created namespace: db")
    except Exception:
        print("Namespace 'db' already exists — skipping.")

    # Schema for enriched transactions
    schema = Schema(
        NestedField(1,  "transaction_id",      StringType(),    required=False),
        NestedField(2,  "user_id",             StringType(),    required=True),
        NestedField(3,  "amount",              StringType(),    required=False),
        NestedField(4,  "merchant",            StringType(),    required=False),
        NestedField(5,  "processed_at",        StringType(),    required=False),
        NestedField(6,  "profile_credit_score",StringType(),    required=False),
        NestedField(7,  "profile_status",      StringType(),    required=False),
        NestedField(8,  "tx_count_5m",         StringType(),    required=False),
        NestedField(9,  "tx_sum_5m",           StringType(),    required=False),
        NestedField(10, "velocity_flag",       StringType(),    required=False),
        NestedField(11, "governance_status",   StringType(),    required=False),
        NestedField(12, "device_id",           StringType(),    required=False),
        NestedField(13, "ip_address",          StringType(),    required=False),
    )

    table_id = "db.enriched_transactions"

    try:
        table = catalog.create_table(table_id, schema=schema)
        print(f"Created table: {table_id}")
        print(f"Table location: {table.location()}")
    except Exception:
        print(f"Table '{table_id}' already exists — skipping.")
        table = catalog.load_table(table_id)

    # Print snapshot history to confirm time-travel is available
    history = table.history()
    print(f"\nCurrent snapshot count: {len(history)}")
    if history:
        for snap in history[-3:]:
            from datetime import datetime
            ts = datetime.utcfromtimestamp(snap.timestamp_ms / 1000)
            print(f"  snapshot_id={snap.snapshot_id}  @{ts} UTC")

    print("\nSetup complete. Start the Flink processor to begin writing data.")


if __name__ == "__main__":
    main()
