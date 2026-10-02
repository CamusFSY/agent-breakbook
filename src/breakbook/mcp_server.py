"""Expose a single local world over MCP stdio; stdout belongs to the protocol."""

import argparse
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from .catalog import CASES
from .models import Limits
from .world import World


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", choices=CASES, required=True)
    parser.add_argument("--variant", choices=["broken", "fixed"], required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--limits", required=True)
    parser.add_argument("--no-fault", action="store_true")
    args = parser.parse_args()
    world = World(
        args.case,
        args.variant,
        Limits.model_validate_json(args.limits),
        fault=not args.no_fault,
        ledger=args.ledger,
    )
    server = FastMCP("Agent Breakbook local fixture", log_level="ERROR")
    if args.case == "lost-ack":

        @server.tool()
        async def send_notification(operation_id: str, message: str) -> dict:
            """Submit a local notification. An ambiguous error does not prove it was not committed.

            Use the same operation_id for retries of the same business operation.
            This fixture does not send any real notification.
            """
            return await world.call(
                "send_notification", {"operation_id": operation_id, "message": message}
            )

        @server.tool()
        async def lookup_notification(operation_id: str) -> dict:
            """Look up the committed receipt for a business operation, if any."""
            return await world.call("lookup_notification", {"operation_id": operation_id})
    elif args.case == "hung-tool":

        @server.tool()
        async def fetch_status() -> dict:
            """Fetch build status. A tool_timeout error means status remains unknown."""
            return await world.call("fetch_status", {})
    else:

        @server.tool()
        async def read_inventory() -> dict:
            """Read local inventory. Stop on retry_limit or harness_budget errors."""
            return await world.call("read_inventory", {})

    server.run(transport="stdio")


if __name__ == "__main__":
    main()
