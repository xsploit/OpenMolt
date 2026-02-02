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
    
    Accepts ollama_options dict for performance settings:
      - num_ctx: Context window size
      - num_predict: Max tokens
      - num_batch: Batch size
      - num_gpu: GPU layers
      - kv_cache_type: "q8_0" for faster inference
      - flash_attention: True for faster attention
      - temperature, repeat_penalty, etc.
    """

    def __init__(self, base_url: str = "http://localhost:11434/v1", model: str = "qwen3:4b", ollama_options: dict = None):
        super().__init__(base_url, "ollama", model)
        # Default optimized options
        self.ollama_options = {
            "num_batch": 512,
            "num_gpu": 1,
            "repeat_penalty": 1.1,
            "kv_cache_type": "q8_0",
            "flash_attention": True,
        }
        if ollama_options:
            self.ollama_options.update(ollama_options)

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

        # Build payload with optimized options (stream to avoid long blocking)
        payload = {
            "model": request.model or self.model,
            "messages": messages,
            "stream": True,
            "options": self.ollama_options.copy()  # Add Ollama-specific options
        }
        if request.tools:
            payload["tools"] = self._tools_to_chat_format(request.tools)
            payload["tool_choice"] = request.tool_choice or "auto"
        if request.temperature is not None:
            payload["temperature"] = request.temperature
            payload["options"]["temperature"] = request.temperature
        if request.max_output_tokens:
            payload["options"]["num_predict"] = request.max_output_tokens

        # Call Ollama
        url = f"{self.base_url}/chat/completions"
        headers = {"Content-Type": "application/json"}
        
        log.debug(f"Ollama request: {url} (stream)")
        accumulated_text = ""
        with requests.post(url, json=payload, headers=headers, stream=True, timeout=300) as resp:
            resp.raise_for_status()
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
                        tool_calls = delta.get("tool_calls") or []
                        if tool_calls:
                            # If the model emits tool calls, keep the arguments for visibility
                            tc = tool_calls[0]
                            accumulated_text = tc.get("function", {}).get("arguments", "")
                    except json.JSONDecodeError:
                        pass

        return ResponseResource(
            id=f"resp_{uuid.uuid4().hex[:16]}",
            status="completed",
            output=[{
                "type": "message",
                "id": f"msg_{uuid.uuid4().hex[:16]}",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": accumulated_text}]
            }],
            model=request.model or self.model,
            usage=None
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
            "stream": True,
            "options": self.ollama_options.copy()  # Add Ollama-specific options
        }
        if request.tools:
            payload["tools"] = self._tools_to_chat_format(request.tools)
            payload["tool_choice"] = request.tool_choice or "auto"
        if request.temperature is not None:
            payload["options"]["temperature"] = request.temperature
        if request.max_output_tokens:
            payload["options"]["num_predict"] = request.max_output_tokens

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
    def _normalize_item(self, item: Any) -> Dict[str, Any]:
        """Normalize Open Responses items to OpenRouter /responses schema."""
        d = item.to_dict() if hasattr(item, "to_dict") else dict(item)
        otype = d.get("type")

        if otype == "function_call":
            # Ensure arguments is a string
            args = d.get("arguments")
            if not isinstance(args, str):
                try:
                    d["arguments"] = json.dumps(args)
                except Exception:
                    d["arguments"] = str(args)
            # Ensure required call_id
            if not d.get("call_id"):
                d["call_id"] = d.get("id") or f"call_{uuid.uuid4().hex[:8]}"

        elif otype == "function_call_output":
            # OpenRouter expects output as string, not array
            out = d.get("output")
            if isinstance(out, list):
                texts = []
                for o in out:
                    if isinstance(o, dict):
                        if o.get("type") == "input_text":
                            texts.append(o.get("text", ""))
                        elif "text" in o:
                            texts.append(o.get("text", ""))
                    else:
                        texts.append(str(o))
                d["output"] = "\n".join([t for t in texts if t])
            elif out is None:
                d["output"] = ""

        elif otype == "message":
            # Ensure content array uses dicts with type/text
            content = d.get("content") or []
            norm_content = []
            for c in content:
                if hasattr(c, "to_dict"):
                    c = c.to_dict()
                if isinstance(c, dict):
                    norm_content.append(c)
                else:
                    norm_content.append({"type": "input_text", "text": str(c)})
            d["content"] = norm_content

        return d

    def _items_to_plaintext(self, items: List[Any]) -> str:
        """Flatten Open Responses items to a single prompt string (fallback for providers that only accept string input)."""
        parts = []
        for it in items:
            d = it.to_dict() if hasattr(it, "to_dict") else dict(it)
            t = d.get("type")
            role = d.get("role", "")
            if t == "message":
                texts = []
                for c in d.get("content", []) or []:
                    if hasattr(c, "to_dict"):
                        c = c.to_dict()
                    if isinstance(c, dict):
                        texts.append(c.get("text", ""))
                    else:
                        texts.append(str(c))
                parts.append(f"[{role}] " + " ".join(texts))
            elif t == "function_call":
                parts.append(f"[tool-call {d.get('name')}] args={d.get('arguments')}")
            elif t == "function_call_output":
                out = d.get("output")
                if isinstance(out, list):
                    out_text = " ".join([o.get("text", "") if isinstance(o, dict) else str(o) for o in out])
                else:
                    out_text = str(out)
                parts.append(f"[tool-result {d.get('call_id')}] {out_text}")
            elif t == "reasoning":
                parts.append("[reasoning]")
            else:
                parts.append(str(d))
        return "\n".join(parts)
    def _tool_entry(self, t):
        """Convert a FunctionTool dataclass or plain dict to /responses tool shape."""
        name = t.name if hasattr(t, "name") else t.get("name")
        desc = t.description if hasattr(t, "description") else t.get("description")
        params = t.parameters if hasattr(t, "parameters") else t.get("parameters")
        strict = t.strict if hasattr(t, "strict") else t.get("strict")
        entry = {
            "type": "function",
            "name": name,
            "description": desc,
            "parameters": params,
        }
        # Only include strict when present to avoid None validation issues
        if strict is not None:
            entry["strict"] = strict
        return entry
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

    def _response_to_items_chat(self, response: Dict[str, Any]) -> List[Item]:
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
        # Use OpenRouter /responses endpoint (normalized schema)
        if isinstance(request.input, str):
            input_items = request.input  # Spec allows raw string
        else:
            # OpenRouter currently prefers string input; flatten items to text.
            input_items = self._items_to_plaintext(request.input)

        payload = {
            "model": request.model or self.model,
            "input": input_items,
        }
        if request.tools:
            payload["tools"] = [self._tool_entry(t) for t in request.tools]
            payload["tool_choice"] = request.tool_choice or "auto"
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.max_output_tokens:
            payload["max_output_tokens"] = request.max_output_tokens

        url = f"{self.base_url}/responses"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

        log.debug(f"OpenRouter request: {url}")
        resp = requests.post(url, json=payload, headers=headers, timeout=120)
        try:
            resp.raise_for_status()
        except requests.HTTPError as e:
            log.error(f"OpenRouter 400/err body: {resp.text[:500]}")
            log.error(f"Payload sent: {json.dumps(payload)[:500]}")
            raise
        data = resp.json()

        def _response_to_items_resp(resp_json: Dict[str, Any]) -> List[Item]:
            items_out = []
            output = resp_json.get("output") or []
            for o in output:
                otype = o.get("type")
                if otype == "message":
                    content = o.get("content") or []
                    text_parts = []
                    for c in content:
                        if c.get("type") in ("output_text", "text"):
                            text_parts.append(c.get("text", ""))
                    items_out.append({
                        "type": "message",
                        "id": o.get("id", f"msg_{uuid.uuid4().hex[:16]}"),
                        "role": o.get("role", "assistant"),
                        "status": o.get("status", "completed"),
                        "content": [{"type": "output_text", "text": " ".join(text_parts)}],
                    })
                elif otype == "function_call":
                    items_out.append({
                        "type": "function_call",
                        "id": o.get("id", f"fc_{uuid.uuid4().hex[:16]}"),
                        "call_id": o.get("id"),
                        "name": o.get("name"),
                        "arguments": o.get("arguments"),
                        "status": o.get("status", "completed"),
                    })
                elif otype == "function_call_output":
                    items_out.append({
                        "type": "function_call_output",
                        "call_id": o.get("call_id"),
                        "output": [{"type": "input_text", "text": o.get("content", "")}],
                    })
            if not items_out and resp_json.get("choices"):
                items_out = self._response_to_items_chat(resp_json)
            return items_out

        return ResponseResource(
            id=data.get("id", f"resp_{uuid.uuid4().hex[:16]}"),
            status="completed",
            output=_response_to_items_resp(data),
            model=request.model or self.model,
            usage=data.get("usage")
        )

    def create_response_stream(self, request: CreateResponseRequest) -> Generator[Dict[str, Any], None, None]:
        if isinstance(request.input, str):
            input_items = request.input
        else:
            input_items = self._items_to_plaintext(request.input)

        payload = {
            "model": request.model or self.model,
            "input": input_items,
            "stream": True
        }
        if request.tools:
            payload["tools"] = [self._tool_entry(t) for t in request.tools]
            payload["tool_choice"] = request.tool_choice or "auto"

        url = f"{self.base_url}/responses"
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
                        output_list = chunk.get("output") or []
                        for o in output_list:
                            if o.get("type") == "message":
                                for c in o.get("content", []):
                                    if c.get("type") in ("output_text", "text") and c.get("text"):
                                        accumulated_text += c["text"]
                                        yield {
                                            "type": "response.output_text.delta",
                                            "delta": c["text"]
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

