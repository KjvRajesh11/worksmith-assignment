"""
Pydantic v2 Schemas for Support Concierge Ticket Triage System.
Defines data structures for tickets, extractions, routing decisions, responses, and audit records.
"""

from datetime import datetime, timezone
from typing import Literal, Optional
from pydantic import BaseModel, Field, FieldValidationInfo, field_validator


class Ticket(BaseModel):
    """Raw input ticket structure."""
    id: str = Field(..., description="Unique ticket identifier (e.g., TCK-1001)")
    received_at: str = Field(..., description="ISO 8601 timestamp of ticket receipt")
    from_name: str = Field(..., description="Sender's full name")
    from_email: str = Field(..., description="Sender's email address")
    subject: str = Field(..., description="Ticket email subject line")
    body: str = Field(..., description="Ticket body text")


class ExtractionOutput(BaseModel):
    """Structured fields extracted from ticket content by ExtractionAgent."""
    category: Literal[
        "billing",
        "bug",
        "feature_request",
        "account_security",
        "spam",
        "gdpr_deletion",
        "other",
    ] = Field(..., description="Primary category of the ticket")
    
    urgency: Literal["low", "medium", "high", "critical"] = Field(
        ..., description="Assessed urgency level"
    )
    
    sentiment: str = Field(
        ..., description="Customer sentiment (e.g., positive, neutral, frustrated, angry)"
    )
    
    product_area: Optional[str] = Field(
        default="general", description="Product area involved (e.g., billing, reporting, auth, mobile)"
    )
    
    contains_financial_risk: bool = Field(
        default=False,
        description="True if ticket involves money, refunds, double charges, overcharges, or pricing changes",
    )
    
    contains_security_risk: bool = Field(
        default=False,
        description="True if ticket involves security vulnerability, account takeover, unauthorized access, or IDOR",
    )
    
    contains_gdpr_deletion: bool = Field(
        default=False,
        description="True if ticket requests account deletion, data removal, or GDPR Article 17 rights",
    )
    
    contains_legal_risk: bool = Field(
        default=False,
        description="True if ticket mentions legal action, attorneys, regulatory complaints, or compliance threats",
    )
    
    extraction_reasoning: str = Field(
        ..., description="Detailed explanation of classification and risk flag detection"
    )


class RoutingOutput(BaseModel):
    """Routing decision produced by RoutingAgent and sanitized by guardrails."""
    action: Literal["auto_resolve", "draft_for_review", "escalate"] = Field(
        ..., description="Triage action for the ticket"
    )
    
    confidence_score: float = Field(
        ..., description="Confidence score between 0.0 and 1.0"
    )
    
    routing_reasoning: str = Field(
        ..., description="Rationale behind the routing decision"
    )
    
    guardrail_overridden: bool = Field(
        default=False,
        description="True if deterministic hard guardrail overrode LLM decision",
    )
    
    original_action: Optional[str] = Field(
        default=None,
        description="Original LLM proposed action before guardrail override",
    )

    @field_validator("confidence_score")
    @classmethod
    def validate_confidence(cls, v: float) -> float:
        if not (0.0 <= v <= 1.0):
            raise ValueError(f"Confidence score must be between 0.0 and 1.0, got {v}")
        return round(v, 4)


class ResponseOutput(BaseModel):
    """Response generation output produced by ResponseAgent."""
    response_draft: str = Field(
        ..., description="Canned or personalized email response draft for customer"
    )
    
    internal_summary: str = Field(
        ..., description="Concise briefing summary for internal human agents"
    )


class AuditRecord(BaseModel):
    """Complete persistent record of a ticket triage execution."""
    ticket_id: str
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    ticket: Ticket
    extraction: ExtractionOutput
    routing: RoutingOutput
    response: ResponseOutput
    review_status: Literal["PENDING", "APPROVED", "EDITED", "REJECTED"] = "PENDING"
    edited_response: Optional[str] = None
    reviewer_notes: Optional[str] = None
