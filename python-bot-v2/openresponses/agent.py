"""
OpenResponses Agent - Agentic loop with tool execution and Discord callbacks
"""
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Callable

from .client import OpenResponsesClient
from .types import (
    Item, FunctionTool, ResponseResource,
    system_message, user_message, function_output, FunctionCallOutputItem
)

log = logging.getLogger(__name__)


class ToolRegistry:
    """Registry of callable tools."""

    def __init__(self):
        self.tools: List[FunctionTool] = []
        self.handlers: Dict[str, Callable] = {}

    def register(
        self,
        name: str,
        description: str,
        parameters: Dict[str, Any],
        handler: Callable,
        strict: bool = False
    ):
        """Register a tool that the agent can call."""
        tool = FunctionTool(
            name=name,
            description=description,
            parameters=parameters,
            strict=strict
        )
        self.tools.append(tool)
        self.handlers[name] = handler

    def execute(self, name: str, arguments: Dict[str, Any]) -> Any:
        """Execute a tool by name."""
        if name not in self.handlers:
            raise ValueError(f"Unknown tool: {name}")
        return self.handlers[name](**arguments)

    def get_tools(self) -> List[FunctionTool]:
        """Get all registered tools as FunctionTool objects."""
        return self.tools


class Agent:
    """
    An agent that can use tools to complete tasks.
    
    The agent runs an agentic loop:
    1. Send context to LLM
    2. If LLM returns function_call items -> execute tools
    3. Append function_call_output items
    4. Loop back to LLM with updated context
    5. When LLM returns message without tool calls -> done
    
    Supports callbacks for Discord webhook integration:
    - on_iteration: Called at start of each iteration
    - on_tool_call: Called when a tool is executed
    - on_response: Called with final response
    """

    def __init__(
        self,
        client: OpenResponsesClient,
        system_prompt: str = "",
        max_iterations: int = 10,
        # Callbacks for external notifications
        on_iteration: Optional[Callable[[int], None]] = None,
        on_tool_call: Optional[Callable[[str, Dict, Any], None]] = None,
        on_response: Optional[Callable[[str, str], None]] = None,  # (thinking, response)
    ):
        self.client = client
        self.system_prompt = system_prompt
        self.max_iterations = max_iterations
        self.registry = ToolRegistry()
        
        # Callbacks
        self.on_iteration = on_iteration
        self.on_tool_call = on_tool_call
        self.on_response = on_response

    def register_tool(
        self,
        name: str,
        description: str,
        parameters: Dict[str, Any],
        handler: Callable
    ):
        """Register a tool the agent can use."""
        self.registry.register(name, description, parameters, handler)

    def think(self, user_input: str, context: Optional[List[Item]] = None) -> str:
        """
        Run the agentic loop given user input.
        
        Args:
            user_input: The user's message/request
            context: Optional additional context items
            
        Returns:
            The final text response from the agent
        """
        # Build initial context
        items: List[Item] = []
        if self.system_prompt:
            items.append(system_message(self.system_prompt))
        if context:
            items.extend(context)
        items.append(user_message(user_input))

        tools = self.registry.get_tools() if self.registry.tools else None
        thinking_trace = []  # Collect thinking/reasoning

        for iteration in range(self.max_iterations):
            log.info(f"Agent iteration {iteration + 1}/{self.max_iterations}")
            
            # Callback: iteration start
            if self.on_iteration:
                try:
                    self.on_iteration(iteration + 1)
                except Exception as e:
                    log.debug(f"on_iteration callback error: {e}")

            # Call LLM
            response = self.client.create_response(
                input=items,
                tools=tools,
                tool_choice="auto" if tools else None
            )

            # Process output items
            function_calls = response.get_function_calls()

            if not function_calls:
                # No tool calls - we have a final answer
                final_text = response.get_text()
                log.info(f"Agent complete: {final_text[:100]}..." if final_text else "No response")
                
                # Callback: final response
                if self.on_response:
                    try:
                        thinking_str = "\n".join(thinking_trace) if thinking_trace else ""
                        self.on_response(thinking_str, final_text or "")
                    except Exception as e:
                        log.debug(f"on_response callback error: {e}")
                
                return final_text or ""

            # Execute each function call
            for fc in function_calls:
                call_id = fc.get("call_id")
                func_name = fc.get("name")
                args_str = fc.get("arguments", "{}")

                log.info(f"Tool call: {func_name}({args_str[:100]}...)")
                thinking_trace.append(f"[Tool: {func_name}]")

                try:
                    args = json.loads(args_str)
                    result = self.registry.execute(func_name, args)
                    result_str = json.dumps(result, default=str) if not isinstance(result, str) else result
                    log.info(f"Tool result: {str(result)[:100]}...")
                except Exception as e:
                    log.error(f"Tool error: {e}")
                    result = f"Error: {str(e)}"
                    result_str = str(result)

                # Callback: tool call
                if self.on_tool_call:
                    try:
                        self.on_tool_call(func_name, args, result_str)
                    except Exception as e:
                        log.debug(f"on_tool_call callback error: {e}")

                # Append function call and output to context
                items.append(fc)  # The function_call item
                items.append(function_output(call_id, result))  # The result

            # Continue loop with updated context

        log.warning("Agent hit max iterations")
        
        # Callback: max iterations
        if self.on_response:
            try:
                self.on_response("\n".join(thinking_trace), "Agent reached maximum iterations.")
            except Exception:
                pass
        
        return "Agent reached maximum iterations without completing."

    def run(self, user_input: str, context: Optional[List[Item]] = None) -> ResponseResource:
        """
        Run the agentic loop and return the full response resource.
        
        Similar to think() but returns the full ResponseResource instead of just text.
        """
        items: List[Item] = []
        if self.system_prompt:
            items.append(system_message(self.system_prompt))
        if context:
            items.extend(context)
        items.append(user_message(user_input))

        tools = self.registry.get_tools() if self.registry.tools else None

        for iteration in range(self.max_iterations):
            if self.on_iteration:
                try:
                    self.on_iteration(iteration + 1)
                except Exception:
                    pass

            response = self.client.create_response(
                input=items,
                tools=tools,
                tool_choice="auto" if tools else None
            )

            function_calls = response.get_function_calls()
            if not function_calls:
                return response

            for fc in function_calls:
                call_id = fc.get("call_id")
                func_name = fc.get("name")
                args_str = fc.get("arguments", "{}")

                try:
                    args = json.loads(args_str)
                    result = self.registry.execute(func_name, args)
                    result_str = json.dumps(result, default=str) if not isinstance(result, str) else result
                except Exception as e:
                    result = f"Error: {str(e)}"
                    result_str = str(result)

                if self.on_tool_call:
                    try:
                        self.on_tool_call(func_name, args, result_str)
                    except Exception:
                        pass

                items.append(fc)
                items.append(function_output(call_id, result))

        # Return last response even if we hit max iterations
        return response


class MultiProviderAgentPool:
    """
    Pool of agents using different providers.
    
    Example:
        pool = MultiProviderAgentPool(config)
        
        # Brain agent uses OpenRouter (expensive, smart)
        brain = pool.get_brain()
        
        # Worker agents use Ollama (cheap, local)
        worker = pool.get_worker()
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config

    def get_brain(
        self,
        system_prompt: str = "",
        on_iteration: Optional[Callable] = None,
        on_tool_call: Optional[Callable] = None,
        on_response: Optional[Callable] = None,
    ) -> Agent:
        """Get an agent using the 'brain' provider (usually cloud/expensive)."""
        client = OpenResponsesClient.openrouter(
            api_key=self.config["openrouter_api_key"],
            model=self.config.get("openrouter_model", "openai/gpt-4o")
        )
        return Agent(
            client=client,
            system_prompt=system_prompt,
            on_iteration=on_iteration,
            on_tool_call=on_tool_call,
            on_response=on_response,
        )

    def get_worker(
        self,
        system_prompt: str = "",
        on_iteration: Optional[Callable] = None,
        on_tool_call: Optional[Callable] = None,
        on_response: Optional[Callable] = None,
    ) -> Agent:
        """Get an agent using the 'worker' provider (usually local/cheap)."""
        client = OpenResponsesClient.ollama(
            base_url=self.config.get("ollama_base_url", "http://localhost:11434/v1"),
            model=self.config.get("ollama_model", "qwen3:4b")
        )
        return Agent(
            client=client,
            system_prompt=system_prompt,
            on_iteration=on_iteration,
            on_tool_call=on_tool_call,
            on_response=on_response,
        )

    def get_agent(
        self,
        use_brain: bool = False,
        system_prompt: str = "",
        on_iteration: Optional[Callable] = None,
        on_tool_call: Optional[Callable] = None,
        on_response: Optional[Callable] = None,
    ) -> Agent:
        """Get an agent, optionally using the brain provider."""
        if use_brain:
            return self.get_brain(system_prompt, on_iteration, on_tool_call, on_response)
        return self.get_worker(system_prompt, on_iteration, on_tool_call, on_response)
