"""
Unified Embeddings Client.
Supports Ollama, OpenAI, and OpenRouter for generating vector embeddings.
"""
import requests
import numpy as np
import logging
from typing import List, Optional, Dict, Any

log = logging.getLogger(__name__)

class EmbeddingClient:
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize based on config.
        """
        self.config = config
        self.provider = "ollama"
        self.base_url = "http://localhost:11434"
        self.model = "qwen3:0.5b" # Default fallback
        self.api_key = None

        if config.get("brain_use_openrouter"):
            self.provider = "openrouter"
            self.base_url = "https://openrouter.ai/api/v1"
            self.model = config.get("openrouter_model", "openai/text-embedding-3-small") # OR usually proxies OpenAI for embeddings
            self.api_key = config.get("openrouter_api_key")
        elif config.get("brain_use_openai"):
            self.provider = "openai"
            self.base_url = "https://api.openai.com/v1"
            self.model = config.get("openai_embedding_model", "text-embedding-3-small")
            self.api_key = config.get("openai_api_key")
        else:
            # Local Ollama
            self.provider = "ollama"
            self.base_url = (config.get("ollama_base_url") or "http://localhost:11434").rstrip("/")
            # Use specific embedding model if user requested, otherwise qwen3-embedding:0.6b (which is effectively qwen3:0.5b in some registries, but let's stick to user request)
            self.model = config.get("ollama_embedding_model", "qwen3-embedding:0.6b")

        log.info(f"Embeddings initialized: Provider={self.provider}, Model={self.model}")

    def get_embedding(self, text: str) -> Optional[List[float]]:
        """Get vector embedding for a single string."""
        if not text or not text.strip():
            return None
        
        try:
            if self.provider == "ollama":
                return self._get_ollama_embedding(text)
            else:
                return self._get_openai_atyle_embedding(text)
        except Exception as e:
            log.warning(f"Embedding failed ({self.provider}): {e}")
            return None

    def _get_ollama_embedding(self, text: str) -> List[float]:
        url = f"{self.base_url}/api/embeddings"
        # Ollama /api/embeddings endpoint
        response = requests.post(
            url, 
            json={"model": self.model, "prompt": text},
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
        return data.get("embedding")

    def _get_openai_atyle_embedding(self, text: str) -> List[float]:
        # OpenAI / OpenRouter style /v1/embeddings
        url = f"{self.base_url}/embeddings"
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        if self.provider == "openrouter":
            headers["HTTP-Referer"] = "https://openmolt.com"
            headers["X-Title"] = "OpenMolt Agent"
            
        response = requests.post(
            url,
            headers=headers,
            json={"model": self.model, "input": text},
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
        
        # Extract embedding from standard OpenAI format
        # {"data": [{"embedding": [...]}]}
        if "data" in data and len(data["data"]) > 0:
            return data["data"][0]["embedding"]
        return None

    def cosine_similarity(self, v1: List[float], v2: List[float]) -> float:
        """Calculate cosine similarity between two vectors."""
        if not v1 or not v2:
            return 0.0
        
        # Convert to numpy arrays if not already
        a = np.array(v1)
        b = np.array(v2)
        
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        
        if norm_a == 0 or norm_b == 0:
            return 0.0
            
        return float(np.dot(a, b) / (norm_a * norm_b))
