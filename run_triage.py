"""
Batch Execution Runner for Support Concierge Ticket Triage System.
Loads all 18 sample tickets from sample_tickets.json, processes them through
the LangGraph pipeline, persists decision records into SQLite, and exports results.json.
"""

import json
import logging
import time
from typing import List, Dict, Any

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from schemas import Ticket
from graph import run_triage_graph
import db

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
console = Console()


def run_batch_triage(
    tickets_file: str = "sample_tickets.json",
    db_path: str = "triage_audit.db",
    output_file: str = "results.json"
):
    """Run batch triage over all tickets in tickets_file."""
    console.print(f"[bold cyan]Starting Support Concierge Triage System...[/bold cyan]")
    console.print(f"Reading tickets from [bold yellow]{tickets_file}[/bold yellow]...")

    with open(tickets_file, "r", encoding="utf-8") as f:
        raw_tickets = json.load(f)

    # Initialize DB
    db.init_db(db_path)

    results: List[Dict[str, Any]] = []
    
    summary_table = Table(title="Batch Ticket Triage Execution Results", show_lines=True)
    summary_table.add_column("Ticket ID", style="cyan bold")
    summary_table.add_column("Category", style="green")
    summary_table.add_column("Urgency", style="yellow")
    summary_table.add_column("Action", style="bold blue")
    summary_table.add_column("Confidence", style="magenta")
    summary_table.add_column("Guardrail Override", style="bold red")

    start_time = time.time()

    for idx, item in enumerate(raw_tickets, 1):
        ticket = Ticket.model_validate(item)
        console.print(f"Processing ({idx}/{len(raw_tickets)}): [bold cyan]{ticket.id}[/bold cyan] - '{ticket.subject}'")

        # Execute LangGraph Triage Pipeline
        state = run_triage_graph(ticket)

        # Persist full decision audit record into SQLite
        db.insert_audit_record(state, db_path=db_path)

        extraction = state["extraction"]
        routing = state["routing"]
        response = state["response"]

        # Collect formatted JSON record for results.json
        record_export = {
            "ticket_id": ticket.id,
            "received_at": ticket.received_at,
            "from_name": ticket.from_name,
            "from_email": ticket.from_email,
            "subject": ticket.subject,
            "body": ticket.body,
            "extraction": extraction.model_dump(),
            "routing": routing.model_dump(),
            "response": response.model_dump(),
            "error_state": state.get("error_state"),
        }
        results.append(record_export)

        override_str = "[bold red]YES[/bold red]" if routing.guardrail_overridden else "[dim]No[/dim]"
        summary_table.add_row(
            ticket.id,
            extraction.category,
            extraction.urgency,
            routing.action,
            f"{routing.confidence_score*100:.1f}%",
            override_str
        )

    elapsed = time.time() - start_time

    # Save to results.json
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    console.print("\n")
    console.print(summary_table)
    console.print(Panel(
        f"[bold green]Batch Processing Completed Successfully![/bold green]\n"
        f"- Total Tickets Processed: {len(raw_tickets)}\n"
        f"- Execution Time: {elapsed:.2f} seconds\n"
        f"- SQLite Audit Trail Persisted: [bold yellow]{db_path}[/bold yellow]\n"
        f"- Formatted Results Exported: [bold yellow]{output_file}[/bold yellow]",
        title="Execution Summary"
    ))


if __name__ == "__main__":
    run_batch_triage()
