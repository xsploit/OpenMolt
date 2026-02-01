"""
Sleep/Dream Agent using Open Responses client.
Uses the same agent loop and Open Responses schema as the main agent.
Supports separate model/provider configuration for sleep-time compute.
"""
import logging
from typing import Any, Dict

log = logging.getLogger(__name__)


def run_dream_cycle(agent, memory, config: Dict[str, Any] = None) -> None:
    """
    Run a 'dream' cycle: Letta-style sleep-time compute.
    The agent reflects on recent events to consolidate long-term memory.
    
    Uses the same Open Responses agent loop pattern as the main agent.
    If sleep_model or sleep_use_ollama is set in config, creates a separate
    client with those settings while maintaining the Open Responses schema.
    
    Args:
        agent: Main agent (used if no separate sleep config)
        memory: AgentMemory instance
        config: Config dict (if provided, can specify separate sleep model)
    """
    log.info("💤 Entering REM sleep (Dream Cycle)...")
    
    # Check if we have enough buffer to dream
    buffer = memory.get_buffer(limit=50)
    if len(buffer) < 3:
        log.info("Not enough recent activity to dream.")
        return

    # Build dream prompt
    reflection_context = memory.get_reflection_context()
    prompt = f"""# SLEEP CYCLE - Memory Consolidation

You are entering a sleep cycle. You are 'dreaming' about your recent experiences.
Your goal is to CONSOLIDATE MEMORY.

{reflection_context}

## Instructions
1. Analyze the 'Recent Activity Buffer'.
2. Extract key facts, user preferences, or relationship details.
3. Summarize what you learned from recent interactions.
4. Identify any important information that should be remembered long-term.
5. If nothing significant happened, briefly note your general observations.

Respond with a concise reflection (2-3 paragraphs max).
"""

    log.info("Dreaming...")
    
    try:
        # Use separate sleep model if configured
        if config and config.get("sleep_model"):
            from openresponses.client import OpenResponsesClient
            
            if config.get("sleep_use_ollama", not config.get("brain_use_openrouter", False)):
                # Build sleep-specific config
                sleep_config = {
                    "ollama_base_url": config.get("ollama_base_url", "http://localhost:11434/v1"),
                    "ollama_model": config.get("sleep_model"),
                    "ollama_options": config.get("ollama_options", {}),
                    "ollama_num_ctx": config.get("ollama_num_ctx"),
                }
                sleep_client = OpenResponsesClient.from_config(sleep_config)
            else:
                # Use OpenRouter with sleep model
                sleep_client = OpenResponsesClient.openrouter(
                    api_key=config.get("openrouter_api_key"),
                    model=config.get("sleep_model")
                )
            
            log.info(f"Using sleep model: {config.get('sleep_model')}")
            response_obj = sleep_client.create_response(input=prompt)
            response = response_obj.get_text() or ""
        else:
            # Use main agent's think method (preserves agent loop)
            response = agent.think(prompt)
        
        log.info(f"Dream result: {response[:300]}...")
        
        # Save reflection
        memory.save_reflection(response)
        
        # Clear buffer (we've processed it)
        count = memory.clear_buffer()
        log.info(f"Woke up. Consolidations complete. Cleared {count['cleared']} buffer entries.")
        
    except Exception as e:
        log.error(f"Nightmare (Dream error): {e}")
