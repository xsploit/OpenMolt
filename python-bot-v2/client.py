"""
Open Responses Client
Strict implementation of https://www.openresponses.org/specification
"""
import json
import logging
import requests
from typing import Generator, Dict, Any, List, Optional, Union

log = logging.getLogger(__name__)

class OpenResponsesClient:
    def __init__(self, base_url: str, api_key: str = None, model: str = None):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.model = model
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}" if api_key else ""
        }

    def chat_completion(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[Union[str, Dict[str, Any]]] = None,
        stream: bool = False,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        response_format: Optional[Dict[str, Any]] = None
    ) -> Union[Dict[str, Any], Generator[Dict[str, Any], None, None]]:
        """
        Send a chat completion request following Open Responses spec.
        """
        url = f"{self.base_url}/chat/completions"
        
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": stream,
            "temperature": temperature
        }
        
        if tools:
            payload["tools"] = tools
        if tool_choice:
            payload["tool_choice"] = tool_choice
        if max_tokens:
            payload["max_tokens"] = max_tokens
        if response_format:
            payload["response_format"] = response_format

        log.debug(f"Request to {url}: {json.dumps(payload)[:200]}...")

        if stream:
            return self._handle_stream(url, payload)
        else:
            return self._handle_sync(url, payload)

    def _handle_sync(self, url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        resp = requests.post(url, headers=self.headers, json=payload, timeout=60)
        resp.raise_for_status()
        return resp.json()

    def _handle_stream(self, url: str, payload: Dict[str, Any]) -> Generator[Dict[str, Any], None, None]:
        resp = requests.post(url, headers=self.headers, json=payload, stream=True, timeout=60)
        resp.raise_for_status()

        for line in resp.iter_lines():
            if not line:
                continue
            
            line_str = line.decode('utf-8').strip()
            if not line_str.startswith('data: '):
                continue

            data_str = line_str[6:] # Strip "data: "
            
            if data_str == '[DONE]':
                break
                
            try:
                data = json.loads(data_str)
                yield data
            except json.JSONDecodeError:
                log.warning(f"Failed to decode stream line: {line_str}")
                continue
