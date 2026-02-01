import logging
from typing import Any

log = logging.getLogger(__name__)

# ============================================================================
# SLEEP / DREAM CYCLE
# ============================================================================

def run_dream_cycle(agent, memory) -> None:
    """
    Run a 'dream' cycle: Letta-style sleep-time compute.
    The agent reflects on recent events to consolidate long-term memory.
    """
    log.info("💤 Entering REM sleep (Dream Cycle)...")
    
    # Check if we have enough buffer to dream
    buffer = memory.get_buffer(limit=50)
    if len(buffer) < 3:
        log.info("Not enough recent activity to dream.")
        return

    # Build dream prompt
    reflection_context = memory.get_reflection_context()
    prompt = f"""
SYSTEM: You are entering a sleep cycle. You are 'dreaming' about your recent experiences.
Your goal is to CONSOLIDATE MEMORY.

{reflection_context}

INSTRUCTIONS:
1. Analyze the 'Recent Activity Buffer'.
2. extract key facts, user preferences, or relationship details.
3. Update your core memory blocks using 'core_memory_replace' or 'core_memory_append' (labels: persona, human, scratchpad).
4. Save lasting facts to long-term storage using 'archival_memory_insert'.
5. If nothing is worth saving, just reflect on your general state.
6. Finish by summarizing what you learned.

You have access to all your memory tools. ACT NOW to update your mind.
"""

    log.info("Dreaming...")
    # Run agent in a special loop just for thinking/memory tools
    
    try:
        response = agent.think(prompt)
        log.info(f"Dream result: {response[:300]}...")
        
        # Save reflection
        memory.save_reflection(response)
        
        # Clear buffer (we've processed it)
        count = memory.clear_buffer()
        log.info(f"Woke up. Consolidations complete. Cleared {count['cleared']} buffer entries.")
        
    except Exception as e:
        log.error(f"Nightmare (Dream error): {e}")
