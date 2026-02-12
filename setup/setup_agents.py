"""Setup script to register all tools and agents in Elastic Agent Builder.

Reads tool and agent definitions from agent_config/ and registers them
via the Kibana API. Idempotent — safe to re-run.

Usage:
    python -m setup.setup_agents --kibana-url <URL> --api-key <KEY>
"""

import json
import argparse
import logging
from pathlib import Path

import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

CONFIG_DIR = Path(__file__).parent.parent / "agent_config"


def load_json(filename: str) -> dict:
    path = CONFIG_DIR / filename
    with open(path) as f:
        return json.load(f)


def register_tools(client: httpx.Client, tools: list[dict]):
    """Register ES|QL tools via Kibana API."""
    for tool in tools:
        tool_id = tool["toolId"]
        logger.info(f"Registering tool: {tool_id}")

        payload = {
            "toolId": tool_id,
            "name": tool["name"],
            "description": tool["description"],
            "type": tool["type"],
        }

        if "parameters" in tool:
            payload["parameters"] = tool["parameters"]
        if "query" in tool:
            payload["query"] = tool["query"]

        # Try to create; if exists, update
        resp = client.post("/api/agent_builder/tools", json=payload)

        if resp.status_code == 409:
            logger.info(f"  Tool {tool_id} exists, updating...")
            resp = client.put(f"/api/agent_builder/tools/{tool_id}", json=payload)

        if resp.status_code in (200, 201):
            logger.info(f"  ✓ Tool {tool_id} registered successfully")
        else:
            logger.error(f"  ✗ Failed to register {tool_id}: {resp.status_code} {resp.text}")


def register_agents(client: httpx.Client, agents: list[dict]):
    """Register custom agents via Kibana API."""
    for agent in agents:
        agent_id = agent["agentId"]
        logger.info(f"Registering agent: {agent_id}")

        payload = {
            "agentId": agent_id,
            "displayName": agent["displayName"],
            "displayDescription": agent["displayDescription"],
            "instructions": agent["instructions"],
            "tools": agent["tools"],
        }

        if "labels" in agent:
            payload["labels"] = agent["labels"]

        # Try to create; if exists, update
        resp = client.post("/api/agent_builder/agents", json=payload)

        if resp.status_code == 409:
            logger.info(f"  Agent {agent_id} exists, updating...")
            resp = client.put(f"/api/agent_builder/agents/{agent_id}", json=payload)

        if resp.status_code in (200, 201):
            logger.info(f"  ✓ Agent {agent_id} registered successfully")
        else:
            logger.error(f"  ✗ Failed to register {agent_id}: {resp.status_code} {resp.text}")


def verify_setup(client: httpx.Client):
    """Verify all tools and agents are registered."""
    logger.info("Verifying setup...")

    resp = client.get("/api/agent_builder/tools")
    if resp.status_code == 200:
        tools = resp.json()
        pharma_tools = [t for t in tools if t.get("toolId", "").startswith("pharma.")]
        logger.info(f"  Pharma tools registered: {len(pharma_tools)}/8")
    else:
        logger.warning(f"  Could not list tools: {resp.status_code}")

    resp = client.get("/api/agent_builder/agents")
    if resp.status_code == 200:
        agents = resp.json()
        our_agents = [a for a in agents if a.get("agentId") in ("signal_scanner", "case_investigator", "safety_reporter")]
        logger.info(f"  PharmaVigil agents registered: {len(our_agents)}/3")
    else:
        logger.warning(f"  Could not list agents: {resp.status_code}")


def main():
    parser = argparse.ArgumentParser(description="Register PharmaVigil tools and agents")
    parser.add_argument("--kibana-url", required=True, help="Kibana URL")
    parser.add_argument("--api-key", required=True, help="Kibana API key")
    args = parser.parse_args()

    client = httpx.Client(
        base_url=args.kibana_url.rstrip("/"),
        headers={
            "Authorization": f"ApiKey {args.api_key}",
            "kbn-xsrf": "true",
            "Content-Type": "application/json",
        },
        timeout=30.0,
    )

    # Load definitions
    tools_config = load_json("tools.json")
    agents_config = load_json("agents.json")

    # Register
    register_tools(client, tools_config["tools"])
    register_agents(client, agents_config["agents"])

    # Verify
    verify_setup(client)

    logger.info("Setup complete!")
    client.close()


if __name__ == "__main__":
    main()
