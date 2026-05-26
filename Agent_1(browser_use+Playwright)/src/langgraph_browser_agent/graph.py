# graph.py — LangGraph Agent 1 Workflow with Task Completion Verification
from langgraph.graph import StateGraph, END

from .state import AgentState
from .nodes import navigate_and_crawl, analyze_and_generate_output, verify_task_completion


def create_agent1_graph():
    """
    Create the Agent 1 LangGraph workflow:
      navigate+crawl → verify_completion → analyze → output

    The verify node checks if the final expected UI element is visible
    before proceeding to analysis.
    """
    workflow = StateGraph(AgentState)

    workflow.add_node("navigate_and_crawl", navigate_and_crawl)
    workflow.add_node("verify_completion", verify_task_completion)
    workflow.add_node("analyze", analyze_and_generate_output)

    workflow.set_entry_point("navigate_and_crawl")
    workflow.add_edge("navigate_and_crawl", "verify_completion")
    workflow.add_edge("verify_completion", "analyze")
    workflow.add_edge("analyze", END)

    return workflow.compile()
