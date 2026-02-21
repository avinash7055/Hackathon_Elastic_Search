"""Elastic Agent Builder Converse API client.

Wraps the Kibana Converse API to communicate with Agent Builder agents.
Handles authentication, streaming responses, and response parsing.
"""

import asyncio
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
            "agent_id": agent_id,
            "input": message,
        }
        if conversation_id:
            payload["conversation_id"] = conversation_id

        logger.info(f"Sending to agent '{agent_id}': {message[:100]}...")

        # Retry up to 3 times on 429 rate limit errors
        for attempt in range(3):
            resp = await client.post(
                "/api/agent_builder/converse",
                json=payload,
            )
            if resp.status_code == 429:
                retry_after = int(resp.headers.get("retry-after", 20))
                logger.warning(f"Rate limited (429). Waiting {retry_after}s before retry {attempt+1}/3...")
                await asyncio.sleep(retry_after)
                continue
            break  # success or non-429 error

        if resp.status_code != 200:
            logger.error(f"Converse API error: {resp.status_code} {resp.text}")
            raise Exception(f"Agent Builder API error: {resp.status_code} — {resp.text}")

        data = resp.json()
        
        # LOG RAW RESPONSE FOR DEBUGGING
        logger.info(f"RAW DATA FROM AGENT '{agent_id}': {json.dumps(data)[:5000]}")

        # The response structure can vary.
        # Primary: data["response"]["message"] (standard Agent Builder format)
        # Fallback: data["message"] (alternative format)
        response_text = ""
        
        # Check nested response.message first (standard format)
        if isinstance(data.get("response"), dict):
            response_text = data["response"].get("message", "")
        
        # Fallback to top-level message
        if not response_text:
            response_text = data.get("message", "")
        
        # If still empty, look through 'steps' for the final text or reasoning
        if not response_text and "steps" in data and isinstance(data["steps"], list):
            # Try to get the last text step or reasoning step
            for step in reversed(data["steps"]):
                if step.get("type") in ("text", "reasoning") and step.get("reasoning" if step.get("type") == "reasoning" else "text"):
                    response_text = step.get("reasoning" if step.get("type") == "reasoning" else "text", "")
                    if response_text:
                        break

        if not response_text and "output" in data:
            response_text = data.get("output", "")
            
        # Extract tool calls from steps if not at top level
        tool_calls = data.get("tool_calls", data.get("toolCalls", []))
        if not tool_calls and "steps" in data and isinstance(data["steps"], list):
            for step in data["steps"]:
                if step.get("type") == "tool_call":
                    tool_calls.append(step)

        result = {
            "response": response_text,
            "conversation_id": data.get("conversation_id", data.get("conversationId", conversation_id)),
            "tool_calls": tool_calls,
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
            "agent_id": agent_id,
            "input": message,
            "stream": True,
        }
        if conversation_id:
            payload["conversation_id"] = conversation_id

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
            data = resp.json()
            return data.get("results", []) if isinstance(data, dict) else data
        logger.error(f"Failed to list agents: {resp.status_code}")
        return []

    async def list_tools(self) -> list[dict]:
        """List all registered tools."""
        client = await self._get_client()
        resp = await client.get("/api/agent_builder/tools")
        if resp.status_code == 200:
            data = resp.json()
            return data.get("results", []) if isinstance(data, dict) else data
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
