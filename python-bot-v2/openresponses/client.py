"""
OpenResponses Client - Unified interface for multi-provider agentic loops
"""
import logging
from typing import List, Dict, Any, Optional, Union, Generator

from .types import (
    Item, FunctionTool, CreateResponseRequest, ResponseResource,
    user_message, system_message, function_output
)
from .adapters import BaseAdapter, OllamaAdapter, OpenRouterAdapter

log = logging.getLogger(__name__)


class OpenResponsesClient:
    """
    Unified client that speaks Open Responses to any supported provider.
    
    Usage:
        # Local Ollama
        client = OpenResponsesClient.ollama(model="qwen3:4b")
        
        # Cloud OpenRouter  
        client = OpenResponsesClient.openrouter(api_key="sk-...", model="openai/gpt-4o")
        
        # Create response
        response = client.create_response(
            input="Hello, world!",
            tools=[...],
            tool_choice="auto"
        )
    """

    def __init__(self, adapter: BaseAdapter):
        self.adapter = adapter

    @classmethod
    def ollama(cls, base_url: str = "http://localhost:11434/v1", model: str = "qwen3:4b", ollama_options: dict = None) -> "OpenResponsesClient":
        """Create a client using Ollama backend with optional optimized options."""
        return cls(OllamaAdapter(base_url=base_url, model=model, ollama_options=ollama_options))

    @classmethod
    def openrouter(
        cls,
        api_key: str,
        model: str = "openai/gpt-4o",
        providers_only: Optional[list] = None,
        allow_fallbacks: Optional[bool] = None,
        providers_ignore: Optional[list] = None,
        providers_order: Optional[list] = None,
    ) -> "OpenResponsesClient":
        """Create a client using OpenRouter backend."""
        return cls(
            OpenRouterAdapter(
                api_key=api_key,
                model=model,
                providers_only=providers_only,
                allow_fallbacks=allow_fallbacks,
                providers_ignore=providers_ignore,
                providers_order=providers_order,
            )
        )

    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> "OpenResponsesClient":
        """Create client from config dict. Respects brain_use_openrouter flag."""
        if config.get("brain_use_openrouter"):
            return cls.openrouter(
                api_key=config["openrouter_api_key"],
                model=config.get("openrouter_model", "openai/gpt-4o"),
                providers_only=config.get("openrouter_provider_only"),
                allow_fallbacks=config.get("openrouter_allow_fallbacks"),
                providers_ignore=config.get("openrouter_provider_ignore"),
                providers_order=config.get("openrouter_provider_order"),
            )
        else:
            # Get Ollama options from config
            ollama_options = config.get("ollama_options", {}).copy()
            # Also check for explicit num_ctx setting
            if config.get("ollama_num_ctx"):
                ollama_options["num_ctx"] = config["ollama_num_ctx"]
            return cls.ollama(
                base_url=config.get("ollama_base_url", "http://localhost:11434/v1"),
                model=config.get("ollama_model", "qwen3:4b"),
                ollama_options=ollama_options
            )

    def create_response(
        self,
        input: Union[str, List[Item]],
        tools: Optional[List[FunctionTool]] = None,
        tool_choice: Optional[Union[str, Dict[str, Any]]] = None,
        temperature: Optional[float] = None,
        max_output_tokens: Optional[int] = None,
        model: Optional[str] = None,
        previous_response_id: Optional[str] = None
    ) -> ResponseResource:
        """
        Create a response using the configured provider.
        
        Args:
            input: Either a string (user message) or list of Open Responses items
            tools: List of function tools the model can call
            tool_choice: "auto" | "required" | "none" | {"type": "function", "name": "..."}
            temperature: Sampling temperature
            max_output_tokens: Maximum tokens to generate
            model: Override the default model
            previous_response_id: Continue from a previous response
            
        Returns:
            ResponseResource with output items
        """
        request = CreateResponseRequest(
            model=model or self.adapter.model,
            input=input,
            tools=tools,
            tool_choice=tool_choice,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            previous_response_id=previous_response_id
        )
        return self.adapter.create_response(request)

    def create_response_stream(
        self,
        input: Union[str, List[Item]],
        tools: Optional[List[FunctionTool]] = None,
        tool_choice: Optional[Union[str, Dict[str, Any]]] = None,
        temperature: Optional[float] = None,
        model: Optional[str] = None
    ) -> Generator[Dict[str, Any], None, None]:
        """
        Stream a response with Open Responses events.
        
        Yields events like:
            {"type": "response.created", "response": {...}}
            {"type": "response.output_text.delta", "delta": "..."}
            {"type": "response.completed", "response": {...}}
        """
        request = CreateResponseRequest(
            model=model or self.adapter.model,
            input=input,
            tools=tools,
            tool_choice=tool_choice,
            temperature=temperature,
            stream=True
        )
        yield from self.adapter.create_response_stream(request)

    def simple_completion(self, prompt: str, system: Optional[str] = None) -> str:
        """
        Simple text completion without tools.
        
        Args:
            prompt: User message
            system: Optional system message
            
        Returns:
            The model's text response
        """
        items = []
        if system:
            items.append(system_message(system))
        items.append(user_message(prompt))

        response = self.create_response(input=items)
        return response.get_text() or ""
