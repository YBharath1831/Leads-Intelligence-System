#!/usr/bin/env python3
"""
Launcher script for the Lead Intelligence System Streamlit UI
"""
import subprocess
import sys
import os
from pathlib import Path

def main():
    # Get the directory where this script is located
    ui_dir = Path(__file__).parent.absolute()
    
    # Path to the Streamlit app
    app_path = ui_dir / "app.py"
    
    # Change to the UI directory
    os.chdir(ui_dir)
    
    # Run streamlit
    try:
        subprocess.run([
            sys.executable, "-m", "streamlit", "run", str(app_path),
            "--server.port", "8501",
            "--server.address", "localhost"
        ])
    except KeyboardInterrupt:
        print("\nShutting down Lead Intelligence System UI...")
    except Exception as e:
        print(f"Error running Streamlit: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()