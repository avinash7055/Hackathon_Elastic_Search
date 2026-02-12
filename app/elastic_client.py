"""Elastic Agent Builder Converse API client.

Wraps the Kibana Converse API to communicate with Agent Builder agents.
Handles authentication, streaming responses, and response parsing.
"""

import logging
import json
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class ElasticAgentClient:
    """Client for communicating with Elastic Agent Builder agents."""

    def __init__(
        self,
        kibana_url: Optional[str] = None,
        api_key: Optional[str] = None,
    ):
        self.kibana_url = (kibana_url or settings.kibana_url).rstrip("/")
        self.api_key = api_key or settings.kibana_api_key
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.kibana_url,
                headers={
                    "Authorization": f"ApiKey {self.api_key}",
                    "kbn-xsrf": "true",
                    "Content-Type": "application/json",
                },
                timeout=120.0,
            )
        return self._client

    async def converse(
        self,
        agent_id: str,
        message: str,
        conversation_id: Optional[str] = None,
    ) -> dict:
        """Send a message to an Agent Builder agent via the Converse API.
        
        Args:
            agent_id: The agent to converse with (e.g., 'signal_scanner')
            message: The user message to send
            conversation_id: Optional conversation ID for multi-turn
            
        Returns:
            Dict with 'response' (agent text), 'conversation_id', and 'tool_calls'
        """
        client = await self._get_client()

        payload = {
            "agentId": agent_id,
            "message": message,
        }
        if conversation_id:
            payload["conversationId"] = conversation_id

        logger.info(f"Sending to agent '{agent_id}': {message[:100]}...")

        resp = await client.post(
            "/api/agent_builder/converse",
            json=payload,
        )

        if resp.status_code != 200:
            logger.error(f"Converse API error: {resp.status_code} {resp.text}")
            raise Exception(f"Agent Builder API error: {resp.status_code} — {resp.text}")

        data = resp.json()

        result = {
            "response": data.get("message", ""),
            "conversation_id": data.get("conversationId", conversation_id),
            "tool_calls": data.get("toolCalls", []),
            "agent_id": agent_id,
            "raw": data,
        }

        logger.info(
            f"Agent '{agent_id}' responded ({len(result['response'])} chars, "
            f"{len(result['tool_calls'])} tool calls)"
        )

        return result

    async def converse_streaming(
        self,
        agent_id: str,
        message: str,
        conversation_id: Optional[str] = None,
    ):
        """Stream a response from an Agent Builder agent.
        
        Yields chunks as they arrive for real-time UI updates.
        """
        client = await self._get_client()

        payload = {
            "agentId": agent_id,
            "message": message,
            "stream": True,
        }
        if conversation_id:
            payload["conversationId"] = conversation_id

        logger.info(f"Streaming from agent '{agent_id}': {message[:100]}...")

        async with client.stream(
            "POST",
            "/api/agent_builder/converse",
            json=payload,
        ) as resp:
            if resp.status_code != 200:
                text = await resp.aread()
                raise Exception(f"Agent Builder API error: {resp.status_code} — {text}")

            buffer = ""
            async for chunk in resp.aiter_text():
                buffer += chunk
                # Yield complete lines
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if line:
                        try:
                            yield json.loads(line)
                        except json.JSONDecodeError:
                            yield {"type": "text", "content": line}

    async def list_agents(self) -> list[dict]:
        """List all registered agents."""
        client = await self._get_client()
        resp = await client.get("/api/agent_builder/agents")
        if resp.status_code == 200:
            return resp.json()
        logger.error(f"Failed to list agents: {resp.status_code}")
        return []

    async def list_tools(self) -> list[dict]:
        """List all registered tools."""
        client = await self._get_client()
        resp = await client.get("/api/agent_builder/tools")
        if resp.status_code == 200:
            return resp.json()
        logger.error(f"Failed to list tools: {resp.status_code}")
        return []

    async def health_check(self) -> dict:
        """Check connectivity to Kibana and Agent Builder."""
        try:
            client = await self._get_client()
            resp = await client.get("/api/status")
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "status": "connected",
                    "kibana_version": data.get("version", {}).get("number", "unknown"),
                }
            return {"status": "error", "code": resp.status_code}
        except Exception as e:
            return {"status": "unreachable", "error": str(e)}

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()


# Singleton instance
elastic_agent_client = ElasticAgentClient()
