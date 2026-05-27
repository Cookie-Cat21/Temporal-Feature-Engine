import operator
import os
import json
import redis
import time
from typing import Annotated, List, TypedDict

from langchain_core.messages import BaseMessage, HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from neo4j import GraphDatabase

# --- 1. Project Config (Environment Priority) ---
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
r = redis.Redis(host=REDIS_HOST, port=6379, db=0)

def report_step(node, message, status="running"):
    """Emits a reasoning step to Redis for the Dashboard."""
    step = {
        "id": os.urandom(4).hex(),
        "node": node,
        "message": message,
        "status": status,
        "ts": time.time()
    }
    r.lpush("agent:reasoning:steps", json.dumps(step))
    r.ltrim("agent:reasoning:steps", 0, 9) # Keep only last 10 steps
    print(f"[AGENT] {node}: {message} ({status})")

# --- 2. Agent State ---
class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], operator.add]
    user_id: str
    transaction_amount: float
    context: str
    decision: str
    governance_status: str
    violations: List[str]

# --- 2. Tooling (Graph Queries) ---
URI = os.getenv("MEMGRAPH_URI", "bolt://localhost:7687")
AUTH = (os.getenv("MEMGRAPH_USER", ""), os.getenv("MEMGRAPH_PASSWORD", ""))

def query_memgraph(cypher):
    try:
        with GraphDatabase.driver(URI, auth=AUTH) as driver:
            with driver.session() as session:
                result = session.run(cypher)
                return [record.data() for record in result]
    except Exception as e:
        return f"Error querying graph: {e}"

# --- 3. Agent Nodes ---
model = ChatOpenAI(model="gpt-4o")

def gather_context(state: AgentState):
    """Query Memgraph for recent history."""
    uid = state['user_id']
    report_step("Gather Context", f"Querying Memgraph for transaction history of {uid}...")
    cypher = f"MATCH (u:User {{user_id: '{uid}'}})-[r:TRANSACTED_WITH]->(m) RETURN m.merchant_name as merchant, r.amount as amount LIMIT 5"
    history = query_memgraph(cypher)
    report_step("Gather Context", f"Success. Found {len(history)} recent records.", status="completed")
    return {"context": f"Recent Transactions: {history}"}

def network_analysis(state: AgentState):
    """Find shared devices or IPs to detect 'Rings'."""
    uid = state['user_id']
    report_step("Network Analysis", "Scanning for shared IP/Device rings...")
    cypher = f"""
    MATCH (u:User {{user_id: '{uid}'}})-[:LOGGED_IN_FROM]->(ip:IP)<-[:LOGGED_IN_FROM]-(other:User)
    RETURN other.user_id as shared_ip_user
    """
    shared = query_memgraph(cypher)
    report_step("Network Analysis", f"Scan complete. Found {len(shared)} linked accounts.", status="completed")
    return {"context": state['context'] + f" | Shared Intelligence: {shared}"}

def reason_and_decide(state: AgentState):
    """The final decision node."""
    report_step("Reason & Decide", "Performing final risk synthesis and decision logic...")
    prompt = f"""
    Investigate this transaction:
    User: {state['user_id']}
    Amount: ${state['transaction_amount']}
    Context: {state['context']}

    Final decision must be one of: [ALLOW, BLOCK, INVESTIGATE].
    Provide a brief reason.
    """
    response = model.invoke([HumanMessage(content=prompt)])
    content = response.content

    decision = "INVESTIGATE"
    if "ALLOW" in content:
        decision = "ALLOW"
    elif "BLOCK" in content:
        decision = "BLOCK"

    report_step("Reason & Decide", f"FINAL DECISION: {decision} - Investigation conclude.", status="completed")
    return {"decision": decision, "messages": [response]}

def security_audit(state: AgentState):
    """Analyze contract violations for malicious intent."""
    violations = state.get("violations", [])
    report_step("Security Audit", f"Analyzing {len(violations)} contract violations for user {state['user_id']}...")
    prompt = f"""
    The Data Sovereignty Guard has detected the following contract violations:
    {violations}

    User: {state['user_id']}

    Is this a simple schema drift or a potential data exfiltration attempt?
    Provide a risk score (0-10) and a recommendation.
    """
    response = model.invoke([HumanMessage(content=prompt)])
    report_step("Security Audit", "Audit complete. Synthesizing risk recommendation.", status="completed")
    return {"context": state['context'] + f" | Security Audit: {response.content}", "messages": [response]}

# --- 4. Define the Graph ---
workflow = StateGraph(AgentState)

workflow.add_node("gather_context", gather_context)
workflow.add_node("network_analysis", network_analysis)
workflow.add_node("security_audit", security_audit)
workflow.add_node("reason_and_decide", reason_and_decide)

def route_investigation(state: AgentState):
    if state.get("governance_status") == "VIOLATION":
        return "security_audit"
    return "network_analysis"

workflow.set_entry_point("gather_context")
workflow.add_conditional_edges(
    "gather_context",
    route_investigation,
    {
        "security_audit": "security_audit",
        "network_analysis": "network_analysis"
    }
)
workflow.add_edge("security_audit", "reason_and_decide")
workflow.add_edge("network_analysis", "reason_and_decide")
workflow.add_edge("reason_and_decide", END)

# Compile
app = workflow.compile()

if __name__ == "__main__":
    print("Agentic Investigator Graph Compiled.")
    # Example invocation
    # app.invoke({"user_id": "user_1", "transaction_amount": 150.0})
