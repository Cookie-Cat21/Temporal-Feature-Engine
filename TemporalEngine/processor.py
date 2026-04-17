import os
import json
import time
import redis
from datetime import datetime
from pyflink.common import WatermarkStrategy, Configuration, Duration
from pyflink.common.serialization import SimpleStringSchema
from pyflink.common.typeinfo import Types
from pyflink.common.watermark_strategy import TimestampAssigner
from pyflink.datastream import StreamExecutionEnvironment, RuntimeExecutionMode
from pyflink.datastream.checkpointing_mode import CheckpointingMode
from pyflink.datastream.connectors.kafka import (
    KafkaSource, KafkaOffsetsInitializer,
    KafkaSink, KafkaRecordSerializationSchema, DeliveryGuarantee,
)
from pyflink.datastream.functions import KeyedProcessFunction, ProcessFunction, RuntimeContext, SinkFunction
from pyflink.datastream.output_tag import OutputTag
from pyflink.datastream.state import ListStateDescriptor
from pyflink.table import StreamTableEnvironment
from neo4j import GraphDatabase
from pii_shield import PIIShield, process_payload

# --- 1. Project Config (Environment Priority) ---
JAR_PATH    = os.getenv("JAR_PATH",     "lib/iceberg-flink-runtime-1.18-1.5.2.jar")
KAFKA_BROKER = os.getenv("KAFKA_BROKER", "redpanda:9092")
MEMGRAPH_URI = os.getenv("MEMGRAPH_URI", "bolt://memgraph:7687")
REDIS_HOST   = os.getenv("REDIS_HOST",   "redis")
MINIO_ENDPOINT   = os.getenv("MINIO_ENDPOINT",   "http://minio:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "admin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "password")

# Side-output tag for parse failures → Dead Letter Queue
DLQ_TAG = OutputTag("parse_errors", type_info=Types.STRING())


# ---------------------------------------------------------------------------
# Watermark
# ---------------------------------------------------------------------------

class TxTimestampAssigner(TimestampAssigner):
    """Extracts event time from the parsed transaction tuple (type_int, dict)."""

    def extract_timestamp(self, value, record_timestamp: int) -> int:
        try:
            ts_str = value[1].get('timestamp', '')
            dt = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
            return int(dt.timestamp() * 1000)
        except Exception:
            return record_timestamp


# ---------------------------------------------------------------------------
# DLQ: safe JSON parsing with side output for bad events
# ---------------------------------------------------------------------------

class SafeParseFunction(ProcessFunction):
    """Parses raw Kafka strings.  Unparseable events are routed to DLQ_TAG."""

    def __init__(self, msg_type: int):
        self._msg_type = msg_type

    def process_element(self, raw: str, ctx: ProcessFunction.Context):
        try:
            data = json.loads(raw)
            yield (self._msg_type, data)
        except Exception as exc:
            ctx.output(
                DLQ_TAG,
                json.dumps({"raw": raw[:500], "error": str(exc), "ts": time.time()}),
            )


# ---------------------------------------------------------------------------
# Temporal join
# ---------------------------------------------------------------------------

class TemporalJoinFunction(KeyedProcessFunction):
    def open(self, runtime_context: RuntimeContext):
        from pyflink.datastream.state import ValueStateDescriptor
        self.profile_state = runtime_context.get_state(
            ValueStateDescriptor("profile_state", Types.STRING())
        )

    def process_element(self, value, ctx: 'KeyedProcessFunction.Context'):
        msg_type, data = value
        if msg_type == 0:
            self.profile_state.update(json.dumps(data))
        else:
            raw_profile  = self.profile_state.value()
            last_profile = json.loads(raw_profile) if raw_profile else {"status": "UNKNOWN"}
            yield {
                **data,
                "profile_credit_score": str(last_profile.get("credit_score", 0)),
                "profile_status":       last_profile.get("account_status", "NEW"),
                "processed_at":         str(ctx.timestamp()),
            }


# ---------------------------------------------------------------------------
# Velocity detector  (5-minute event-time window per user)
# ---------------------------------------------------------------------------

class VelocityDetector(KeyedProcessFunction):
    WINDOW_MS       = 5 * 60 * 1000
    COUNT_THRESHOLD = 5
    SUM_THRESHOLD   = 1000.0

    def open(self, runtime_context: RuntimeContext):
        self.tx_history = runtime_context.get_list_state(
            ListStateDescriptor("tx_history", Types.TUPLE([Types.LONG(), Types.FLOAT()]))
        )

    def process_element(self, enriched, ctx: 'KeyedProcessFunction.Context'):
        event_ts     = ctx.timestamp()
        window_start = event_ts - self.WINDOW_MS

        try:
            amount = float(enriched.get('amount', 0))
        except (ValueError, TypeError):
            amount = 0.0

        self.tx_history.add((event_ts, amount))
        valid = [(ts, amt) for ts, amt in self.tx_history.get() if ts >= window_start]
        self.tx_history.clear()
        for entry in valid:
            self.tx_history.add(entry)

        tx_count = len(valid)
        tx_sum   = sum(amt for _, amt in valid)

        enriched['tx_count_5m']  = str(tx_count)
        enriched['tx_sum_5m']    = str(round(tx_sum, 2))
        enriched['velocity_flag'] = (
            'HIGH' if (tx_count > self.COUNT_THRESHOLD or tx_sum > self.SUM_THRESHOLD)
            else 'NORMAL'
        )
        yield enriched


# ---------------------------------------------------------------------------
# Governance
# ---------------------------------------------------------------------------

class ContractEnforcer(KeyedProcessFunction):
    def open(self, runtime_context: RuntimeContext):
        with open("contract.json") as f:
            self.contract = json.load(f)

    def process_element(self, enriched, ctx: 'KeyedProcessFunction.Context'):
        allowed    = set(self.contract.get("allowed_fields", []))
        violations = set(enriched.keys()) - allowed
        if violations:
            enriched["governance_status"] = "VIOLATION"
            enriched["violations"]        = list(violations)
            print(f"ALERT: Contract violation for {enriched['user_id']}: {violations}")
        else:
            enriched["governance_status"] = "OK"
        yield enriched


class PIIShieldOperator(KeyedProcessFunction):
    def open(self, runtime_context: RuntimeContext):
        with open("contract.json") as f:
            self.sensitive_fields = json.load(f).get("sensitive_fields", [])
        self._shield = PIIShield()
        self._shield._ensure_loaded()

    def process_element(self, enriched, ctx: 'KeyedProcessFunction.Context'):
        yield process_payload(enriched, self.sensitive_fields, shield=self._shield)


# ---------------------------------------------------------------------------
# Sinks
# ---------------------------------------------------------------------------

class RedisFeatureSink(KeyedProcessFunction):
    def open(self, runtime_context: RuntimeContext):
        self.r = redis.Redis(host=REDIS_HOST, port=6379, db=0)

    def process_element(self, enriched, ctx: 'KeyedProcessFunction.Context'):
        uid = enriched['user_id']
        self.r.set(f"feature:user:{uid}:credit_score",  enriched['profile_credit_score'])
        self.r.set(f"feature:user:{uid}:status",        enriched['profile_status'])
        self.r.set(f"feature:user:{uid}:velocity_flag", enriched.get('velocity_flag', 'NORMAL'))
        # Prometheus counters (read by metrics_server.py)
        self.r.incr("metrics:events_processed_total")
        if enriched.get('velocity_flag') == 'HIGH':
            self.r.incr("metrics:velocity_high_total")
        if enriched.get('governance_status') == 'VIOLATION':
            self.r.incr("metrics:violations_total")
        # Push fraud alerts to Redis list for the dashboard AlertFeed
        if enriched.get('velocity_flag') == 'HIGH' or enriched.get('governance_status') == 'VIOLATION':
            alert = json.dumps({
                'user_id':    uid,
                'alert_type': 'VELOCITY' if enriched.get('velocity_flag') == 'HIGH' else 'GOVERNANCE',
                'amount':     enriched.get('amount', '0'),
                'merchant':   enriched.get('merchant', ''),
                'ts':         time.time(),
            })
            self.r.lpush('fraud:alerts', alert)
            self.r.ltrim('fraud:alerts', 0, 49)   # keep last 50
        yield enriched


class GraphSyncSink(KeyedProcessFunction):
    """Writes User, Merchant, Device and IP nodes — enabling ring + network analysis."""

    def open(self, runtime_context: RuntimeContext):
        self.driver = GraphDatabase.driver(MEMGRAPH_URI, auth=("", ""))

    def process_element(self, enriched, ctx: 'KeyedProcessFunction.Context'):
        with self.driver.session() as session:
            cypher = """
            MERGE (u:User {user_id: $uid})
              SET u.governance_status = $gov_status,
                  u.violations        = $violations,
                  u.velocity_flag     = $velocity_flag

            MERGE (m:Merchant {merchant_name: $merchant})
            CREATE (u)-[:TRANSACTED_WITH {amount: $amount, ts: $ts}]->(m)

            WITH u
            WHERE $device_id <> ''
            MERGE (d:Device {device_id: $device_id})
            MERGE (u)-[:LOGGED_IN_FROM]->(d)

            WITH u
            WHERE $ip_address <> ''
            MERGE (ip:IP {ip_address: $ip_address})
            MERGE (u)-[:LOGGED_IN_FROM]->(ip)
            """
            session.run(
                cypher,
                uid          = enriched['user_id'],
                gov_status   = enriched.get('governance_status', 'OK'),
                violations   = json.dumps(enriched.get('violations', [])),
                velocity_flag = enriched.get('velocity_flag', 'NORMAL'),
                merchant   = enriched['merchant'],
                amount     = enriched['amount'],
                ts         = enriched['processed_at'],
                device_id  = enriched.get('device_id', ''),
                ip_address = enriched.get('ip_address', ''),
            )
        yield enriched


class IcebergSink(SinkFunction):
    """Buffers enriched records and appends them to the Iceberg table in MinIO."""

    BATCH_SIZE = 50

    def __init__(self):
        self._buffer = []
        self._table  = None

    def open(self, runtime_context):
        from pyiceberg.catalog import load_catalog
        catalog = load_catalog(
            "hadoop",
            **{
                "type":               "hadoop",
                "warehouse":          "s3://warehouse",
                "s3.endpoint":        MINIO_ENDPOINT,
                "s3.access-key-id":   MINIO_ACCESS_KEY,
                "s3.secret-access-key": MINIO_SECRET_KEY,
                "s3.path-style-access": "true",
            },
        )
        try:
            self._table = catalog.load_table("db.enriched_transactions")
        except Exception as e:
            print(f"[IcebergSink] Could not load table — run create_iceberg_tables.py first: {e}")

    def invoke(self, value, context):
        if self._table is None:
            return
        self._buffer.append(value)
        if len(self._buffer) >= self.BATCH_SIZE:
            self._flush()

    def close(self):
        if self._buffer:
            self._flush()

    def _flush(self):
        try:
            import pandas as pd
            df = pd.DataFrame(self._buffer)
            # Ensure all expected columns exist
            for col in ["transaction_id", "user_id", "amount", "merchant", "processed_at",
                        "profile_credit_score", "profile_status", "tx_count_5m",
                        "tx_sum_5m", "velocity_flag", "governance_status",
                        "device_id", "ip_address"]:
                if col not in df.columns:
                    df[col] = ""
            self._table.append(df)
            print(f"[IcebergSink] Wrote {len(self._buffer)} records to Iceberg.")
        except Exception as e:
            print(f"[IcebergSink] Flush error: {e}")
        finally:
            self._buffer.clear()


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def run_temporal_engine():
    # --- 2. Environment ---
    config = Configuration()
    env    = StreamExecutionEnvironment.get_execution_environment(config)
    t_env  = StreamTableEnvironment.create(env)

    # Checkpointing: EXACTLY_ONCE every 60 s, stored in MinIO
    env.enable_checkpointing(60_000)
    env.get_checkpoint_config().set_checkpointing_mode(CheckpointingMode.EXACTLY_ONCE)
    env.get_checkpoint_config().set_min_pause_between_checkpoints(30_000)
    env.get_checkpoint_config().set_checkpoint_timeout(120_000)
    env.get_checkpoint_config().set_max_concurrent_checkpoints(1)

    # Add JARs for Kafka and Iceberg
    env.add_jars(f"file://{os.path.abspath('lib/iceberg-flink-runtime-1.18-1.5.2.jar')}")
    env.add_jars(f"file://{os.path.abspath('lib/hadoop-aws-3.3.4.jar')}")

    # Register Iceberg catalog
    t_env.execute_sql("""
        CREATE CATALOG iceberg_catalog WITH (
            'type'='iceberg',
            'catalog-impl'='org.apache.iceberg.hadoop.HadoopCatalog',
            'warehouse'='s3a://warehouse/',
            's3.endpoint'='http://minio:9000',
            's3.path-style-access'='true',
            's3.access-key'='admin',
            's3.secret-key'='password'
        )
    """)

    # --- 3. Sources ---
    tx_source = (
        KafkaSource.builder()
        .set_bootstrap_servers(KAFKA_BROKER)
        .set_topics("user_transactions")
        .set_group_id("temporal_engine_group")
        .set_starting_offsets(KafkaOffsetsInitializer.earliest())
        .set_value_only_deserializer(SimpleStringSchema())
        .build()
    )
    profile_source = (
        KafkaSource.builder()
        .set_bootstrap_servers(KAFKA_BROKER)
        .set_topics("user_profiles")
        .set_group_id("temporal_engine_group")
        .set_starting_offsets(KafkaOffsetsInitializer.earliest())
        .set_value_only_deserializer(SimpleStringSchema())
        .build()
    )

    # --- 4. Parse with DLQ side-output ---
    tx_parsed = (
        env.from_source(tx_source, WatermarkStrategy.no_watermarks(), "TxSource")
        .process(SafeParseFunction(msg_type=1),
                 output_type=Types.TUPLE([Types.INT(), Types.MAP(Types.STRING(), Types.STRING())]))
    )
    profile_parsed = (
        env.from_source(profile_source, WatermarkStrategy.no_watermarks(), "ProfileSource")
        .process(SafeParseFunction(msg_type=0),
                 output_type=Types.TUPLE([Types.INT(), Types.MAP(Types.STRING(), Types.STRING())]))
    )

    # Route bad events to DLQ topic
    dlq_sink = (
        KafkaSink.builder()
        .set_bootstrap_servers(KAFKA_BROKER)
        .set_record_serializer(
            KafkaRecordSerializationSchema.builder()
            .set_topic("user_transactions_dlq")
            .set_value_serialization_schema(SimpleStringSchema())
            .build()
        )
        .set_delivery_guarantee(DeliveryGuarantee.AT_LEAST_ONCE)
        .build()
    )
    tx_parsed.get_side_output(DLQ_TAG).sink_to(dlq_sink)
    profile_parsed.get_side_output(DLQ_TAG).sink_to(dlq_sink)

    # --- 5. Watermarks (on transaction stream only) ---
    event_time_strategy = (
        WatermarkStrategy
        .for_bounded_out_of_orderness(Duration.of_seconds(30))
        .with_timestamp_assigner(TxTimestampAssigner())
    )
    tx_stream      = tx_parsed.assign_timestamps_and_watermarks(event_time_strategy)
    profile_stream = profile_parsed

    # --- 6. Temporal join ---
    enriched_stream = (
        tx_stream.union(profile_stream)
        .key_by(lambda x: x[1]['user_id'])
        .process(TemporalJoinFunction(),
                 output_type=Types.MAP(Types.STRING(), Types.STRING()))
    )

    # --- 7. Velocity detection ---
    velocity_stream = enriched_stream.process(
        VelocityDetector(), output_type=Types.MAP(Types.STRING(), Types.STRING())
    )

    # --- 8. Sovereignty guard ---
    governed_stream = (
        velocity_stream
        .process(ContractEnforcer(), output_type=Types.MAP(Types.STRING(), Types.STRING()))
        .process(PIIShieldOperator(), output_type=Types.MAP(Types.STRING(), Types.STRING()))
    )

    # --- 9. Alert routing — HIGH velocity or governance VIOLATION → fraud_alerts ---
    alert_sink = (
        KafkaSink.builder()
        .set_bootstrap_servers(KAFKA_BROKER)
        .set_record_serializer(
            KafkaRecordSerializationSchema.builder()
            .set_topic("fraud_alerts")
            .set_value_serialization_schema(SimpleStringSchema())
            .build()
        )
        .set_delivery_guarantee(DeliveryGuarantee.AT_LEAST_ONCE)
        .build()
    )
    (
        governed_stream
        .filter(lambda x: x.get('velocity_flag') == 'HIGH' or x.get('governance_status') == 'VIOLATION')
        .map(
            lambda x: json.dumps({
                "user_id":           x['user_id'],
                "alert_type":        "VELOCITY" if x.get('velocity_flag') == 'HIGH' else "GOVERNANCE",
                "velocity_flag":     x.get('velocity_flag'),
                "governance_status": x.get('governance_status'),
                "amount":            x.get('amount'),
                "ts":                x.get('processed_at'),
            }),
            output_type=Types.STRING(),
        )
        .sink_to(alert_sink)
    )

    # --- 10. Feature store + graph + Iceberg ---
    final_stream = (
        governed_stream
        .process(RedisFeatureSink(), output_type=Types.MAP(Types.STRING(), Types.STRING()))
        .process(GraphSyncSink(),   output_type=Types.MAP(Types.STRING(), Types.STRING()))
    )
    final_stream.add_sink(IcebergSink())
    final_stream.print()

    print("Submitting Flink Job...")
    env.execute("Temporal Feature Engine")


if __name__ == "__main__":
    run_temporal_engine()
