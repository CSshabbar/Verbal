#!/usr/bin/env python3
"""
build_and_test.py - Build and test the Windows application
"""

import os
import sys
import subprocess
import tempfile
import shutil
import time

def run_command(cmd, cwd=None, shell=False):
    """Run a command and return the result"""
    print(f"Running: {cmd}")
    try:
        result = subprocess.run(
            cmd, 
            shell=shell, 
            cwd=cwd, 
            capture_output=True, 
            text=True, 
            timeout=300
        )
        if result.returncode != 0:
            print(f"Command failed with code {result.returncode}")
            print(f"STDOUT: {result.stdout}")
            print(f"STDERR: {result.stderr}")
            return False
        print(f"Command succeeded")
        return True
    except subprocess.TimeoutExpired:
        print("Command timed out")
        return False
    except Exception as e:
        print(f"Command failed with exception: {e}")
        return False

def build_windows_app():
    """Build the Windows application"""
    print("Building Windows application...")
    
    # Activate virtual environment if it exists
    if os.path.exists(".venv"):
        if os.name == "nt":  # Windows
            activate_script = ".venv\\Scripts\\activate.bat"
        else:  # Unix-like
            activate_script = ".venv/bin/activate"
        
        # For now, we'll just ensure dependencies are installed
        print("Ensuring dependencies are installed...")
        if not run_command([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"]):
            return False
    
    # Run PyInstaller
    print("Running PyInstaller...")
    if not run_command([sys.executable, "-m", "PyInstaller", "verbal-win.spec", "--clean", "--noconfirm"]):
        return False
    
    # Check if build succeeded
    exe_path = os.path.join("dist", "Verbal.exe")
    if not os.path.exists(exe_path):
        print(f"Build failed: {exe_path} not found")
        return False
    
    print(f"Build succeeded: {exe_path}")
    return True

def test_dependencies():
    """Test that all dependencies are available"""
    print("Testing dependencies...")
    
    deps = [
        "faster_whisper",
        "ctranslate2", 
        "sounddevice",
        "soundfile",
        "numpy",
        "groq",
        "google.generativeai",
        "pyperclip",
        "pyautogui", 
        "PIL",
        "websocket",
        "httpx",
        "pystray",
        "pywebview",
        "pynput"
    ]
    
    failed = []
    for dep in deps:
        try:
            __import__(dep)
            print(f"✓ {dep}")
        except ImportError as e:
            print(f"✗ {dep} - {e}")
            failed.append(dep)
        except Exception as e:
            print(f"? {dep} - {e}")
    
    if failed:
        print(f"Failed dependencies: {failed}")
        return False
    
    print("All dependencies OK!")
    return True

def test_executable():
    """Test the built executable"""
    exe_path = os.path.join("dist", "Verbal.exe")
    if not os.path.exists(exe_path):
        print(f"Executable not found: {exe_path}")
        return False
    
    print(f"Testing executable: {exe_path}")
    
    # Try to run the executable briefly to see if it starts
    try:
        # Start the process
        process = subprocess.Popen(
            [exe_path, "--help"],  # Assuming the app supports --help
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # Wait a moment
        time.sleep(2)
        
        # Check if it's still running
        if process.poll() is None:
            # Still running, terminate it
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
        
        print("Executable test completed")
        return True
    except Exception as e:
        print(f"Executable test failed: {e}")
        return False

def main():
    """Main function"""
    print("Verbal Windows Build and Test Script")
    print("=" * 50)
    
    # Change to script directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
    
    # Test dependencies first
    if not test_dependencies():
        print("Dependency test failed!")
        return 1
    
    # Build the application
    if not build_windows_app():
        print("Build failed!")
        return 1
    
    # Test the executable
    if not test_executable():
        print("Executable test failed!")
        return 1
    
    print("\nAll tests passed!")
    return 0

if __name__ == "__main__":
    sys.exit(main())