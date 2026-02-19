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
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def register_tools(client: httpx.Client, tools: list[dict]):
    """Register ES|QL tools via Kibana API."""
    for tool in tools:
        tool_id = tool["toolId"]
        logger.info(f"Registering tool: {tool_id}")

        # Transform parameters list to the object format the API expects
        params_obj = {}
        for p in tool.get("parameters", []):
            param_def = {
                "type": p["type"],
                "description": p.get("description", ""),
                "optional": not p.get("required", True)
            }
            if "defaultValue" in p:
                param_def["defaultValue"] = p["defaultValue"]
            params_obj[p["name"]] = param_def

        payload = {
            "id": tool_id,
            "type": "esql",
            "description": tool["description"],
            "configuration": {
                "query": tool["query"],
                "params": params_obj
            }
        }

        # Delete first to ensure a clean update (idempotent setup)
        client.delete(f"/api/agent_builder/tools/{tool_id}")
        
        # Create
        resp = client.post("/api/agent_builder/tools", json=payload)

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
            "id": agent_id,
            "name": agent["displayName"],
            "description": agent["displayDescription"],
            "avatar_color": agent.get("avatarColor", "#4ECDC4"),
            "avatar_symbol": agent.get("avatarSymbol", "🤖"),
            "configuration": {
                "instructions": agent["instructions"],
                "tools": [
                    { "tool_ids": agent["tools"] }
                ]
            }
        }

        if "labels" in agent:
            payload["labels"] = agent["labels"]

        # Delete first to ensure a clean update
        client.delete(f"/api/agent_builder/agents/{agent_id}")

        # Create
        resp = client.post("/api/agent_builder/agents", json=payload)

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
        logger.info(f"  Raw tools response type: {type(tools)}")
        if isinstance(tools, list):
            pharma_tools = []
            for t in tools:
                if isinstance(t, dict):
                    tid = t.get("id", t.get("toolId", ""))
                    if tid.startswith("pharma."):
                        pharma_tools.append(t)
                elif isinstance(t, str) and t.startswith("pharma."):
                    pharma_tools.append(t)
            logger.info(f"  Pharma tools registered: {len(pharma_tools)}/8")
        elif isinstance(tools, dict) and "tools" in tools:
            pharma_tools = [t for t in tools["tools"] if isinstance(t, dict) and t.get("id", "").startswith("pharma.")]
            logger.info(f"  Pharma tools registered: {len(pharma_tools)}/8")
        else:
            logger.info(f"  Tools response: {str(tools)[:200]}")
    else:
        logger.warning(f"  Could not list tools: {resp.status_code} {resp.text[:200]}")

    resp = client.get("/api/agent_builder/agents")
    if resp.status_code == 200:
        agents = resp.json()
        logger.info(f"  Raw agents response type: {type(agents)}")
        if isinstance(agents, list):
            our_agents = []
            for a in agents:
                if isinstance(a, dict):
                    aid = a.get("id", a.get("agentId", ""))
                    if aid in ("signal_scanner", "case_investigator", "safety_reporter"):
                        our_agents.append(a)
                elif isinstance(a, str) and a in ("signal_scanner", "case_investigator", "safety_reporter"):
                    our_agents.append(a)
            logger.info(f"  PharmaVigil agents registered: {len(our_agents)}/3")
        elif isinstance(agents, dict) and "agents" in agents:
            our_agents = [a for a in agents["agents"] if isinstance(a, dict) and a.get("id", "") in ("signal_scanner", "case_investigator", "safety_reporter")]
            logger.info(f"  PharmaVigil agents registered: {len(our_agents)}/3")
        else:
            logger.info(f"  Agents response: {str(agents)[:200]}")
    else:
        logger.warning(f"  Could not list agents: {resp.status_code} {resp.text[:200]}")


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
