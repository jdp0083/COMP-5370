import os
import subprocess

TIMEOUT = 10 # 10 seconds allowed for each testcase

VALID_TC = [
        ('spec-testcases/valid/0001.input', 'spec-testcases/valid/0001.output'),
        ('spec-testcases/valid/0002.input', 'spec-testcases/valid/0002.output'),
        ('spec-testcases/valid/0003.input', 'spec-testcases/valid/0003.output'),
        ('spec-testcases/valid/0004.input', 'spec-testcases/valid/0004.output'),
        ('spec-testcases/valid/0005.input', 'spec-testcases/valid/0005.output'),
        ('spec-testcases/valid/0006.input', 'spec-testcases/valid/0006.output'),
        ('spec-testcases/valid/0007.input', 'spec-testcases/valid/0007.output'),
        ('spec-testcases/valid/0008.input', 'spec-testcases/valid/0008.output'),
        ('spec-testcases/valid/0009.input', 'spec-testcases/valid/0009.output'),
        ('spec-testcases/valid/0010.input', 'spec-testcases/valid/0010.output'),
        ('spec-testcases/valid/0011.input', 'spec-testcases/valid/0011.output'),
        ]

INVALID_TC = [
        'spec-testcases/invalid/0001.input',
        'spec-testcases/invalid/0002.input',
        'spec-testcases/invalid/0003.input',
        ]

def check_valid(inputPath, outputPath):
    try:
        res = subprocess.run(
                ['make', 'run', 'FILE='+inputPath],
                capture_output=True,
                timeout=TIMEOUT,
                )
    except subprocess.TimeoutExpired:
        # Likely infinite loop but not guaranteed
        return False

    if res.returncode != 0:
        return False

    if len(res.stderr) != 0:
        return False

    got = res.stdout
    with open(outputPath, 'rb') as handle:
        want = handle.read()
    if got != want:
        return False

    return True

def check_invalid(inputPath):
    try:
        res = subprocess.run(
                ['make', 'run', 'FILE='+inputPath],
                capture_output=True,
                timeout=TIMEOUT,
                )
    except subprocess.TimeoutExpired:
        # Likely infinite loop but not guaranteed
        return False

    if len(res.stderr) == 0:
        return False

    stderrLines = res.stderr.split(b'\n')

    if len(stderrLines) < 3:
        return False

    if not stderrLines[-2].startswith(b'make:'):
        return False

    if not stderrLines[-2].endswith(b'Error 66'):
        return False

    if len(stderrLines[0]) < 9: # Prefix string length
        return False

    assert(type(res.stderr) == bytes), type(res.stderr)
    if stderrLines[0][:9] != b'ERROR -- ':
        return False

    return True

def main():
    errors = []

    for tc in VALID_TC:
        if not check_valid(tc[0], tc[1]):
            errors.append('incorrect handling of valid file: '+tc[0])
        else:
            print('OK --', tc[0])

    for tc in INVALID_TC:
        if not check_invalid(tc):
            errors.append('incorrect handling of invalid file: '+tc)
        else:
            print('OK --', tc)

    for error in errors:
        print('ERROR --', error)

main()
