import os
import json
import redis
from datetime import datetime
from pyflink.common import WatermarkStrategy, Configuration, Duration
from pyflink.common.serialization import SimpleStringSchema
from pyflink.common.typeinfo import Types
from pyflink.common.watermark_strategy import TimestampAssigner
from pyflink.datastream import StreamExecutionEnvironment, RuntimeExecutionMode
from pyflink.datastream.connectors.kafka import KafkaSource, KafkaOffsetsInitializer
from pyflink.datastream.functions import KeyedProcessFunction, RuntimeContext
from pyflink.datastream.state import ListStateDescriptor
from pyflink.table import StreamTableEnvironment
from neo4j import GraphDatabase
from pii_shield import PIIShield, process_payload

# --- 1. Project Config (Environment Priority) ---
JAR_PATH = os.getenv("JAR_PATH", "lib/iceberg-flink-runtime-1.18-1.5.2.jar")
KAFKA_BROKER = os.getenv("KAFKA_BROKER", "redpanda:9092")
MEMGRAPH_URI = os.getenv("MEMGRAPH_URI", "bolt://memgraph:7687")
REDIS_HOST = os.getenv("REDIS_HOST", "redis")

class TxTimestampAssigner(TimestampAssigner):
    """Extracts event time from the parsed transaction tuple (type_int, dict)."""

    def extract_timestamp(self, value, record_timestamp: int) -> int:
        try:
            ts_str = value[1].get('timestamp', '')
            dt = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
            return int(dt.timestamp() * 1000)
        except Exception:
            return record_timestamp


class TemporalJoinFunction(KeyedProcessFunction):
    def __init__(self):
        self.profile_state = None

    def open(self, runtime_context: RuntimeContext):
        from pyflink.datastream.state import ValueStateDescriptor
        descriptor = ValueStateDescriptor("profile_state", Types.STRING())
        self.profile_state = runtime_context.get_state(descriptor)

    def process_element(self, value, ctx: 'KeyedProcessFunction.Context'):
        msg_type, data = value
        if msg_type == 0:
            self.profile_state.update(json.dumps(data))
        else:
            last_profile_json = self.profile_state.value()
            last_profile = json.loads(last_profile_json) if last_profile_json else {"status": "UNKNOWN"}
            enriched = {
                **data,
                "profile_credit_score": str(last_profile.get("credit_score", 0)),
                "profile_status": last_profile.get("account_status", "NEW"),
                "processed_at": str(ctx.timestamp())
            }
            yield enriched

class RedisFeatureSink(KeyedProcessFunction):
    def __init__(self):
        self.r = None

    def open(self, runtime_context: RuntimeContext):
        self.r = redis.Redis(host=REDIS_HOST, port=6379, db=0)

    def process_element(self, enriched, ctx: 'KeyedProcessFunction.Context'):
        user_id = enriched['user_id']
        self.r.set(f"feature:user:{user_id}:credit_score", enriched['profile_credit_score'])
        self.r.set(f"feature:user:{user_id}:status", enriched['profile_status'])
        yield enriched

class GraphSyncSink(KeyedProcessFunction):
    def __init__(self):
        self.driver = None

    def open(self, runtime_context: RuntimeContext):
        # 'memgraph' is the service name in docker-compose
        self.driver = GraphDatabase.driver(MEMGRAPH_URI, auth=("", ""))

    def process_element(self, enriched, ctx: 'KeyedProcessFunction.Context'):
        with self.driver.session() as session:
            cypher = """
            MERGE (u:User {user_id: $uid})
            SET u.governance_status = $status, u.violations = $violations
            MERGE (m:Merchant {merchant_name: $merchant})
            CREATE (u)-[:TRANSACTED_WITH {amount: $amount, ts: $ts}]->(m)
            """
            session.run(cypher, 
                        uid=enriched['user_id'], 
                        status=enriched.get('governance_status', 'OK'),
                        violations=json.dumps(enriched.get('violations', [])),
                        merchant=enriched['merchant'], 
                        amount=enriched['amount'], 
                        ts=enriched['processed_at'])
        yield enriched

class VelocityDetector(KeyedProcessFunction):
    """Computes per-user transaction velocity over a 5-minute event-time window.

    Uses a ListState of (event_ts_ms, amount) pairs.  On every event, entries
    older than the window are evicted and velocity features are appended to the
    enriched record before it continues downstream.
    """

    WINDOW_MS = 5 * 60 * 1000   # 5 minutes
    COUNT_THRESHOLD = 5          # > 5 txns in window → HIGH
    SUM_THRESHOLD = 1000.0       # > $1 000 in window → HIGH

    def open(self, runtime_context: RuntimeContext):
        self.tx_history = runtime_context.get_list_state(
            ListStateDescriptor("tx_history", Types.TUPLE([Types.LONG(), Types.FLOAT()]))
        )

    def process_element(self, enriched, ctx: 'KeyedProcessFunction.Context'):
        event_ts = ctx.timestamp()
        window_start = event_ts - self.WINDOW_MS

        try:
            amount = float(enriched.get('amount', 0))
        except (ValueError, TypeError):
            amount = 0.0

        self.tx_history.add((event_ts, amount))

        # Evict entries outside the window
        valid = [(ts, amt) for ts, amt in self.tx_history.get() if ts >= window_start]
        self.tx_history.clear()
        for entry in valid:
            self.tx_history.add(entry)

        tx_count = len(valid)
        tx_sum = sum(amt for _, amt in valid)

        enriched['tx_count_5m'] = str(tx_count)
        enriched['tx_sum_5m'] = str(round(tx_sum, 2))
        enriched['velocity_flag'] = (
            'HIGH' if (tx_count > self.COUNT_THRESHOLD or tx_sum > self.SUM_THRESHOLD)
            else 'NORMAL'
        )
        yield enriched


class ContractEnforcer(KeyedProcessFunction):
    def __init__(self):
        self.contract = None

    def open(self, runtime_context: RuntimeContext):
        with open("contract.json", "r") as f:
            self.contract = json.load(f)

    def process_element(self, enriched, ctx: 'KeyedProcessFunction.Context'):
        allowed = set(self.contract.get("allowed_fields", []))
        current_keys = set(enriched.keys())
        
        violations = current_keys - allowed
        if violations:
            # Tag and Alert (not blocking for now)
            enriched["governance_status"] = "VIOLATION"
            enriched["violations"] = list(violations)
            print(f"ALERT: Contract violation for user {enriched['user_id']}: {violations}")
        else:
            enriched["governance_status"] = "OK"
            
        yield enriched

class PIIShieldOperator(KeyedProcessFunction):
    def __init__(self):
        self.sensitive_fields = None
        self._shield = None

    def open(self, runtime_context: RuntimeContext):
        with open("contract.json", "r") as f:
            contract = json.load(f)
            self.sensitive_fields = contract.get("sensitive_fields", [])
        # Initialise once per Flink task slot — avoids re-loading spaCy/Presidio per record
        self._shield = PIIShield()
        self._shield._ensure_loaded()

    def process_element(self, enriched, ctx: 'KeyedProcessFunction.Context'):
        masked = process_payload(enriched, self.sensitive_fields, shield=self._shield)
        yield masked

def run_temporal_engine():
    # --- 2. Setup Environment ---
    config = Configuration()
    env = StreamExecutionEnvironment.get_execution_environment(config)
    t_env = StreamTableEnvironment.create(env)
    
    # Add JARs for Kafka and Iceberg
    env.add_jars(f"file://{os.path.abspath('lib/iceberg-flink-runtime-1.18-1.5.2.jar')}")
    env.add_jars(f"file://{os.path.abspath('lib/hadoop-aws-3.3.4.jar')}")

    # Register Iceberg Catalog
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
    tx_source = KafkaSource.builder() \
        .set_bootstrap_servers(KAFKA_BROKER) \
        .set_topics("user_transactions") \
        .set_group_id("temporal_engine_group") \
        .set_starting_offsets(KafkaOffsetsInitializer.earliest()) \
        .set_value_only_deserializer(SimpleStringSchema()) \
        .build()

    profile_source = KafkaSource.builder() \
        .set_bootstrap_servers(KAFKA_BROKER) \
        .set_topics("user_profiles") \
        .set_group_id("temporal_engine_group") \
        .set_starting_offsets(KafkaOffsetsInitializer.earliest()) \
        .set_value_only_deserializer(SimpleStringSchema()) \
        .build()

    # Parse first, then assign event-time watermarks from the 'timestamp' field.
    # 30-second out-of-orderness tolerance matches the late-arrival simulation in producer.py.
    event_time_strategy = (
        WatermarkStrategy
        .for_bounded_out_of_orderness(Duration.of_seconds(30))
        .with_timestamp_assigner(TxTimestampAssigner())
    )

    tx_stream = (
        env.from_source(tx_source, WatermarkStrategy.no_watermarks(), "TxSource")
        .map(lambda x: (1, json.loads(x)), output_type=Types.TUPLE([Types.INT(), Types.MAP(Types.STRING(), Types.STRING())]))
        .assign_timestamps_and_watermarks(event_time_strategy)
    )

    profile_stream = (
        env.from_source(profile_source, WatermarkStrategy.no_watermarks(), "ProfileSource")
        .map(lambda x: (0, json.loads(x)), output_type=Types.TUPLE([Types.INT(), Types.MAP(Types.STRING(), Types.STRING())]))
    )

    # --- 4. The Core Logic: Connected Streams ---
    enriched_stream = tx_stream.union(profile_stream) \
        .key_by(lambda x: x[1]['user_id']) \
        .process(TemporalJoinFunction(), output_type=Types.MAP(Types.STRING(), Types.STRING()))

    # --- 5. Velocity Detection (event-time windowed per-user stats) ---
    velocity_stream = enriched_stream.process(
        VelocityDetector(), output_type=Types.MAP(Types.STRING(), Types.STRING())
    )

    # --- 6. The Sovereignty Guard (PII Masking & Contracts) ---
    governed_stream = (
        velocity_stream
        .process(ContractEnforcer(), output_type=Types.MAP(Types.STRING(), Types.STRING()))
        .process(PIIShieldOperator(), output_type=Types.MAP(Types.STRING(), Types.STRING()))
    )

    # --- 7. Sinks ---
    # Sync to Redis for real-time features
    final_stream = governed_stream.process(RedisFeatureSink(), output_type=Types.MAP(Types.STRING(), Types.STRING()))
    
    # Sync to Memgraph for Graph Reasoning
    final_stream = final_stream.process(GraphSyncSink(), output_type=Types.MAP(Types.STRING(), Types.STRING()))

    # Print results
    final_stream.print()
    
    print("Submitting Flink Job...")
    env.execute("Temporal Feature Engine")

if __name__ == "__main__":
    run_temporal_engine()
