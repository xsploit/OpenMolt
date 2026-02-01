"""
Unified Embeddings Client with Independent Provider Selection.
Supports Ollama, OpenAI, and OpenRouter for generating vector embeddings.

Config options (explicit override for embeddings):
  - embedding_use_ollama: true/false (forces Ollama even if brain uses OpenRouter)
  - embedding_use_openrouter: true/false (forces OpenRouter)
  - embedding_model: Override model name (e.g., "nomic-embed-text", "text-embedding-3-small")

If no explicit embedding_* settings, falls back to brain provider settings.
"""
import requests
import numpy as np
import logging
from typing import List, Optional, Dict, Any

log = logging.getLogger(__name__)


class EmbeddingClient:
    """
    Vector embedding client with independent provider configuration.
    Same pattern as brain/sleep agents but for embeddings.
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self._configure_provider()
        log.info(f"Embeddings initialized: Provider={self.provider}, Model={self.model}")

    def _configure_provider(self):
        """Determine provider based on explicit embedding config or brain fallback."""
        config = self.config
        
        # ========== EXPLICIT EMBEDDING PROVIDER ==========
        # These take priority over brain settings
        
        if config.get("embedding_use_ollama"):
            # Explicit: Use Ollama for embeddings
            self.provider = "ollama"
            base = config.get("ollama_base_url", "http://localhost:11434")
            self.base_url = base.rstrip("/").replace("/v1", "")  # Ollama native API
            self.model = config.get("embedding_model", config.get("ollama_embedding_model", "qwen3-embedding:0.6b"))
            self.api_key = None
            return
        
        if config.get("embedding_use_openrouter"):
            # Explicit: Use OpenRouter for embeddings
            self.provider = "openrouter"
            self.base_url = "https://openrouter.ai/api/v1"
            self.model = config.get("embedding_model", "openai/text-embedding-3-small")
            self.api_key = config.get("openrouter_api_key")
            return
        
        if config.get("embedding_use_openai"):
            # Explicit: Use OpenAI for embeddings
            self.provider = "openai"
            self.base_url = "https://api.openai.com/v1"
            self.model = config.get("embedding_model", "text-embedding-3-small")
            self.api_key = config.get("openai_api_key")
            return
        
        # ========== FALLBACK TO BRAIN PROVIDER ==========
        
        if config.get("brain_use_openrouter"):
            self.provider = "openrouter"
            self.base_url = "https://openrouter.ai/api/v1"
            self.model = config.get("embedding_model", "openai/text-embedding-3-small")
            self.api_key = config.get("openrouter_api_key")
        elif config.get("brain_use_openai"):
            self.provider = "openai"
            self.base_url = "https://api.openai.com/v1"
            self.model = config.get("embedding_model", "text-embedding-3-small")
            self.api_key = config.get("openai_api_key")
        else:
            # Default: Local Ollama
            self.provider = "ollama"
            base = config.get("ollama_base_url", "http://localhost:11434")
            self.base_url = base.rstrip("/").replace("/v1", "")
            self.model = config.get("embedding_model", config.get("ollama_embedding_model", "qwen3-embedding:0.6b"))
            self.api_key = None

    def get_embedding(self, text: str) -> Optional[List[float]]:
        """Get vector embedding for a single string."""
        if not text or not text.strip():
            return None
        
        try:
            if self.provider == "ollama":
                return self._get_ollama_embedding(text)
            else:
                return self._get_openai_style_embedding(text)
        except Exception as e:
            log.warning(f"Embedding failed ({self.provider}): {e}")
            return None

    def _get_ollama_embedding(self, text: str) -> List[float]:
        """Ollama /api/embeddings endpoint (native API, not OpenAI-compat)."""
        url = f"{self.base_url}/api/embeddings"
        response = requests.post(
            url, 
            json={"model": self.model, "prompt": text},
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
        return data.get("embedding")

    def _get_openai_style_embedding(self, text: str) -> List[float]:
        """OpenAI / OpenRouter style /v1/embeddings endpoint."""
        url = f"{self.base_url}/embeddings"
        headers = {
            "Authorization": f"Bearer {self.api_key}", 
            "Content-Type": "application/json"
        }
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
        
        a = np.array(v1)
        b = np.array(v2)
        
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        
        if norm_a == 0 or norm_b == 0:
            return 0.0
            
        return float(np.dot(a, b) / (norm_a * norm_b))
