import subprocess
import sys
import os

# Get the path to the directory this script is in
script_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(script_dir)

# Run uvicorn with no console
startupinfo = subprocess.STARTUPINFO()
startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
startupinfo.wShowWindow = 0  # SW_HIDE

subprocess.Popen(
    ["uvicorn", "app.main:app", "--port", "8383"],
    startupinfo=startupinfo
)