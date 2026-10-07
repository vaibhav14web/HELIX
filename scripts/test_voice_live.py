import asyncio
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from foundation.event_bus.event_bus import EventBus
from core_ai.voice_engine.voice_engine import VoiceEngine

async def test_live_voice():
    # Load .env settings
    load_dotenv(ROOT / ".env")
    
    # Force configurations
    os.environ["HELIX_VOICE_BACKEND"] = "mock"
    os.environ["HELIX_VOICE_STT_BACKEND"] = "faster_whisper"
    os.environ["HELIX_VOICE_TTS_BACKEND"] = "piper"
    os.environ["HELIX_VOICE_TTS_MODEL"] = "piper"
    os.environ["HELIX_VOICE_TTS_MODEL_PATH"] = r"C:\Users\vaibh\Documents\HELIX_MODELS\PIPER\zh_CN-huayan-medium.onnx"
    
    event_bus = EventBus()
    engine = VoiceEngine(event_bus)
    
    print("Starting Voice Engine with Piper backend...")
    print(f"TTS Backend: {engine._tts_backend}")
    print(f"TTS Model Path: {os.getenv('HELIX_VOICE_TTS_MODEL_PATH')}")
    
    await engine.start()
    
    try:
        # Test: Voice Synthesis
        print("\n--- Synthesizing Text 'Hello Helix, integration test' ---")
        text = "Hello Helix, integration test"
        audio_bytes = await engine.synthesize(text)
        print(f"Synthesis successful! Generated audio size: {len(audio_bytes)} bytes")
        
        if len(audio_bytes) > 0:
            print("Voice Synthesis is fully functional!")
        else:
            print("WARNING: Generated audio bytes is empty.")
            
    except Exception as e:
        print(f"Error during voice synthesis test: {e}")
    finally:
        # Stop capture
        engine._capture.stop()

if __name__ == "__main__":
    asyncio.run(test_live_voice())
