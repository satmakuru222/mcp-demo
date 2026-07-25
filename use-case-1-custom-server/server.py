"""MCP server exposing simple internal-tooling examples over stdio."""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from mcp.server.fastmcp import FastMCP

BASE_DIR = Path(__file__).parent
DEPLOYMENTS_FILE = BASE_DIR / "data" / "deployments.json"
KNOWLEDGE_BASE_DIR = BASE_DIR / "data" / "knowledge_base"
# MCP_DEMO_TICKETS_FILE exists for test isolation (subprocess-based integration
# tests), not as a real deployment configuration knob.
TICKETS_FILE = Path(os.environ.get("MCP_DEMO_TICKETS_FILE", BASE_DIR / "tickets.json"))

mcp = FastMCP("enterprise-tools-demo")


def _load_deployments() -> dict:
    with open(DEPLOYMENTS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_tickets() -> list:
    if not TICKETS_FILE.exists():
        return []
    with open(TICKETS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_tickets(tickets: list) -> None:
    with open(TICKETS_FILE, "w", encoding="utf-8") as f:
        json.dump(tickets, f, indent=2)


@mcp.tool()
def get_deployment_status(service: str) -> dict:
    """Get the current deployment status for an internal service.

    Args:
        service: The service name, e.g. "checkout-api".
    """
    deployments = _load_deployments()
    if service not in deployments:
        raise ValueError(
            f"Unknown service: {service}. Known services: {', '.join(sorted(deployments))}"
        )
    return {"service": service, **deployments[service]}


@mcp.tool()
def search_knowledge_base(query: str) -> list[dict]:
    """Search the internal knowledge base for documents matching a query.

    Args:
        query: A keyword or phrase to search for.
    """
    if not query.strip():
        raise ValueError("query must not be empty")

    matches = []
    needle = query.lower()
    for doc_path in sorted(KNOWLEDGE_BASE_DIR.glob("*.md")):
        text = doc_path.read_text(encoding="utf-8")
        if needle in text.lower():
            idx = text.lower().index(needle)
            start = max(0, idx - 80)
            end = min(len(text), idx + 80)
            snippet = text[start:end].replace("\n", " ").strip()
            matches.append({"file": doc_path.name, "snippet": snippet})
    return matches


@mcp.tool()
def create_support_ticket(title: str, description: str) -> dict:
    """File an internal support ticket.

    Args:
        title: Short summary of the issue.
        description: Full details of the issue.
    """
    if not title.strip():
        raise ValueError("title must not be empty")

    tickets = _load_tickets()
    ticket = {
        "id": len(tickets) + 1,
        "title": title,
        "description": description,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "open",
    }
    tickets.append(ticket)
    _save_tickets(tickets)
    return ticket


if __name__ == "__main__":
    mcp.run()
