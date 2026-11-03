#!/usr/bin/env python3
"""Every static check, shown the violation it exists for, has to fail.

    python3 tests/static/plant_violations.py

A check that cannot fail is not a check. Each line of tests/static/plants.tsv
names a file, a piece of it, its replacement, and the check in
scripts/validate.sh that must catch it: a component definition edited by
hand, a node that is not the flagship's, a model server unlike the
flagship's, an image by tag, a document trestle refuses, a gate rule
switched off, a gate rule changed without its mutation. Each plant goes into
its own copy of the repository; the run fails if the named check stays
green, or if the text a plant breaks is no longer in the file (a stale plant
would prove nothing while looking like a pass).

Run scripts/validate.sh first: the untouched tree has to pass every check.
The copies take the flagship's release and NIST's catalogs from .cache; the
downloaded tools (.cache/bin), the cluster run's state (.cache/run) and the
virtual environment are left out, since no static check reads them.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def ignore(directory, names):
    rel = os.path.relpath(directory, ROOT)
    skip = {".git", "out", ".venv", "__pycache__"}
    if rel == ".cache":
        skip |= {"bin", "run"}
    return [n for n in names if n in skip]


def main():
    plants = []
    with open(os.path.join(ROOT, "tests", "static", "plants.tsv"), encoding="utf-8") as f:
        for line in f:
            if line.startswith("#") or not line.strip():
                continue
            plants.append([json.loads(x) for x in line.rstrip("\n").split("\t")])
    missed = stale = 0
    for fname, old, new, check, what in plants:
        work = tempfile.mkdtemp(prefix="plant-")
        try:
            shutil.copytree(ROOT, work, dirs_exist_ok=True, symlinks=True, ignore=ignore)
            path = os.path.join(work, fname)
            text = open(path, encoding="utf-8").read() if os.path.exists(path) else ""
            if old not in text:
                print("  STALE   %-10s %s: the text it breaks is no longer in %s" % (check, what, fname))
                stale += 1
                continue
            open(path, "w", encoding="utf-8").write(text.replace(old, new, 1))
            r = subprocess.run(["bash", os.path.join(work, "scripts", "validate.sh"), check],
                               capture_output=True, text=True, cwd=work)
            if "-- %s: FAILED" % check in r.stdout:
                print("  caught  %-10s %s" % (check, what))
            else:
                print("  MISSED  %-10s %s" % (check, what))
                print("\n".join("          " + l for l in (r.stdout + r.stderr).splitlines()[-15:]))
                missed += 1
        finally:
            shutil.rmtree(work, ignore_errors=True)
    print("%d plants: %d caught, %d missed, %d stale" % (len(plants), len(plants) - missed - stale, missed, stale))
    sys.exit(1 if (missed or stale) else 0)


if __name__ == "__main__":
    main()
