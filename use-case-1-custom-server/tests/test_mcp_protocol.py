import os
from pathlib import Path

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER_SCRIPT = Path(__file__).parent.parent / "server.py"


async def test_full_protocol_round_trip(tmp_path):
    with anyio.fail_after(10):
        fake_tickets = tmp_path / "tickets.json"
        params = StdioServerParameters(
            command="python",
            args=[str(SERVER_SCRIPT)],
            env={**os.environ, "MCP_DEMO_TICKETS_FILE": str(fake_tickets)},
        )

        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                tools = await session.list_tools()
                tool_names = {tool.name for tool in tools.tools}
                assert tool_names == {
                    "get_deployment_status",
                    "search_knowledge_base",
                    "create_support_ticket",
                }

                result = await session.call_tool(
                    "get_deployment_status", {"service": "payments-service"}
                )
                assert result.isError is not True
                assert "degraded" in result.content[0].text

                result = await session.call_tool(
                    "get_deployment_status", {"service": "does-not-exist"}
                )
                assert result.isError is True

                result = await session.call_tool(
                    "search_knowledge_base", {"query": "canary"}
                )
                assert result.isError is not True
                assert "deployment_process.md" in result.content[0].text

                result = await session.call_tool(
                    "create_support_ticket",
                    {"title": "Test ticket", "description": "created via protocol test"},
                )
                assert result.isError is not True
                assert "Test ticket" in result.content[0].text
                assert fake_tickets.exists()
