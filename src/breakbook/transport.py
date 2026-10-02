"""MCP transport shared by the scripted and SDK adapters."""

import json
import sys
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from .models import Limits


def server_arguments(case, variant, limits: Limits, fault, ledger: Path):
    args = [
        "-m",
        "breakbook.mcp_server",
        "--case",
        case,
        "--variant",
        variant,
        "--ledger",
        str(ledger),
        "--limits",
        limits.model_dump_json(),
    ]
    if not fault:
        args.append("--no-fault")
    return args


def parse_tool_reply(reply):
    if reply.isError:
        raise RuntimeError("MCP tool invocation failed at the protocol boundary")
    if reply.structuredContent is not None:
        return reply.structuredContent
    text = "".join(item.text for item in reply.content if item.type == "text")
    return json.loads(text)


@asynccontextmanager
async def mcp_call(case, variant, limits, fault, ledger):
    params = StdioServerParameters(
        command=sys.executable,
        args=server_arguments(case, variant, limits, fault, ledger),
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(
            read, write, read_timeout_seconds=timedelta(seconds=max(5, limits.watchdog * 2))
        ) as session:
            await session.initialize()

            async def call(name, arguments):
                reply = await session.call_tool(
                    name,
                    arguments,
                    read_timeout_seconds=timedelta(seconds=max(5, limits.watchdog * 2)),
                )
                return parse_tool_reply(reply)

            yield call
