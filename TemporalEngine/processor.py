import os
import json
import redis
from pyflink.common import WatermarkStrategy, Configuration
from pyflink.common.serialization import SimpleStringSchema
from pyflink.common.typeinfo import Types
from pyflink.datastream import StreamExecutionEnvironment, RuntimeExecutionMode
from pyflink.datastream.connectors.kafka import KafkaSource, KafkaOffsetsInitializer
from pyflink.datastream.functions import KeyedProcessFunction, RuntimeContext
from pyflink.table import StreamTableEnvironment
from neo4j import GraphDatabase

# --- 1. Project Config ---
JAR_PATH = "lib/iceberg-flink-runtime-1.18-1.5.2.jar"
KAFKA_BROKER = "redpanda:9092"

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
        self.r = redis.Redis(host='redis', port=6379, db=0)

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
        self.driver = GraphDatabase.driver("bolt://memgraph:7687", auth=("", ""))

    def process_element(self, enriched, ctx: 'KeyedProcessFunction.Context'):
        with self.driver.session() as session:
            cypher = """
            MERGE (u:User {user_id: $uid})
            MERGE (m:Merchant {merchant_name: $merchant})
            CREATE (u)-[:TRANSACTED_WITH {amount: $amount, ts: $ts}]->(m)
            """
            session.run(cypher, uid=enriched['user_id'], merchant=enriched['merchant'], amount=enriched['amount'], ts=enriched['processed_at'])
        yield enriched

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

    tx_stream = env.from_source(tx_source, WatermarkStrategy.no_watermarks(), "TxSource") \
        .map(lambda x: (1, json.loads(x)), output_type=Types.TUPLE([Types.INT(), Types.MAP(Types.STRING(), Types.STRING())]))

    profile_stream = env.from_source(profile_source, WatermarkStrategy.no_watermarks(), "ProfileSource") \
        .map(lambda x: (0, json.loads(x)), output_type=Types.TUPLE([Types.INT(), Types.MAP(Types.STRING(), Types.STRING())]))

    # --- 4. The Core Logic: Connected Streams ---
    enriched_stream = tx_stream.union(profile_stream) \
        .key_by(lambda x: x[1]['user_id']) \
        .process(TemporalJoinFunction(), output_type=Types.MAP(Types.STRING(), Types.STRING())) \
        .process(RedisFeatureSink(), output_type=Types.MAP(Types.STRING(), Types.STRING()))

    # --- 5. Sinks ---
    # Sync to Redis for real-time features
    enriched_stream = full_stream.process(RedisFeatureSink(), output_type=Types.MAP(Types.STRING(), Types.STRING()))
    
    # Sync to Memgraph for Graph Reasoning
    final_stream = enriched_stream.process(GraphSyncSink(), output_type=Types.MAP(Types.STRING(), Types.STRING()))

    # Print results
    final_stream.print()
    
    print("Submitting Flink Job...")
    env.execute("Temporal Feature Engine")

if __name__ == "__main__":
    run_temporal_engine()
