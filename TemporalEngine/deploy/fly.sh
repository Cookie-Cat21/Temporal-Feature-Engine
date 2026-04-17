#!/usr/bin/env bash
# =============================================================================
# TemporalEngine — Fly.io deployment script
# Run from the TemporalEngine/ directory:  bash deploy/fly.sh
# =============================================================================
set -euo pipefail

REGION="${FLY_REGION:-iad}"
ORG="${FLY_ORG:-personal}"

# Colour helpers
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()    { echo -e "${GREEN}[deploy]${NC} $*"; }
warn()    { echo -e "${YELLOW}[warn]${NC}  $*"; }
die()     { echo -e "${RED}[error]${NC} $*"; exit 1; }

command -v fly >/dev/null 2>&1 || die "flyctl not found. Install: curl -L https://fly.io/install.sh | sh"

# ---------------------------------------------------------------------------
# 0. Confirm login
# ---------------------------------------------------------------------------
info "Checking Fly.io login..."
fly auth whoami || die "Run 'fly auth login' first."

# ---------------------------------------------------------------------------
# 1. Managed Redis (Upstash via Fly)
# ---------------------------------------------------------------------------
info "Creating managed Redis..."
if fly redis list | grep -q "temporal-engine-redis"; then
  warn "temporal-engine-redis already exists — skipping."
  REDIS_URL=$(fly redis status temporal-engine-redis --json | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('privateUrl',''))")
else
  REDIS_URL=$(fly redis create \
    --name temporal-engine-redis \
    --region "$REGION" \
    --no-replicas \
    --vm-size shared-cpu-1x \
    --json | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('privateUrl',''))")
fi
info "Redis URL: ${REDIS_URL:0:30}..."

# ---------------------------------------------------------------------------
# Helper: create app + volume + deploy
# ---------------------------------------------------------------------------
create_and_deploy() {
  local APP="$1"
  local CONFIG="$2"
  local VOLUME="$3"     # optional, pass "" to skip
  local VOL_SIZE="${4:-5}"

  if fly apps list | grep -q "$APP"; then
    warn "App $APP already exists — redeploying."
  else
    info "Creating app: $APP"
    fly apps create "$APP" --org "$ORG"
  fi

  if [[ -n "$VOLUME" ]]; then
    if ! fly volumes list --app "$APP" | grep -q "$VOLUME"; then
      info "Creating volume $VOLUME for $APP (${VOL_SIZE}GB)..."
      fly volumes create "$VOLUME" \
        --app "$APP" \
        --region "$REGION" \
        --size "$VOL_SIZE"
    else
      warn "Volume $VOLUME already exists — skipping."
    fi
  fi

  info "Deploying $APP..."
  fly deploy --config "$CONFIG" --app "$APP" --region "$REGION" --remote-only
}

# ---------------------------------------------------------------------------
# 2. Redpanda
# ---------------------------------------------------------------------------
create_and_deploy \
  "temporal-redpanda" \
  "deploy/configs/redpanda.toml" \
  "redpanda_data" 10

info "Waiting for Redpanda to stabilise..."
sleep 10

# Create required Kafka topics
info "Creating Kafka topics..."
fly ssh console --app temporal-redpanda --command \
  "rpk topic create user_transactions user_profiles user_transactions_dlq fraud_alerts \
   --brokers localhost:9092 || true"

# ---------------------------------------------------------------------------
# 3. MinIO
# ---------------------------------------------------------------------------
create_and_deploy \
  "temporal-minio" \
  "deploy/configs/minio.toml" \
  "minio_data" 10

info "Waiting for MinIO to stabilise..."
sleep 8

# Create warehouse bucket
info "Creating MinIO warehouse bucket..."
fly ssh console --app temporal-minio --command \
  "mc alias set local http://localhost:9000 admin password && \
   mc mb local/warehouse --ignore-existing || true" 2>/dev/null || \
  warn "Could not create bucket via SSH — create it manually in MinIO console."

# ---------------------------------------------------------------------------
# 4. Memgraph
# ---------------------------------------------------------------------------
create_and_deploy \
  "temporal-memgraph" \
  "deploy/configs/memgraph.toml" \
  "memgraph_data" 5

# Allocate a public IPv4 so Vercel can reach Memgraph over Bolt
info "Allocating public IP for Memgraph..."
fly ips allocate-v4 --shared --app temporal-memgraph 2>/dev/null || \
  warn "IPv4 already allocated or failed — check: fly ips list --app temporal-memgraph"

MEMGRAPH_IP=$(fly ips list --app temporal-memgraph --json 2>/dev/null | \
  python3 -c "import sys,json; ips=json.load(sys.stdin); \
  v4=[i for i in ips if i['Type']=='v4']; print(v4[0]['Address'] if v4 else '')" 2>/dev/null || echo "")

# ---------------------------------------------------------------------------
# 5. Flink (JobManager + TaskManager + job submission)
# ---------------------------------------------------------------------------
create_and_deploy \
  "temporal-flink" \
  "deploy/configs/flink.toml" \
  "" 0

# Inject Redis + MinIO secrets into Flink
fly secrets set \
  --app temporal-flink \
  REDIS_URL="$REDIS_URL" \
  MINIO_SECRET_KEY="password" \
  KAFKA_BROKER="temporal-redpanda.internal:9092" \
  MEMGRAPH_URI="bolt://temporal-memgraph.internal:7687"

# ---------------------------------------------------------------------------
# 6. Ring Hunter
# ---------------------------------------------------------------------------
create_and_deploy \
  "temporal-ring-hunter" \
  "deploy/configs/ring-hunter.toml" \
  "" 0

fly secrets set \
  --app temporal-ring-hunter \
  REDIS_URL="$REDIS_URL"

# OPENAI_API_KEY must be set by the user
if [[ -n "${OPENAI_API_KEY:-}" ]]; then
  fly secrets set --app temporal-ring-hunter OPENAI_API_KEY="$OPENAI_API_KEY"
else
  warn "OPENAI_API_KEY not set. Run: fly secrets set --app temporal-ring-hunter OPENAI_API_KEY=sk-..."
fi

# ---------------------------------------------------------------------------
# 7. Metrics Server
# ---------------------------------------------------------------------------
create_and_deploy \
  "temporal-metrics" \
  "deploy/configs/metrics.toml" \
  "" 0

fly secrets set \
  --app temporal-metrics \
  REDIS_URL="$REDIS_URL"

# ---------------------------------------------------------------------------
# Done — print connection strings for Vercel env vars
# ---------------------------------------------------------------------------
echo ""
echo -e "${GREEN}═══════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  TemporalEngine deployed to Fly.io${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════${NC}"
echo ""
echo "Set these in your Vercel dashboard (Settings → Environment Variables):"
echo ""
echo "  REDIS_URL      = $REDIS_URL"
if [[ -n "$MEMGRAPH_IP" ]]; then
  echo "  MEMGRAPH_URI   = bolt://${MEMGRAPH_IP}:7687"
else
  echo "  MEMGRAPH_URI   = bolt://temporal-memgraph.fly.dev:7687  (verify IP: fly ips list --app temporal-memgraph)"
fi
echo ""
echo "Service URLs:"
echo "  Flink UI   → https://temporal-flink.fly.dev"
echo "  MinIO      → https://temporal-minio.fly.dev"
echo "  Metrics    → https://temporal-metrics.fly.dev"
echo ""
echo "Run producer locally against Fly Redpanda:"
echo "  KAFKA_BROKER=temporal-redpanda.fly.dev:19092 python producer.py"
echo ""
