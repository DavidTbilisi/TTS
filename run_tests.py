import subprocess, sys, os
os.chdir(r'D:\Code\python\TTS')
r = subprocess.run(
    [sys.executable, '-m', 'pytest', 'tests/', '-v', '--tb=short', '--no-header', '-p', 'no:warnings'],
    capture_output=True, text=True, timeout=120
)
with open('test_results.txt', 'w') as f:
    f.write(r.stdout)
    f.write('\n--- STDERR ---\n')
    f.write(r.stderr)
    f.write(f'\nEXIT CODE: {r.returncode}\n')
print('Done. Exit code:', r.returncode)
