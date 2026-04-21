import subprocess
r = subprocess.run(
    ["py", "-m", "pip", "install", "-e", "."],
    capture_output=True, text=True, cwd=r"D:\Code\python\TTS"
)
print(r.stdout)
print(r.stderr)
