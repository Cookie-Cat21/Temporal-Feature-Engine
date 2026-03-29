import os
import operator
from typing import Annotated, List, TypedDict, Union
from typing_extensions import TypedDict
from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, HumanMessage
from langgraph.graph import StateGraph, END
from neo4j import GraphDatabase

# --- 1. Agent State ---
class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], operator.add]
    user_id: str
    transaction_amount: float
    context: str
    decision: str

# --- 2. Tooling (Graph Queries) ---
URI = "bolt://localhost:7687"
AUTH = ("", "")

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
    cypher = f"MATCH (u:User {{user_id: '{uid}'}})-[r:TRANSACTED_WITH]->(m) RETURN m.merchant_name as merchant, r.amount as amount LIMIT 5"
    history = query_memgraph(cypher)
    return {"context": f"Recent Transactions: {history}"}

def network_analysis(state: AgentState):
    """Find shared devices or IPs to detect 'Rings'."""
    uid = state['user_id']
    cypher = f"""
    MATCH (u:User {{user_id: '{uid}'}})-[:LOGGED_IN_FROM]->(ip:IP)<-[:LOGGED_IN_FROM]-(other:User)
    RETURN other.user_id as shared_ip_user
    """
    shared = query_memgraph(cypher)
    return {"context": state['context'] + f" | Shared Intelligence: {shared}"}

def reason_and_decide(state: AgentState):
    """The final decision node."""
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
    if "ALLOW" in content: decision = "ALLOW"
    elif "BLOCK" in content: decision = "BLOCK"
    
    return {"decision": decision, "messages": [response]}

# --- 4. Define the Graph ---
workflow = StateGraph(AgentState)

workflow.add_node("gather_context", gather_context)
workflow.add_node("network_analysis", network_analysis)
workflow.add_node("reason_and_decide", reason_and_decide)

workflow.set_entry_point("gather_context")
workflow.add_edge("gather_context", "network_analysis")
workflow.add_edge("network_analysis", "reason_and_decide")
workflow.add_edge("reason_and_decide", END)

# Compile
app = workflow.compile()

if __name__ == "__main__":
    print("Agentic Investigator Graph Compiled.")
    # Example invocation
    # app.invoke({"user_id": "user_1", "transaction_amount": 150.0})
