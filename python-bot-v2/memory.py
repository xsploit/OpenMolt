"""
Letta-style Memory System for OpenMolt V2.

Implements:
- Core Memory Blocks: Always-in-context named blocks (Persona, Human, Scratchpad, etc.)
- Archival Memory: Long-term storage with semantic search
- Conversation Buffer: Rolling window of recent interactions
- Reflection: Sleep-time compute to consolidate memories

Structure adheres to Letta's "Memory Blocks" pattern:
<memory_blocks>
  <block label="persona">...</block>
  <block label="human">...</block>
</memory_blocks>
"""
import json
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
import hashlib

log = logging.getLogger(__name__)

MEMORY_PATH = Path("memory.json")
MAX_ARCHIVAL = 1000
MAX_BUFFER = 50 


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _hash(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()[:12]


class AgentMemory:
    """
    Letta-style memory with Memory Blocks and Archival storage.
    """
    
    def __init__(self, path: Path = MEMORY_PATH, embedding_client=None):
        self.path = path
        self.data = self._load()
        
        # Initialize embeddings client
        if embedding_client:
            self.embedder = embedding_client
        else:
            try:
                from embeddings_client import EmbeddingClient
                # Use empty config for default Ollama fallback
                self.embedder = EmbeddingClient({})
            except (ImportError, Exception) as e:
                self.embedder = None
                log.warning(f"Embeddings unavailable: {e} - falling back to keyword search")
    
    def _load(self) -> Dict:
        if self.path.exists():
            try:
                return json.loads(self.path.read_text(encoding="utf-8"))
            except Exception as e:
                log.warning(f"Memory load failed: {e}")
        return self._default()
    
    def _default(self) -> Dict:
        return {
            "blocks": {
                "persona": {
                    "value": "You are a helpful AI agent.",
                    "description": "The persona block: Stores details about your current persona, guiding how you behave and respond.",
                    "limit": 2000
                },
                "human": {
                    "value": "",
                    "description": "The human block: Stores key details about the person you are conversing with.",
                    "limit": 2000
                },
                "scratchpad": {
                    "value": "",
                    "description": "The scratchpad block: Use this to track your current state, plans, or working memory.",
                    "limit": 5000
                }
            },
            "archival": [],
            "buffer": [],
            "reflections": [],
            "stats": {
                "memories_written": 0,
                "memories_read": 0,
                "reflections_done": 0,
                "last_reflection": None,
            }
        }
    
    def save(self) -> None:
        try:
            self.path.write_text(json.dumps(self.data, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            log.error(f"Memory save failed: {e}")
    
    # =========================================================================
    # CORE MEMORY BLOCKS
    # =========================================================================
    
    def get_blocks(self) -> Dict[str, Dict]:
        return self.data.get("blocks", {})
    
    def get_block_summary(self) -> str:
        """Format blocks as XML-like structure for system prompt."""
        blocks = self.get_blocks()
        xml_parts = ["<memory_blocks>"]
        
        for label, block in blocks.items():
            val = block.get("value", "")
            desc = block.get("description", "")
            limit = block.get("limit", 1000)
            
            xml_parts.append(f""" <{label}>
  <description>{desc}</description>
  <metadata>
   - chars_current={len(val)}
   - chars_limit={limit}
  </metadata>
  <value>{val}</value>
 </{label}>""")
            
        xml_parts.append("</memory_blocks>")
        return "\n".join(xml_parts)
    
    def update_block(self, label: str, value: str) -> Dict:
        """Update a specific memory block."""
        blocks = self.data["blocks"]
        if label not in blocks:
             return {"error": f"Block '{label}' does not exist. Available: {list(blocks.keys())}"}
        
        limit = blocks[label].get("limit", 2000)
        if len(value) > limit:
             return {"error": f"Value too long ({len(value)} chars). Limit is {limit}."}
             
        blocks[label]["value"] = value
        self.save()
        return {"success": True, "updated": label, "length": len(value)}

    # Helper aliases for specific blocks (compatibility)
    def update_persona(self, persona: str) -> Dict:
        return self.update_block("persona", persona)
        
    def update_human(self, human_info: str) -> Dict:
        return self.update_block("human", human_info)

    def replace_in_block(self, label: str, old_str: str, new_str: str) -> Dict:
        """Replace specific text in a block (Letta memory_replace pattern)."""
        blocks = self.data["blocks"]
        if label not in blocks:
            return {"status": "error", "message": f"Block '{label}' not found. Available: {list(blocks.keys())}"}
        
        current = blocks[label].get("value", "")
        if old_str not in current:
            return {"status": "error", "message": f"Text '{old_str[:50]}...' not found in block '{label}'"}
        if current.count(old_str) > 1:
            return {"status": "error", "message": "Multiple matches found - be more specific with old_str"}
        
        new_value = current.replace(old_str, new_str, 1)
        limit = blocks[label].get("limit", 2000)
        if len(new_value) > limit:
            return {"status": "error", "message": f"Result exceeds limit ({len(new_value)}/{limit} chars)"}
        
        blocks[label]["value"] = new_value
        self.save()
        return {"status": "success", "block": label, "old_length": len(current), "new_length": len(new_value)}

    def insert_in_block(self, label: str, new_str: str, insert_line: int = -1) -> Dict:
        """Insert text at specific line in a block (Letta memory_insert pattern)."""
        blocks = self.data["blocks"]
        if label not in blocks:
            return {"status": "error", "message": f"Block '{label}' not found"}
        
        current = blocks[label].get("value", "")
        lines = current.split("\n") if current else []
        
        if insert_line == 0:
            lines.insert(0, new_str)
        elif insert_line == -1 or insert_line >= len(lines):
            lines.append(new_str)
        else:
            lines.insert(insert_line, new_str)
        
        new_value = "\n".join(lines)
        limit = blocks[label].get("limit", 2000)
        if len(new_value) > limit:
            return {"status": "error", "message": f"Result exceeds limit ({len(new_value)}/{limit} chars)"}
        
        blocks[label]["value"] = new_value
        self.save()
        return {"status": "success", "block": label, "new_length": len(new_value), "line_count": len(lines)}

    def conversation_search(self, query: str, limit: int = 5) -> Dict:
        """Search past conversation buffer (Letta conversation_search)."""
        results = []
        query_lower = query.lower()
        
        for msg in reversed(self.data["buffer"]):
            content = msg.get("content", "")
            if query_lower in content.lower():
                results.append({
                    "role": msg.get("role"),
                    "content": content,
                    "timestamp": msg.get("timestamp")
                })
                if len(results) >= limit:
                    break
        
        return {"status": "success", "query": query, "found": len(results), "messages": results}


    # =========================================================================
    # ARCHIVAL MEMORY (vector)
    # =========================================================================
    
    def remember(self, content: str, tags: List[str] = None, importance: int = 5) -> Dict:
        """Store in archival memory with embedding."""
        h = _hash(content)
        for mem in self.data["archival"]:
            if mem.get("hash") == h:
                return {"success": False, "error": "Duplicate memory"}
        
        vector = None
        if self.embedder:
            vector = self.embedder.get_embedding(content)
        
        memory = {
            "id": h,
            "hash": h,
            "content": content[:1000],
            "tags": (tags or [])[:5],
            "importance": min(max(importance, 1), 10),
            "created_at": _now_iso(),
            "accessed_at": _now_iso(),
            "access_count": 0,
            "embedding": vector
        }
        
        self.data["archival"].insert(0, memory)
        if len(self.data["archival"]) > MAX_ARCHIVAL:
            self.data["archival"].sort(key=lambda m: (m["importance"], m["access_count"]), reverse=True)
            self.data["archival"] = self.data["archival"][:MAX_ARCHIVAL]
        
        self.data["stats"]["memories_written"] += 1
        self.save()
        return {"success": True, "memory_id": h}
    
    def recall(self, query: str, limit: int = 5) -> Dict:
        """Search archival memory."""
        results = []
        if self.embedder:
            query_vec = self.embedder.get_embedding(query)
            if query_vec:
                for mem in self.data["archival"]:
                    score = 0
                    if mem.get("embedding"):
                        score = self.embedder.cosine_similarity(query_vec, mem["embedding"]) * 10
                    score += mem.get("importance", 5) / 10
                    if score > 0.1:
                        results.append({"memory": mem, "score": score})
                if results:
                    results.sort(key=lambda x: x["score"], reverse=True)
                    results = results[:limit]
                    self._mark_accessed(results)
                    self.data["stats"]["memories_read"] += 1
                    self.save()
                    return self._clean_results(results, query, "vector")

        # Fallback keyword
        query_lower = query.lower()
        query_words = set(query_lower.split())
        for mem in self.data["archival"]:
            content_lower = mem["content"].lower()
            tags_lower = [t.lower() for t in mem.get("tags", [])]
            score = 0
            for word in query_words:
                if word in content_lower: score += 2
                if any(word in tag for tag in tags_lower): score += 3
            score += mem.get("importance", 5) / 2
            if score > 0:
                results.append({"memory": mem, "score": score})
        
        results.sort(key=lambda x: x["score"], reverse=True)
        results = results[:limit]
        self._mark_accessed(results)
        self.data["stats"]["memories_read"] += 1
        self.save()
        return self._clean_results(results, query, "keyword")

    def _mark_accessed(self, results):
        for r in results:
            for mem in self.data["archival"]:
                if mem["id"] == r["memory"]["id"]:
                    mem["accessed_at"] = _now_iso()
                    mem["access_count"] = mem.get("access_count", 0) + 1
                    break

    def _clean_results(self, results, query, method):
        clean = []
        for r in results:
            m = r["memory"].copy()
            if "embedding" in m: del m["embedding"]
            clean.append(m)
        return {"query": query, "found": len(clean), "memories": clean, "method": method}
    
    def forget(self, memory_id: str) -> Dict:
        before = len(self.data["archival"])
        self.data["archival"] = [m for m in self.data["archival"] if m["id"] != memory_id]
        after = len(self.data["archival"])
        self.save()
        return {"success": before > after}
    
    def list_memories(self, limit: int = 10, page: int = 1, tag: str = None) -> Dict:
        memories = self.data["archival"]
        if tag:
            memories = [m for m in memories if tag.lower() in [t.lower() for t in m.get("tags", [])]]
        
        total_items = len(memories)
        total_pages = (total_items + limit - 1) // limit
        start = (page - 1) * limit
        end = start + limit
        
        view_memories = []
        for m in memories[start:end]:
            clean = m.copy()
            if "embedding" in clean: del clean["embedding"]
            view_memories.append(clean)
            
        return {
            "total_items": total_items,
            "total_pages": total_pages,
            "current_page": page,
            "memories": view_memories
        }

    # =========================================================================
    # CONVERSATION BUFFER
    # =========================================================================
    def add_to_buffer(self, role: str, content: str, metadata: Dict = None) -> None:
        self.data["buffer"].append({
            "role": role,
            "content": content[:500],
            "timestamp": _now_iso(),
            "metadata": metadata or {}
        })
        if len(self.data["buffer"]) > MAX_BUFFER:
            self.data["buffer"] = self.data["buffer"][-MAX_BUFFER:]
        self.save()

    def get_buffer(self, limit: int = 20) -> List[Dict]:
        return self.data["buffer"][-limit:]
    
    def clear_buffer(self) -> Dict:
        count = len(self.data["buffer"])
        self.data["buffer"] = []
        self.save()
        return {"cleared": count}

    def get_reflection_context(self) -> str:
        buffer_text = "\n".join(f"[{e['timestamp']}] {e['role']}: {e['content']}" for e in self.data["buffer"][-30:])
        return f"""
Recent Activity Buffer (Reflect on this):
{buffer_text}

Statistics:
- Archival memories: {len(self.data['archival'])}
- Memories written this session: {self.data["stats"]['memories_written']}

Current Memory Blocks:
{self.get_block_summary()}
"""

    def save_reflection(self, reflection: str) -> Dict:
        self.data["reflections"].insert(0, {"content": reflection[:2000], "timestamp": _now_iso()})
        self.data["reflections"] = self.data["reflections"][:50]
        self.data["stats"]["reflections_done"] += 1
        self.save()
        return {"success": True}


# ============================================================================
# MEMORY TOOL REGISTRATIONS
# ============================================================================

def register_memory_tools(agent, memory: AgentMemory) -> None:
    """Register Letta V2+ memory tools."""
    
    # ========== MEMORY BLOCK EDITING ==========
    
    agent.register_tool(
        name="memory_rethink",
        description="Completely rewrite a memory block's contents. Use when major reorganization needed.",
        parameters={
            "type": "object",
            "properties": {
                "label": {"type": "string", "description": "Block label (persona, human, scratchpad)"},
                "new_memory": {"type": "string", "description": "Complete new contents for the block"}
            },
            "required": ["label", "new_memory"]
        },
        handler=lambda label, new_memory: memory.update_block(label, new_memory)
    )
    
    agent.register_tool(
        name="memory_replace",
        description="Replace specific text in a memory block. old_str must match exactly.",
        parameters={
            "type": "object",
            "properties": {
                "label": {"type": "string", "description": "Block label"},
                "old_str": {"type": "string", "description": "Exact text to find and replace"},
                "new_str": {"type": "string", "description": "Replacement text"}
            },
            "required": ["label", "old_str", "new_str"]
        },
        handler=memory.replace_in_block
    )
    
    agent.register_tool(
        name="memory_insert",
        description="Insert text at a specific line in a memory block.",
        parameters={
            "type": "object",
            "properties": {
                "label": {"type": "string", "description": "Block label"},
                "new_str": {"type": "string", "description": "Text to insert"},
                "insert_line": {"type": "integer", "description": "Line number (0=beginning, -1=end)"}
            },
            "required": ["label", "new_str"]
        },
        handler=memory.insert_in_block
    )
    
    # ========== RECALL MEMORY ==========
    
    agent.register_tool(
        name="conversation_search",
        description="Search past messages in conversation buffer.",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What to search for"},
                "limit": {"type": "integer", "description": "Max results (default 5)"}
            },
            "required": ["query"]
        },
        handler=memory.conversation_search
    )
    
    # ========== ARCHIVAL MEMORY ==========
    
    agent.register_tool(
        name="archival_memory_insert",
        description="Store content in archival memory for long-term retrieval.",
        parameters={
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "Text to store"},
                "tags": {"type": "array", "items": {"type": "string"}, "description": "Optional tags for organization"},
                "importance": {"type": "integer", "description": "1-10 importance score"}
            },
            "required": ["content"]
        },
        handler=memory.remember
    )
    
    agent.register_tool(
        name="archival_memory_search",
        description="Search archival memory using semantic (embedding-based) search.",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What to search for"},
                "limit": {"type": "integer", "description": "Max results (default 5)"},
                "tags": {"type": "array", "items": {"type": "string"}, "description": "Optional tag filters"}
            },
            "required": ["query"]
        },
        handler=lambda query, limit=5, tags=None: memory.recall(query, limit)
    )
    
    agent.register_tool(
        name="list_memories",
        description="Browse archival memory with pagination.",
        parameters={
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Items per page (default 10)"},
                "page": {"type": "integer", "description": "Page number (1-indexed)"},
                "tag": {"type": "string", "description": "Filter by tag"}
            },
            "required": []
        },
        handler=memory.list_memories
    )
    
    # Legacy aliases for backward compatibility
    agent.register_tool(
        name="core_memory_replace",
        description="[DEPRECATED: Use memory_rethink] Replace entire block contents.",
        parameters={
            "type": "object",
            "properties": {
                "label": {"type": "string"},
                "value": {"type": "string"}
            },
            "required": ["label", "value"]
        },
        handler=memory.update_block
    )
    
    agent.register_tool(
        name="core_memory_append",
        description="[DEPRECATED: Use memory_insert] Append to a block.",
        parameters={
            "type": "object",
            "properties": {
                "label": {"type": "string"},
                "content": {"type": "string"}
            },
            "required": ["label", "content"]
        },
        handler=lambda label, content: memory.insert_in_block(label, content, -1)
    )

    log.info("Registered Letta V2+ memory tools: memory_rethink, memory_replace, memory_insert, conversation_search, archival_memory_insert/search")

