import json
import time
import random
from datetime import datetime
from faker import Faker
from confluent_kafka import Producer

# Configuration
KAFKA_BROKER = "localhost:19092"
TRANSACTION_TOPIC = "user_transactions"
PROFILE_TOPIC = "user_profiles"

fake = Faker()
p = Producer({'bootstrap.servers': KAFKA_BROKER})

def delivery_report(err, msg):
    if err is not None:
        print(f"Message delivery failed: {err}")
    else:
        print(f"Message delivered to {msg.topic()} [{msg.partition()}]")

def generate_transaction(user_id):
    return {
        "transaction_id": fake.uuid4(),
        "user_id": user_id,
        "amount": round(random.uniform(5.0, 500.0), 2),
        "merchant": fake.company(),
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }

def generate_profile_update(user_id):
    return {
        "user_id": user_id,
        "credit_score": random.randint(300, 850),
        "account_status": random.choice(["ACTIVE", "FLAGGED", "VIP"]),
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }

if __name__ == "__main__":
    print(f"Starting producer (Brokers: {KAFKA_BROKER})...")
    
    # Active users to simulate
    user_ids = [f"user_{i}" for i in range(1, 11)]
    
    try:
        while True:
            # 1. Randomly update a user profile (less frequent)
            if random.random() < 0.2:
                uid = random.choice(user_ids)
                profile = generate_profile_update(uid)
                p.produce(PROFILE_TOPIC, key=uid, value=json.dumps(profile), callback=delivery_report)
                print(f"Sent Profile Update: {uid}")

            # 2. Generate transactions (more frequent)
            uid = random.choice(user_ids)
            transaction = generate_transaction(uid)
            
            # Simulate LATE ARRIVAL (5% of the time, delay the event timestamp)
            if random.random() < 0.05:
                # Set timestamp to 30 seconds ago
                transaction["timestamp"] = datetime.fromisoformat(transaction["timestamp"][:-1] if transaction["timestamp"].endswith("Z") else transaction["timestamp"])
                transaction["timestamp"] = datetime.utcnow().replace(second=0).isoformat() + "Z"
                print(f"!!! GHOST TRANSACTION (Late Arrival): {uid}")

            p.produce(TRANSACTION_TOPIC, key=uid, value=json.dumps(transaction), callback=delivery_report)
            
            p.poll(0)
            time.sleep(random.uniform(0.5, 2.0))
            
    except KeyboardInterrupt:
        print("Stopping...")
    finally:
        p.flush()
