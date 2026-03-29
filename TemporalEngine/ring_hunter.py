import os
import time
from neo4j import GraphDatabase

# --- 1. Project Config (Environment Priority) ---
URI = os.getenv("MEMGRAPH_URI", "bolt://localhost:7687")
AUTH = (os.getenv("MEMGRAPH_USER", ""), os.getenv("MEMGRAPH_PASSWORD", ""))
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "30")) # Scan the graph every 30 seconds

class RingHunter:
    """The Autonomous Fraud Cluster Identification Engine."""
    
    def __init__(self):
        self.driver = GraphDatabase.driver(URI, auth=AUTH)

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
                print(f"IDENTIFIED: Ring {record['component_id']} (Size: {record['ring_size']})")
            
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
