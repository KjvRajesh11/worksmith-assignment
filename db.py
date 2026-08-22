"""
Database Module for Support Concierge Ticket Triage System.
Manages SQLite storage for decision audit logs, human review workflows, and metrics.
"""

import json
import sqlite3
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

DEFAULT_DB_PATH = "triage_audit.db"


def get_connection(db_path: str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Connect to SQLite database with ROW factory."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str = DEFAULT_DB_PATH):
    """Initialize SQLite table for audit trail logging."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS triage_audit_log (
                ticket_id TEXT PRIMARY KEY,
                received_at TEXT NOT NULL,
                from_name TEXT NOT NULL,
                from_email TEXT NOT NULL,
                subject TEXT NOT NULL,
                body TEXT NOT NULL,
                
                category TEXT NOT NULL,
                urgency TEXT NOT NULL,
                sentiment TEXT NOT NULL,
                product_area TEXT,
                contains_financial_risk INTEGER NOT NULL,
                contains_security_risk INTEGER NOT NULL,
                contains_gdpr_deletion INTEGER NOT NULL,
                contains_legal_risk INTEGER NOT NULL,
                extraction_reasoning TEXT NOT NULL,
                
                action TEXT NOT NULL,
                confidence_score REAL NOT NULL,
                routing_reasoning TEXT NOT NULL,
                guardrail_overridden INTEGER NOT NULL,
                original_action TEXT,
                
                response_draft TEXT NOT NULL,
                internal_summary TEXT NOT NULL,
                error_state TEXT,
                
                review_status TEXT NOT NULL DEFAULT 'PENDING',
                edited_response TEXT,
                reviewer_notes TEXT,
                
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        conn.commit()


def insert_audit_record(state: Dict[str, Any], db_path: str = DEFAULT_DB_PATH):
    """Insert or update a complete triage decision state in SQLite."""
    init_db(db_path)
    ticket = state["ticket"]
    extraction = state["extraction"]
    routing = state["routing"]
    response = state["response"]
    error_state = state.get("error_state")
    
    # Determine initial review status
    if routing.action == "auto_resolve":
        review_status = "COMPLETED"
    else:
        review_status = "PENDING"

    now_iso = datetime.now(timezone.utc).isoformat()

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO triage_audit_log (
                ticket_id, received_at, from_name, from_email, subject, body,
                category, urgency, sentiment, product_area,
                contains_financial_risk, contains_security_risk, contains_gdpr_deletion, contains_legal_risk,
                extraction_reasoning,
                action, confidence_score, routing_reasoning, guardrail_overridden, original_action,
                response_draft, internal_summary, error_state,
                review_status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ticket_id) DO UPDATE SET
                action=excluded.action,
                confidence_score=excluded.confidence_score,
                routing_reasoning=excluded.routing_reasoning,
                response_draft=excluded.response_draft,
                internal_summary=excluded.internal_summary,
                updated_at=excluded.updated_at
        """, (
            ticket.id,
            ticket.received_at,
            ticket.from_name,
            ticket.from_email,
            ticket.subject,
            ticket.body,
            extraction.category,
            extraction.urgency,
            extraction.sentiment,
            extraction.product_area,
            1 if extraction.contains_financial_risk else 0,
            1 if extraction.contains_security_risk else 0,
            1 if extraction.contains_gdpr_deletion else 0,
            1 if extraction.contains_legal_risk else 0,
            extraction.extraction_reasoning,
            routing.action,
            routing.confidence_score,
            routing.routing_reasoning,
            1 if routing.guardrail_overridden else 0,
            routing.original_action,
            response.response_draft,
            response.internal_summary,
            error_state,
            review_status,
            now_iso,
            now_iso
        ))
        conn.commit()


def get_audit_record(ticket_id: str, db_path: str = DEFAULT_DB_PATH) -> Optional[Dict[str, Any]]:
    """Fetch single audit log record by ticket ID."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM triage_audit_log WHERE ticket_id = ?", (ticket_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def list_tickets(
    action: Optional[str] = None,
    review_status: Optional[str] = None,
    db_path: str = DEFAULT_DB_PATH
) -> List[Dict[str, Any]]:
    """List tickets filtered by routing action or human review status."""
    init_db(db_path)
    query = "SELECT * FROM triage_audit_log WHERE 1=1"
    params = []
    
    if action:
        query += " AND action = ?"
        params.append(action)
    if review_status:
        query += " AND review_status = ?"
        params.append(review_status)
        
    query += " ORDER BY ticket_id ASC"
    
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]


def update_review_status(
    ticket_id: str,
    review_status: str,
    edited_response: Optional[str] = None,
    reviewer_notes: Optional[str] = None,
    db_path: str = DEFAULT_DB_PATH
) -> bool:
    """Update human review status (APPROVED, EDITED, REJECTED) in database."""
    now_iso = datetime.now(timezone.utc).isoformat()
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE triage_audit_log
            SET review_status = ?,
                edited_response = COALESCE(?, edited_response),
                reviewer_notes = COALESCE(?, reviewer_notes),
                updated_at = ?
            WHERE ticket_id = ?
        """, (review_status, edited_response, reviewer_notes, now_iso, ticket_id))
        conn.commit()
        return cursor.rowcount > 0


def get_summary_stats(db_path: str = DEFAULT_DB_PATH) -> Dict[str, Any]:
    """Calculate summary statistics for dashboard or CLI review."""
    init_db(db_path)
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM triage_audit_log")
        total = cursor.fetchone()[0]
        
        cursor.execute("SELECT action, COUNT(*) FROM triage_audit_log GROUP BY action")
        actions = dict(cursor.fetchall())
        
        cursor.execute("SELECT COUNT(*) FROM triage_audit_log WHERE guardrail_overridden = 1")
        guardrail_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT review_status, COUNT(*) FROM triage_audit_log GROUP BY review_status")
        review_statuses = dict(cursor.fetchall())
        
        return {
            "total_tickets": total,
            "actions": actions,
            "guardrail_overrides": guardrail_count,
            "review_statuses": review_statuses
        }
