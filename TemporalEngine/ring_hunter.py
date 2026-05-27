import os
import time
import redis
from neo4j import GraphDatabase

# --- 1. Project Config (Environment Priority) ---
URI            = os.getenv("MEMGRAPH_URI",  "bolt://localhost:7687")
AUTH           = (os.getenv("MEMGRAPH_USER", ""), os.getenv("MEMGRAPH_PASSWORD", ""))
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "30"))
REDIS_HOST     = os.getenv("REDIS_HOST", "localhost")


class RingHunter:
    """The Autonomous Fraud Cluster Identification Engine."""

    def __init__(self):
        self.driver = GraphDatabase.driver(URI, auth=AUTH)
        self.r = redis.Redis(host=REDIS_HOST, port=6379, db=0)

    def close(self):
        self.driver.close()

    def find_fraud_rings(self):
        """Scans Memgraph for suspicious user clusters using Community Detection."""
        with self.driver.session() as session:
            # 1. Run Weakly Connected Components (WCC) to identify clusters of Users and Merchants
            print("Scanning for autonomous fraud rings...")

            # WCC helps find disconnected subgraphs (potential rings)
            cypher_wcc = """
            CALL wcc.get() YIELD node, component_id
            WITH component_id, collect(node) as cluster
            WHERE size(cluster) > 3  -- Only clusters larger than 3 entities
            UNWIND cluster as member
            MATCH (member)
            SET member.fraud_ring_id = component_id
            RETURN component_id, size(cluster) as ring_size
            """

            results = session.run(cypher_wcc)
            count = 0
            for record in results:
                count += 1
                ring_id   = record['component_id']
                ring_size = record['ring_size']
                print(f"IDENTIFIED: Ring {ring_id} (Size: {ring_size})")

                # Prometheus counter
                self.r.incr("metrics:fraud_rings_detected_total")

                # Autonomous Agentic Trigger
                from investigator_agent import app
                print(f"TRIGGERING: Autonomous Agent Investigation for Ring {ring_id}...")
                try:
                    representative_user = f"user_{ring_id}"
                    app.invoke({
                        "user_id":           representative_user,
                        "transaction_amount": 1000.0,
                        "governance_status": "INVESTIGATE",
                    })
                    self.r.incr("metrics:agent_investigations_total")
                except Exception as e:
                    print(f"AGENT ERROR: Failed to invoke investigator for ring {ring_id}: {e}")

            if count == 0:
                print("No suspect clusters identified in the current graph.")
            else:
                print(f"Targeted {count} autonomous rings for investigation.")

    def continuous_hunt(self):
        """Infinite loop for autonomous monitoring."""
        print("Ring Hunter Mission: ACTIVE.")
        try:
            while True:
                self.find_fraud_rings()
                time.sleep(CHECK_INTERVAL)
        except KeyboardInterrupt:
            print("Ring Hunter Mission: ABORTED.")
        finally:
            self.close()

if __name__ == "__main__":
    hunter = RingHunter()
    hunter.continuous_hunt()
