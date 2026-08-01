import time
import logging
import sys
from app.recorder import Recorder
from app.config import load_config
from app.transcriber import transcribe
from app.ai_cleanup import process_text
from app.linux_injector import inject_text

logging.basicConfig(level=logging.INFO)

def run_pipeline():
    config = load_config()
    recorder = Recorder()
    
    print("\n--- RECORDING IN 3 SECONDS... GET READY ---")
    time.sleep(3)
    
    print(">>> RECORDING STARTED (SPEAK NOW) <<<")
    recorder.start()
    time.sleep(5) # record for 5 seconds
    
    print(">>> RECORDING STOPPED <<<")
    audio = recorder.stop()
    
    if audio is None or len(audio) < 8000:
        print("ERROR: No audio captured (silence or too short).")
        return False
        
    print(f"Captured {len(audio)} audio samples.")
    print("Transcribing...")
    
    text = transcribe(audio, config, recorder.sample_rate)
    if not text:
        print("ERROR: Transcription returned empty.")
        return False
        
    print(f"Transcription: {text}")
    print("Processing via AI...")
    
    processed = process_text(text, config)
    print(f"Processed Text: {processed}")
    
    print("Attempting to inject (paste)...")
    outcome = inject_text(processed)
    if outcome.paste_sent:
        print("SUCCESS! Pipeline works.")
        return True
    if outcome.copied:
        print("PARTIAL: Text is on the clipboard, but the paste keystroke failed.")
    else:
        print("ERROR: Clipboard copy and injection failed.")
    return False

if __name__ == "__main__":
    sys.exit(0 if run_pipeline() else 1)
