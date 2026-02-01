"""
OpenResponses Type Definitions
Based on https://www.openresponses.org/specification
"""
from typing import List, Dict, Any, Optional, Union, Literal
from dataclasses import dataclass, field, asdict
from enum import Enum
import json

# ============================================================================
# Enums
# ============================================================================

class ItemStatus(str, Enum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    INCOMPLETE = "incomplete"
    FAILED = "failed"

class Role(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    DEVELOPER = "developer"
    TOOL = "tool"

class ToolChoice(str, Enum):
    AUTO = "auto"
    REQUIRED = "required"
    NONE = "none"

# ============================================================================
# Content Types
# ============================================================================

@dataclass
class InputTextContent:
    text: str
    type: str = "input_text"

@dataclass
class OutputTextContent:
    text: str
    type: str = "output_text"
    annotations: List[Dict[str, Any]] = field(default_factory=list)

@dataclass
class RefusalContent:
    refusal: str
    type: str = "refusal"

# ============================================================================
# Item Types (Core of Open Responses)
# ============================================================================

@dataclass
class MessageItem:
    """A message in the conversation."""
    role: str
    content: List[Union[InputTextContent, OutputTextContent, RefusalContent, Dict[str, Any]]]
    id: Optional[str] = None
    status: str = "completed"
    type: str = "message"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "id": self.id,
            "role": self.role,
            "status": self.status,
            "content": [c if isinstance(c, dict) else asdict(c) for c in self.content]
        }

@dataclass
class FunctionCallItem:
    """Model wants to call a function tool."""
    name: str
    arguments: str  # JSON string
    call_id: str
    id: Optional[str] = None
    status: str = "completed"
    type: str = "function_call"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "id": self.id,
            "name": self.name,
            "call_id": self.call_id,
            "arguments": self.arguments,
            "status": self.status
        }

    def parsed_arguments(self) -> Dict[str, Any]:
        return json.loads(self.arguments)

@dataclass
class FunctionCallOutputItem:
    """Result from executing an external function."""
    call_id: str
    output: List[Union[InputTextContent, Dict[str, Any]]]
    id: Optional[str] = None
    status: str = "completed"
    type: str = "function_call_output"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "id": self.id,
            "call_id": self.call_id,
            "output": [o if isinstance(o, dict) else asdict(o) for o in self.output],
            "status": self.status
        }

@dataclass
class ReasoningItem:
    """Reasoning trace from the model."""
    summary: List[Dict[str, Any]]
    id: Optional[str] = None
    encrypted_content: Optional[str] = None
    type: str = "reasoning"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "id": self.id,
            "summary": self.summary,
            "encrypted_content": self.encrypted_content
        }

# Type alias for any item
Item = Union[MessageItem, FunctionCallItem, FunctionCallOutputItem, ReasoningItem, Dict[str, Any]]

# ============================================================================
# Tool Definitions
# ============================================================================

@dataclass
class FunctionTool:
    """A function tool that the model can call."""
    name: str
    description: str
    parameters: Dict[str, Any]
    strict: bool = False
    type: str = "function"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
            "strict": self.strict
        }

# ============================================================================
# Request / Response
# ============================================================================

@dataclass
class CreateResponseRequest:
    """Request body for POST /responses"""
    model: str
    input: Union[str, List[Item]]
    tools: Optional[List[FunctionTool]] = None
    tool_choice: Optional[Union[str, Dict[str, Any]]] = None
    temperature: Optional[float] = None
    max_output_tokens: Optional[int] = None
    stream: bool = False
    previous_response_id: Optional[str] = None
    reasoning: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        d = {"model": self.model, "stream": self.stream}
        
        # Handle input
        if isinstance(self.input, str):
            d["input"] = self.input
        else:
            d["input"] = [i.to_dict() if hasattr(i, 'to_dict') else i for i in self.input]

        if self.tools:
            d["tools"] = [t.to_dict() if hasattr(t, 'to_dict') else t for t in self.tools]
        if self.tool_choice:
            d["tool_choice"] = self.tool_choice
        if self.temperature is not None:
            d["temperature"] = self.temperature
        if self.max_output_tokens:
            d["max_output_tokens"] = self.max_output_tokens
        if self.previous_response_id:
            d["previous_response_id"] = self.previous_response_id
        if self.reasoning:
            d["reasoning"] = self.reasoning

        return d

@dataclass
class ResponseResource:
    """Response from POST /responses"""
    id: str
    status: str
    output: List[Item]
    model: str
    usage: Optional[Dict[str, Any]] = None
    error: Optional[Dict[str, Any]] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ResponseResource":
        return cls(
            id=data.get("id", ""),
            status=data.get("status", "completed"),
            output=data.get("output", []),
            model=data.get("model", ""),
            usage=data.get("usage"),
            error=data.get("error")
        )

    def get_text(self) -> Optional[str]:
        """Extract text from the first message output."""
        for item in self.output:
            if isinstance(item, dict) and item.get("type") == "message":
                for content in item.get("content", []):
                    if content.get("type") == "output_text":
                        return content.get("text")
            elif isinstance(item, MessageItem):
                for content in item.content:
                    if isinstance(content, OutputTextContent):
                        return content.text
                    elif isinstance(content, dict) and content.get("type") == "output_text":
                        return content.get("text")
        return None

    def get_function_calls(self) -> List[Dict[str, Any]]:
        """Extract all function calls from output."""
        calls = []
        for item in self.output:
            if isinstance(item, dict) and item.get("type") == "function_call":
                calls.append(item)
            elif isinstance(item, FunctionCallItem):
                calls.append(item.to_dict())
        return calls

# ============================================================================
# Helpers
# ============================================================================

def user_message(text: str) -> MessageItem:
    """Create a user message item."""
    return MessageItem(
        role="user",
        content=[InputTextContent(text=text)]
    )

def system_message(text: str) -> MessageItem:
    """Create a system message item."""
    return MessageItem(
        role="system",
        content=[InputTextContent(text=text)]
    )

def assistant_message(text: str) -> MessageItem:
    """Create an assistant message item."""
    return MessageItem(
        role="assistant",
        content=[OutputTextContent(text=text)]
    )

def function_output(call_id: str, result: Any) -> FunctionCallOutputItem:
    """Create a function call output item."""
    text = result if isinstance(result, str) else json.dumps(result)
    return FunctionCallOutputItem(
        call_id=call_id,
        output=[InputTextContent(text=text)]
    )
