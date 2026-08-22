"""
Graph Module for Support Concierge Ticket Triage System.
Builds the LangGraph state machine orchestrating Extractor -> Router -> ResponseGenerator
with strict exception handling and safety degradation.
"""

import logging
from typing import Optional, TypedDict

from langgraph.graph import StateGraph, END
from schemas import Ticket, ExtractionOutput, RoutingOutput, ResponseOutput
from agents import ExtractionAgent, RoutingAgent, ResponseAgent

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# TRIAGE STATE DEFINITION
# ---------------------------------------------------------------------------
class TriageState(TypedDict):
    ticket: Ticket
    extraction: Optional[ExtractionOutput]
    routing: Optional[RoutingOutput]
    response: Optional[ResponseOutput]
    error_state: Optional[str]


# Agent Instances
extractor_agent = ExtractionAgent()
router_agent = RoutingAgent()
response_agent = ResponseAgent()


# ---------------------------------------------------------------------------
# GRAPH NODES WITH EXCEPTION WRAPPERS & SAFE DEGRADATION
# ---------------------------------------------------------------------------
def extractor_node(state: TriageState) -> TriageState:
    """Extractor node function wrapped in try/except safety boundary."""
    ticket = state["ticket"]
    try:
        extraction = extractor_agent.extract(ticket)
        state["extraction"] = extraction
    except Exception as e:
        error_msg = f"ExtractionAgent Exception: {str(e)}"
        logger.error(f"[{ticket.id}] {error_msg}")
        state["error_state"] = error_msg
        
        # Fallback safe extraction
        state["extraction"] = ExtractionOutput(
            category="other",
            urgency="high",
            sentiment="unknown",
            product_area="unknown",
            contains_financial_risk=True,  # Err on side of caution
            contains_security_risk=False,
            contains_gdpr_deletion=False,
            contains_legal_risk=False,
            extraction_reasoning=f"Pipeline exception during extraction: {e}"
        )
    return state


def router_node(state: TriageState) -> TriageState:
    """Router node function wrapped in try/except safety boundary."""
    ticket = state["ticket"]
    extraction = state["extraction"]
    
    # If prior node errored out, immediately force safety escalation
    if state.get("error_state"):
        state["routing"] = RoutingOutput(
            action="escalate",
            confidence_score=0.0,
            routing_reasoning=f"Escalated due to prior node error: {state['error_state']}",
            guardrail_overridden=True,
            original_action="unknown"
        )
        return state
        
    try:
        routing = router_agent.route(extraction, ticket)
        state["routing"] = routing
    except Exception as e:
        error_msg = f"RoutingAgent Exception: {str(e)}"
        logger.error(f"[{ticket.id}] {error_msg}")
        state["error_state"] = error_msg
        
        # Fallback safe routing
        state["routing"] = RoutingOutput(
            action="escalate",
            confidence_score=0.0,
            routing_reasoning=f"Graceful safety escalation triggered by routing failure: {e}",
            guardrail_overridden=True,
            original_action="failed"
        )
    return state


def response_generator_node(state: TriageState) -> TriageState:
    """Response Generator node function wrapped in try/except safety boundary."""
    ticket = state["ticket"]
    extraction = state["extraction"]
    routing = state["routing"]
    
    try:
        response = response_agent.generate(ticket, extraction, routing)
        state["response"] = response
    except Exception as e:
        error_msg = f"ResponseAgent Exception: {str(e)}"
        logger.error(f"[{ticket.id}] {error_msg}")
        state["error_state"] = error_msg
        
        # Fallback safe response
        state["response"] = ResponseOutput(
            response_draft="[SYSTEM ESCALATION - PROCESSING FAILURE] Ticket failed automated processing and has been routed to a human agent.",
            internal_summary=f"CRITICAL: Ticket {ticket.id} encountered an exception during response generation: {e}"
        )
    return state


# ---------------------------------------------------------------------------
# LANGGRAPH BUILD & COMPILE
# ---------------------------------------------------------------------------
def build_triage_graph():
    """Build and return compiled LangGraph state machine."""
    workflow = StateGraph(TriageState)
    
    # Add Nodes
    workflow.add_node("extractor", extractor_node)
    workflow.add_node("router", router_node)
    workflow.add_node("response_generator", response_generator_node)
    
    # Define Sequential Edges
    workflow.set_entry_point("extractor")
    workflow.add_edge("extractor", "router")
    workflow.add_edge("router", "response_generator")
    workflow.add_edge("response_generator", END)
    
    return workflow.compile()


# Compiled Graph Singleton
triage_graph = build_triage_graph()


def run_triage_graph(ticket: Ticket) -> TriageState:
    """
    Main invocation entry point for orchestrating a single ticket through the triage graph.
    """
    initial_state: TriageState = {
        "ticket": ticket,
        "extraction": None,
        "routing": None,
        "response": None,
        "error_state": None,
    }
    
    return triage_graph.invoke(initial_state)
