#!/usr/bin/env python3
"""mutate.py - every rule of the gate switched off in turn, and the tests must notice.

tests/plants.tsv lists one change per line: a file, a line of it, what it
becomes, and the test in tests/test_evidence.py that must then fail. Each
change is made to a copy of the scripts, never to the scripts themselves;
the test suite is run against that copy (SCRIPTS_DIR), and the named test
must fail. A change whose text is not found exactly once is an error: a
plant that no longer applies proves nothing.

The unchanged scripts are run first and must pass. Exits 1 if any plant was
not caught, 2 if a plant cannot be applied.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def suite(scripts_dir, test=None):
    cmd = [sys.executable, "-m", "unittest"]
    cmd += [f"test_evidence.{test}"] if test else ["test_evidence"]
    env = dict(os.environ, SCRIPTS_DIR=scripts_dir)
    p = subprocess.run(cmd, cwd=os.path.join(ROOT, "tests"), env=env, capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def main():
    code, out = suite(os.path.join(ROOT, "scripts"))
    if code != 0:
        print(out)
        print("the unchanged scripts fail their own tests; nothing to measure")
        sys.exit(1)
    plants = []
    for line in open(os.path.join(ROOT, "tests", "plants.tsv")):
        if line.startswith("#") or not line.strip():
            continue
        plants.append([json.loads(f) for f in line.rstrip("\n").split("\t")])
    missed = []
    for path, old, new, test, what in plants:
        tmp = tempfile.mkdtemp()
        try:
            # A copy of the repository's tree, with the scripts copied and the
            # rest linked, so each script still finds the files beside it.
            for name in os.listdir(ROOT):
                if name in (".git", "scripts"):
                    continue
                os.symlink(os.path.join(ROOT, name), os.path.join(tmp, name))
            shutil.copytree(os.path.join(ROOT, "scripts"), os.path.join(tmp, "scripts"))
            target = os.path.join(tmp, path)
            text = open(target).read()
            if text.count(old) != 1:
                print(f"PLANT DOES NOT APPLY: {path}: {what} ({text.count(old)} matches)")
                sys.exit(2)
            open(target, "w").write(text.replace(old, new))
            code, out = suite(os.path.join(tmp, "scripts"), test)
            caught = code != 0
            print(f"{'caught' if caught else 'MISSED'}: {what} ({path}; {test})")
            if not caught:
                missed.append(what)
        finally:
            shutil.rmtree(tmp)
    print(f"== {len(plants) - len(missed)} of {len(plants)} plants caught")
    sys.exit(1 if missed else 0)


if __name__ == "__main__":
    main()
