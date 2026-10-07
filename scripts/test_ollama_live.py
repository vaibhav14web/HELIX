import asyncio
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from foundation.event_bus.event_bus import EventBus
from core_ai.llm_engine.llm_engine import LLMEngine

async def test_live_ollama():
    # Load .env settings
    load_dotenv(ROOT / ".env")
    
    # Ensure backend is set to ollama
    os.environ["HELIX_LLM_BACKEND"] = "ollama"
    
    event_bus = EventBus()
    engine = LLMEngine(event_bus)
    
    print("Starting LLM Engine with Ollama backend...")
    print(f"Ollama URL: {os.getenv('HELIX_LLM_OLLAMA_URL', 'http://localhost:11434')}")
    print(f"Orchestrator Model: {os.getenv('HELIX_LLM_ORCHESTRATOR_MODEL_NAME', 'qwen3:4b')}")
    print(f"Coder Model: {os.getenv('HELIX_LLM_CODER_MODEL_NAME', 'qwen2.5-coder:3b')}")
    
    await engine.start()
    
    try:
        # Test 1: Orchestrator Model
        print("\n--- Testing Orchestrator Model ---")
        prompt = "Explain in one short sentence what is artificial intelligence."
        print(f"Prompt: {prompt}")
        response = await engine.generate(prompt, is_coding=False)
        print(f"Response: {response}")
        
        # Test 2: Coder Model
        print("\n--- Testing Coder Model ---")
        coding_prompt = "Write a python function to add two numbers."
        print(f"Prompt: {coding_prompt}")
        coding_response = await engine.generate(coding_prompt, is_coding=True)
        print(f"Response:\n{coding_response}")
        
    except Exception as e:
        print(f"Error during test: {e}")
    finally:
        await engine.stop()

if __name__ == "__main__":
    asyncio.run(test_live_ollama())
