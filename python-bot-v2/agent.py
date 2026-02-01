import json
import logging
import time
from typing import List, Dict, Any, Callable, Optional
from client import OpenResponsesClient
import moltbook

log = logging.getLogger(__name__)

class ToolRegistry:
    def __init__(self):
        self.tools = []
        self.functions = {}

    def register(self, name: str, description: str, parameters: Dict[str, Any], func: Callable):
        tool_def = {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": parameters
            }
        }
        self.tools.append(tool_def)
        self.functions[name] = func

class MoltbookAgent:
    def __init__(
        self, 
        client: OpenResponsesClient, 
        moltbook_api_key: str,
        persona: str,
        system_prompt: str
    ):
        self.client = client
        self.moltbook_api_key = moltbook_api_key
        self.persona = persona
        self.system_prompt = system_prompt
        self.registry = ToolRegistry()
        self._register_default_tools()

    def _register_default_tools(self):
        # Moltbook Tools
        self.registry.register(
            name="search_moltbook",
            description="Search Moltbook posts and comments.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"}
                },
                "required": ["query"]
            },
            func=lambda query: moltbook.search(self.moltbook_api_key, query)
        )

        self.registry.register(
            name="create_post",
            description="Create a new post on Moltbook.",
            parameters={
                "type": "object",
                "properties": {
                    "submolt": {"type": "string", "description": "The submolt to post to (e.g. 'general')."},
                    "title": {"type": "string", "description": "The title of the post."},
                    "content": {"type": "string", "description": "The content body of the post."}
                },
                "required": ["submolt", "title", "content"]
            },
            func=lambda submolt, title, content: moltbook.create_post(self.moltbook_api_key, submolt, title, content)
        )

        self.registry.register(
            name="create_comment",
            description="Add a comment to a post or reply to a comment.",
            parameters={
                "type": "object",
                "properties": {
                    "post_id": {"type": "string", "description": "The ID of the post to comment on."},
                    "content": {"type": "string", "description": "The comment text."},
                    "parent_id": {"type": "string", "description": "Optional parent comment ID for replies."}
                },
                "required": ["post_id", "content"]
            },
            func=lambda post_id, content, parent_id=None: moltbook.add_comment(self.moltbook_api_key, post_id, content, parent_id)
        )

        self.registry.register(
            name="send_dm",
            description="Send a direct message reply.",
            parameters={
                "type": "object",
                "properties": {
                    "conversation_id": {"type": "string", "description": "The ID of the DM conversation."},
                    "message": {"type": "string", "description": "The message text to send."}
                },
                "required": ["conversation_id", "message"]
            },
            func=lambda conversation_id, message: moltbook._post(self.moltbook_api_key, f"/agents/dm/conversations/{conversation_id}/send", {"message": message})
        )

    def think(self, context_messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Run the agent loop:
        1. Send context to LLM
        2. LLM calls tools? -> Execute -> Loop back
        3. LLM returns message -> Done
        """
        messages = [{"role": "system", "content": self.system_prompt}] + context_messages
        
        while True:
            # 1. Call LLM
            response = self.client.chat_completion(
                messages=messages,
                tools=self.registry.tools,
                tool_choice="auto"
            )
            
            # TODO: Handle streaming properly if we switch to stream=True later
            # For now sync
            
            choice = response["choices"][0]
            message = choice["message"]
            messages.append(message)

            tool_calls = message.get("tool_calls")
            
            if not tool_calls:
                # Final response
                return message["content"]
            
            # 2. Execute Tools
            for tc in tool_calls:
                func_name = tc["function"]["name"]
                args = json.loads(tc["function"]["arguments"])
                call_id = tc["id"]
                
                log.info(f"Tool Call: {func_name}({args})")
                
                if func_name in self.registry.functions:
                    try:
                        result = self.registry.functions[func_name](**args)
                        content = json.dumps(result)
                    except Exception as e:
                        content = f"Error: {str(e)}"
                else:
                    content = "Error: Tool not found"
                
                messages.append({
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": content
                })

            # Loop back to let LLM see tool results
