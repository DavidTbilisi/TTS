import subprocess, sys, os
os.chdir(r'D:\Code\python\TTS')
r = subprocess.run(
    [sys.executable, '-m', 'pytest', 'tests/', '-v', '--tb=short', '--no-header', '-p', 'no:warnings',
     '--ignore=tests/test_audio.py',
     '--ignore=tests/test_fast_audio.py',
     '--ignore=tests/test_main.py',
     '--ignore=tests/test_rich_progress.py',
     '--ignore=tests/test_simple_help.py',
     '--ignore=tests/test_ultra_fast.py',
    ],
    capture_output=True, text=True, timeout=120
)
with open('test_results2.txt', 'w') as f:
    f.write(r.stdout)
    f.write('\n--- STDERR ---\n')
    f.write(r.stderr)
    f.write(f'\nEXIT CODE: {r.returncode}\n')
print('Done. Exit code:', r.returncode)
