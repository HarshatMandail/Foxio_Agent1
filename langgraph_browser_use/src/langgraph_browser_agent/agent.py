# agent.py
from .state import AgentState
from .models import Agent1Output
from .graph import create_agent1_graph


async def run_agent1(url: str, user_query: str) -> Agent1Output:
    """
    Main entry point for Agent 1.

    Args:
        url: The platform URL to analyze (e.g., Salesforce login page).
        user_query: The user's question (e.g., "How do I create a new contract?")

    Returns:
        Agent1Output: Full platform analysis with multi-page context for video generation.
    """
    graph = create_agent1_graph()

    initial_state: AgentState = {
        "url": url,
        "user_query": user_query,
        "page_captures": None,
        "structured_output": None,
    }

    final_state = await graph.ainvoke(initial_state)
    return final_state["structured_output"]
