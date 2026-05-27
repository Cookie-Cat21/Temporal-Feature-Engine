from neo4j import GraphDatabase

# --- 1. Memgraph Config ---
URI = "bolt://localhost:7687"
AUTH = ("", "") # Default for local Memgraph

def initialize_graph():
    """Setup the Fraud Ring Schema in Memgraph."""
    print(f"Connecting to Memgraph at {URI}...")

    with GraphDatabase.driver(URI, auth=AUTH) as driver:
        with driver.session() as session:
            # 1. Clear existing Data (Be careful in Prod!)
            print("Clearing existing graph...")
            session.run("MATCH (n) DETACH DELETE n")

            # 2. Constraints / Indices (Optional but good)
            print("Creating indices...")
            session.run("CREATE INDEX ON :User(user_id)")
            session.run("CREATE INDEX ON :Device(device_id)")
            session.run("CREATE INDEX ON :IP(ip_address)")
            session.run("CREATE INDEX ON :Merchant(merchant_name)")

            # 3. Define the Schema Logic
            print("✓ Graph Schema Ready.")

if __name__ == "__main__":
    initialize_graph()
