"""
Provider Adapters - Translate between Open Responses schema and provider APIs

Each adapter:
1. Takes Open Responses items as input
2. Translates to provider's native format
3. Calls the provider
4. Translates response back to Open Responses items
"""
import json
import logging
import requests
import uuid
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Generator

from .types import (
    Item, MessageItem, FunctionCallItem, FunctionCallOutputItem,
    FunctionTool, CreateResponseRequest, ResponseResource,
    InputTextContent, OutputTextContent
)

log = logging.getLogger(__name__)

class BaseAdapter(ABC):
    """Base class for provider adapters."""
    
    def __init__(self, base_url: str, api_key: str, model: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model

    @abstractmethod
    def create_response(self, request: CreateResponseRequest) -> ResponseResource:
        """Execute a request and return Open Responses format."""
        pass

    @abstractmethod
    def create_response_stream(self, request: CreateResponseRequest) -> Generator[Dict[str, Any], None, None]:
        """Stream a response with Open Responses events."""
        pass


class OllamaAdapter(BaseAdapter):
    """
    Adapter for Ollama's OpenAI-compatible API.
    Translates Open Responses items <-> Chat Completions format.
    """

    def __init__(self, base_url: str = "http://localhost:11434/v1", model: str = "qwen3:4b"):
        super().__init__(base_url, "ollama", model)

    def _items_to_messages(self, items: List[Item]) -> List[Dict[str, Any]]:
        """Convert Open Responses items to chat messages."""
        messages = []
        for item in items:
            item_dict = item.to_dict() if hasattr(item, 'to_dict') else item
            item_type = item_dict.get("type", "")

            if item_type == "message":
                role = item_dict.get("role", "user")
                # Extract text from content array
                text_parts = []
                for c in item_dict.get("content", []):
                    if c.get("type") in ("input_text", "output_text"):
                        text_parts.append(c.get("text", ""))
                messages.append({"role": role, "content": " ".join(text_parts)})

            elif item_type == "function_call":
                # Model's function call -> assistant message with tool_calls
                messages.append({
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{
                        "id": item_dict.get("call_id"),
                        "type": "function",
                        "function": {
                            "name": item_dict.get("name"),
                            "arguments": item_dict.get("arguments")
                        }
                    }]
                })

            elif item_type == "function_call_output":
                # Tool result -> tool message
                output_text = ""
                for o in item_dict.get("output", []):
                    if o.get("type") == "input_text":
                        output_text += o.get("text", "")
                messages.append({
                    "role": "tool",
                    "tool_call_id": item_dict.get("call_id"),
                    "content": output_text
                })

        return messages

    def _tools_to_chat_format(self, tools: List[FunctionTool]) -> List[Dict[str, Any]]:
        """Convert Open Responses tools to chat completions format."""
        return [{
            "type": "function",
            "function": {
                "name": t.name if hasattr(t, 'name') else t.get("name"),
                "description": t.description if hasattr(t, 'description') else t.get("description"),
                "parameters": t.parameters if hasattr(t, 'parameters') else t.get("parameters")
            }
        } for t in tools]

    def _response_to_items(self, response: Dict[str, Any]) -> List[Item]:
        """Convert chat completion response to Open Responses items."""
        items = []
        choice = response.get("choices", [{}])[0]
        message = choice.get("message", {})

        tool_calls = message.get("tool_calls")
        if tool_calls:
            for tc in tool_calls:
                items.append({
                    "type": "function_call",
                    "id": f"fc_{uuid.uuid4().hex[:16]}",
                    "call_id": tc.get("id"),
                    "name": tc["function"]["name"],
                    "arguments": tc["function"]["arguments"],
                    "status": "completed"
                })
        elif message.get("content"):
            items.append({
                "type": "message",
                "id": f"msg_{uuid.uuid4().hex[:16]}",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": message["content"]}]
            })

        return items

    def create_response(self, request: CreateResponseRequest) -> ResponseResource:
        """Execute via Ollama's chat completions endpoint."""
        # Convert input
        if isinstance(request.input, str):
            messages = [{"role": "user", "content": request.input}]
        else:
            messages = self._items_to_messages(request.input)

        # Build payload
        payload = {
            "model": request.model or self.model,
            "messages": messages,
            "stream": False
        }
        if request.tools:
            payload["tools"] = self._tools_to_chat_format(request.tools)
            payload["tool_choice"] = request.tool_choice or "auto"
        if request.temperature is not None:
            payload["temperature"] = request.temperature

        # Call Ollama
        url = f"{self.base_url}/chat/completions"
        headers = {"Content-Type": "application/json"}
        
        log.debug(f"Ollama request: {url}")
        resp = requests.post(url, json=payload, headers=headers, timeout=120)
        resp.raise_for_status()
        data = resp.json()

        # Convert to Open Responses
        return ResponseResource(
            id=f"resp_{uuid.uuid4().hex[:16]}",
            status="completed",
            output=self._response_to_items(data),
            model=request.model or self.model,
            usage=data.get("usage")
        )

    def create_response_stream(self, request: CreateResponseRequest) -> Generator[Dict[str, Any], None, None]:
        """Stream via Ollama - yields Open Responses events."""
        # Convert input
        if isinstance(request.input, str):
            messages = [{"role": "user", "content": request.input}]
        else:
            messages = self._items_to_messages(request.input)

        payload = {
            "model": request.model or self.model,
            "messages": messages,
            "stream": True
        }
        if request.tools:
            payload["tools"] = self._tools_to_chat_format(request.tools)
            payload["tool_choice"] = request.tool_choice or "auto"

        url = f"{self.base_url}/chat/completions"
        headers = {"Content-Type": "application/json"}

        resp_id = f"resp_{uuid.uuid4().hex[:16]}"
        yield {"type": "response.created", "response": {"id": resp_id, "status": "in_progress"}}

        with requests.post(url, json=payload, headers=headers, stream=True, timeout=120) as resp:
            resp.raise_for_status()
            accumulated_text = ""
            for line in resp.iter_lines():
                if not line:
                    continue
                line = line.decode("utf-8")
                if line.startswith("data: "):
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                        if delta.get("content"):
                            accumulated_text += delta["content"]
                            yield {
                                "type": "response.output_text.delta",
                                "delta": delta["content"]
                            }
                    except json.JSONDecodeError:
                        pass

        # Final event
        yield {
            "type": "response.completed",
            "response": {
                "id": resp_id,
                "status": "completed",
                "output": [{
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": accumulated_text}]
                }]
            }
        }


class OpenRouterAdapter(BaseAdapter):
    """
    Adapter for OpenRouter's API.
    Same translation logic, different auth and endpoint.
    """

    def __init__(self, api_key: str, model: str = "openai/gpt-4o"):
        super().__init__("https://openrouter.ai/api/v1", api_key, model)

    def _items_to_messages(self, items: List[Item]) -> List[Dict[str, Any]]:
        """Same as Ollama - chat completions format."""
        messages = []
        for item in items:
            item_dict = item.to_dict() if hasattr(item, 'to_dict') else item
            item_type = item_dict.get("type", "")

            if item_type == "message":
                role = item_dict.get("role", "user")
                text_parts = []
                for c in item_dict.get("content", []):
                    if c.get("type") in ("input_text", "output_text"):
                        text_parts.append(c.get("text", ""))
                messages.append({"role": role, "content": " ".join(text_parts)})

            elif item_type == "function_call":
                messages.append({
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{
                        "id": item_dict.get("call_id"),
                        "type": "function",
                        "function": {
                            "name": item_dict.get("name"),
                            "arguments": item_dict.get("arguments")
                        }
                    }]
                })

            elif item_type == "function_call_output":
                output_text = ""
                for o in item_dict.get("output", []):
                    if o.get("type") == "input_text":
                        output_text += o.get("text", "")
                messages.append({
                    "role": "tool",
                    "tool_call_id": item_dict.get("call_id"),
                    "content": output_text
                })

        return messages

    def _tools_to_chat_format(self, tools: List[FunctionTool]) -> List[Dict[str, Any]]:
        return [{
            "type": "function",
            "function": {
                "name": t.name if hasattr(t, 'name') else t.get("name"),
                "description": t.description if hasattr(t, 'description') else t.get("description"),
                "parameters": t.parameters if hasattr(t, 'parameters') else t.get("parameters")
            }
        } for t in tools]

    def _response_to_items(self, response: Dict[str, Any]) -> List[Item]:
        items = []
        choice = response.get("choices", [{}])[0]
        message = choice.get("message", {})

        tool_calls = message.get("tool_calls")
        if tool_calls:
            for tc in tool_calls:
                items.append({
                    "type": "function_call",
                    "id": f"fc_{uuid.uuid4().hex[:16]}",
                    "call_id": tc.get("id"),
                    "name": tc["function"]["name"],
                    "arguments": tc["function"]["arguments"],
                    "status": "completed"
                })
        elif message.get("content"):
            items.append({
                "type": "message",
                "id": f"msg_{uuid.uuid4().hex[:16]}",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": message["content"]}]
            })

        return items

    def create_response(self, request: CreateResponseRequest) -> ResponseResource:
        if isinstance(request.input, str):
            messages = [{"role": "user", "content": request.input}]
        else:
            messages = self._items_to_messages(request.input)

        payload = {
            "model": request.model or self.model,
            "messages": messages,
            "stream": False
        }
        if request.tools:
            payload["tools"] = self._tools_to_chat_format(request.tools)
            payload["tool_choice"] = request.tool_choice or "auto"
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.max_output_tokens:
            payload["max_tokens"] = request.max_output_tokens

        url = f"{self.base_url}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

        log.debug(f"OpenRouter request: {url}")
        resp = requests.post(url, json=payload, headers=headers, timeout=120)
        resp.raise_for_status()
        data = resp.json()

        return ResponseResource(
            id=data.get("id", f"resp_{uuid.uuid4().hex[:16]}"),
            status="completed",
            output=self._response_to_items(data),
            model=request.model or self.model,
            usage=data.get("usage")
        )

    def create_response_stream(self, request: CreateResponseRequest) -> Generator[Dict[str, Any], None, None]:
        if isinstance(request.input, str):
            messages = [{"role": "user", "content": request.input}]
        else:
            messages = self._items_to_messages(request.input)

        payload = {
            "model": request.model or self.model,
            "messages": messages,
            "stream": True
        }
        if request.tools:
            payload["tools"] = self._tools_to_chat_format(request.tools)
            payload["tool_choice"] = request.tool_choice or "auto"

        url = f"{self.base_url}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

        resp_id = f"resp_{uuid.uuid4().hex[:16]}"
        yield {"type": "response.created", "response": {"id": resp_id, "status": "in_progress"}}

        with requests.post(url, json=payload, headers=headers, stream=True, timeout=120) as resp:
            resp.raise_for_status()
            accumulated_text = ""
            for line in resp.iter_lines():
                if not line:
                    continue
                line = line.decode("utf-8")
                if line.startswith("data: "):
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                        if delta.get("content"):
                            accumulated_text += delta["content"]
                            yield {
                                "type": "response.output_text.delta",
                                "delta": delta["content"]
                            }
                    except json.JSONDecodeError:
                        pass

        yield {
            "type": "response.completed",
            "response": {
                "id": resp_id,
                "status": "completed",
                "output": [{
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": accumulated_text}]
                }]
            }
        }
