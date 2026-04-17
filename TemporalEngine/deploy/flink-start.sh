#!/bin/bash
# Starts Flink JobManager + TaskManager in a single container, then submits
# the TemporalEngine Python streaming job.
set -e

export FLINK_PROPERTIES="
jobmanager.rpc.address: 0.0.0.0
jobmanager.rpc.port: 6123
taskmanager.numberOfTaskSlots: 2
rest.port: 8081
rest.address: 0.0.0.0
metrics.reporter.prom.class: org.apache.flink.metrics.prometheus.PrometheusReporter
metrics.reporter.prom.port: 9249
state.backend: filesystem
state.checkpoints.dir: s3a://warehouse/checkpoints
s3.endpoint: ${MINIO_ENDPOINT:-http://temporal-minio.internal:9000}
s3.path.style.access: true
s3.access-key: ${MINIO_ACCESS_KEY:-admin}
s3.secret-key: ${MINIO_SECRET_KEY:-password}
"

echo "[flink-start] Starting JobManager..."
/docker-entrypoint.sh jobmanager &
JM_PID=$!

echo "[flink-start] Starting TaskManager..."
sleep 6
/docker-entrypoint.sh taskmanager &

echo "[flink-start] Waiting for cluster to become ready..."
until curl -sf http://localhost:8081/overview > /dev/null 2>&1; do
  sleep 3
done
echo "[flink-start] Cluster ready."

# Create the Iceberg table schema before the job starts
echo "[flink-start] Bootstrapping Iceberg tables..."
cd /opt/flink/usrlib
python3 create_iceberg_tables.py || echo "[flink-start] Iceberg bootstrap skipped (MinIO may not be ready yet)."

# Submit the streaming job
echo "[flink-start] Submitting Temporal Feature Engine job..."
flink run --python processor.py || echo "[flink-start] Job submission failed — cluster still running, retry manually."

echo "[flink-start] Job submitted. Keeping cluster alive..."
wait $JM_PID
