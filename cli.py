"""
CLI Module for Support Concierge Human-in-the-Loop Ticket Triage System.
Provides an interactive command-line interface for human agents to list queued tickets,
inspect decision audit traces, and approve, edit, or reject drafted responses.
"""

import sys
from typing import Optional
import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich import print as rprint

import db

app = typer.Typer(help="Support Concierge Human-in-the-Loop Triage CLI")
console = Console()
DB_PATH = "triage_audit.db"


@app.command("list")
def list_tickets(
    action: Optional[str] = typer.Option(None, "--action", "-a", help="Filter by action (auto_resolve, draft_for_review, escalate)"),
    status: Optional[str] = typer.Option(None, "--status", "-s", help="Filter by review status (PENDING, APPROVED, EDITED, REJECTED, COMPLETED)"),
):
    """List tickets sitting in the review queues."""
    tickets = db.list_tickets(action=action, review_status=status, db_path=DB_PATH)
    if not tickets:
        console.print("[yellow]No tickets found matching the specified filters.[/yellow]")
        return

    table = Table(title="Support Concierge Triage Audit Queue", show_lines=True)
    table.add_column("ID", style="cyan bold", no_wrap=True)
    table.add_column("From", style="magenta")
    table.add_column("Subject", style="white")
    table.add_column("Category", style="green")
    table.add_column("Urgency", style="yellow")
    table.add_column("Action", style="bold blue")
    table.add_column("Guardrail?", style="red")
    table.add_column("Status", style="bold green")

    for t in tickets:
        guardrail_str = "[bold red]YES[/bold red]" if t["guardrail_overridden"] else "[dim]No[/dim]"
        status_color = "green" if t["review_status"] in ["APPROVED", "COMPLETED"] else ("yellow" if t["review_status"] == "PENDING" else "red")
        
        table.add_row(
            t["ticket_id"],
            t["from_name"],
            t["subject"][:35] + ("..." if len(t["subject"]) > 35 else ""),
            t["category"],
            t["urgency"],
            t["action"],
            guardrail_str,
            f"[{status_color}]{t['review_status']}[/{status_color}]",
        )

    console.print(table)


@app.command("show")
def show_ticket(ticket_id: str = typer.Argument(..., help="ID of ticket to inspect (e.g. TCK-1001)")):
    """Display complete audit trace and details for a ticket."""
    record = db.get_audit_record(ticket_id, db_path=DB_PATH)
    if not record:
        console.print(f"[bold red]Error:[/bold red] Ticket {ticket_id} not found in database.")
        raise typer.Exit(code=1)

    console.print(Panel(
        f"[bold cyan]TICKET ID:[/bold cyan] {record['ticket_id']}\n"
        f"[bold cyan]FROM:[/bold cyan] {record['from_name']} <{record['from_email']}>\n"
        f"[bold cyan]RECEIVED AT:[/bold cyan] {record['received_at']}\n"
        f"[bold cyan]SUBJECT:[/bold cyan] {record['subject']}\n\n"
        f"[bold white]BODY:[/bold white]\n{record['body']}",
        title=f"Ticket Content ({record['ticket_id']})",
        expand=False
    ))

    console.print(Panel(
        f"[bold green]Category:[/bold green] {record['category']}  |  [bold yellow]Urgency:[/bold yellow] {record['urgency']}  |  [bold magenta]Sentiment:[/bold magenta] {record['sentiment']}\n"
        f"[bold blue]Product Area:[/bold blue] {record['product_area']}\n"
        f"[bold red]Risk Flags:[/bold red] Financial={bool(record['contains_financial_risk'])}, Security={bool(record['contains_security_risk'])}, GDPR={bool(record['contains_gdpr_deletion'])}, Legal={bool(record['contains_legal_risk'])}\n"
        f"[bold white]Extraction Reasoning:[/bold white] {record['extraction_reasoning']}",
        title="1. Agent Extraction Analysis",
        expand=False
    ))

    guardrail_msg = "[bold red]TRIGGERED - OVERRODE LLM DECISION[/bold red]" if record['guardrail_overridden'] else "[dim]Not Triggered[/dim]"
    console.print(Panel(
        f"[bold blue]Final Action:[/bold blue] {record['action']}  |  [bold cyan]Confidence Score:[/bold cyan] {record['confidence_score']*100:.1f}%\n"
        f"[bold red]Hard Guardrail:[/bold red] {guardrail_msg}\n"
        f"[bold white]Original LLM Action:[/bold white] {record['original_action'] or 'N/A'}\n"
        f"[bold white]Routing Reasoning:[/bold white] {record['routing_reasoning']}",
        title="2. Routing Decision & Safety Guardrails",
        expand=False
    ))

    current_draft = record['edited_response'] or record['response_draft']
    console.print(Panel(
        f"[bold green]Review Status:[/bold green] {record['review_status']}\n\n"
        f"[bold white]Customer Response Draft:[/bold white]\n{current_draft}\n\n"
        f"[bold white]Internal Agent Briefing Summary:[/bold white]\n{record['internal_summary']}\n\n"
        f"[bold white]Reviewer Notes:[/bold white] {record['reviewer_notes'] or 'None'}",
        title="3. Drafted Response & Review Status",
        expand=False
    ))


@app.command("approve")
def approve_ticket(
    ticket_id: str = typer.Argument(..., help="ID of ticket to approve"),
    notes: Optional[str] = typer.Option(None, "--notes", "-n", help="Optional reviewer notes")
):
    """Approve a drafted response for sending."""
    record = db.get_audit_record(ticket_id, db_path=DB_PATH)
    if not record:
        console.print(f"[bold red]Error:[/bold red] Ticket {ticket_id} not found.")
        raise typer.Exit(code=1)

    updated = db.update_review_status(
        ticket_id=ticket_id,
        review_status="APPROVED",
        reviewer_notes=notes or "Approved via CLI review interface",
        db_path=DB_PATH
    )
    if updated:
        console.print(f"[bold green]Successfully approved ticket {ticket_id}![/bold green]")
    else:
        console.print(f"[bold red]Failed to update ticket {ticket_id}.[/bold red]")


@app.command("edit")
def edit_ticket(ticket_id: str = typer.Argument(..., help="ID of ticket to edit response")):
    """Interactively edit the response draft for a ticket."""
    record = db.get_audit_record(ticket_id, db_path=DB_PATH)
    if not record:
        console.print(f"[bold red]Error:[/bold red] Ticket {ticket_id} not found.")
        raise typer.Exit(code=1)

    console.print(f"\n[bold cyan]Current Response Draft for {ticket_id}:[/bold cyan]")
    current_draft = record['edited_response'] or record['response_draft']
    console.print(Panel(current_draft, title="Current Draft"))

    new_draft = Prompt.ask("\n[bold yellow]Enter new edited response draft[/bold yellow]", default=current_draft)
    notes = Prompt.ask("[bold yellow]Enter reviewer notes[/bold yellow]", default="Edited by human reviewer via CLI")

    updated = db.update_review_status(
        ticket_id=ticket_id,
        review_status="EDITED",
        edited_response=new_draft,
        reviewer_notes=notes,
        db_path=DB_PATH
    )
    if updated:
        console.print(f"[bold green]Successfully updated response draft for {ticket_id} (Status: EDITED)![/bold green]")


@app.command("reject")
def reject_ticket(
    ticket_id: str = typer.Argument(..., help="ID of ticket to reject"),
    notes: Optional[str] = typer.Option(None, "--notes", "-n", help="Reason for rejection")
):
    """Reject a drafted response and queue for manual handling."""
    record = db.get_audit_record(ticket_id, db_path=DB_PATH)
    if not record:
        console.print(f"[bold red]Error:[/bold red] Ticket {ticket_id} not found.")
        raise typer.Exit(code=1)

    reason = notes or Prompt.ask("[bold yellow]Enter rejection reason/notes[/bold yellow]", default="Rejected by human agent")
    updated = db.update_review_status(
        ticket_id=ticket_id,
        review_status="REJECTED",
        reviewer_notes=reason,
        db_path=DB_PATH
    )
    if updated:
        console.print(f"[bold red]Ticket {ticket_id} marked as REJECTED.[/bold red]")


@app.command("stats")
def show_stats():
    """Display overall triage analytics, safety guardrail metrics, and review status."""
    stats = db.get_summary_stats(db_path=DB_PATH)
    
    console.print(Panel(
        f"[bold white]Total Ingested Tickets:[/bold white] {stats['total_tickets']}\n"
        f"[bold red]Hard Guardrail Overrides:[/bold red] {stats['guardrail_overrides']}\n\n"
        f"[bold cyan]Action Breakdown:[/bold cyan]\n"
        f"  - Auto-Resolve: {stats['actions'].get('auto_resolve', 0)}\n"
        f"  - Draft for Review: {stats['actions'].get('draft_for_review', 0)}\n"
        f"  - Escalate: {stats['actions'].get('escalate', 0)}\n\n"
        f"[bold green]Human Review Status Breakdown:[/bold green]\n"
        f"  - Pending: {stats['review_statuses'].get('PENDING', 0)}\n"
        f"  - Approved: {stats['review_statuses'].get('APPROVED', 0)}\n"
        f"  - Edited: {stats['review_statuses'].get('EDITED', 0)}\n"
        f"  - Rejected: {stats['review_statuses'].get('REJECTED', 0)}\n"
        f"  - Auto-Completed: {stats['review_statuses'].get('COMPLETED', 0)}",
        title="Support Concierge Triage System Analytics",
        expand=False
    ))


if __name__ == "__main__":
    app()
