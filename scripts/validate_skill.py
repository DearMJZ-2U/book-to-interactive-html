#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Validate this skill's own frontmatter. Run it after editing SKILL.md.

    python scripts/validate_skill.py

Catches the two failures that produce NO error message anywhere:
  - a ": " inside the unquoted description breaks the YAML and the skill
    silently never loads (pitfall G3)
  - a capital or underscore in `name` violates the spec (pitfall G4)

The only symptom of either is "the skill is not in my catalog".
"""
import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.join(os.path.dirname(HERE), "SKILL.md")

t = open(SKILL, encoding="utf-8").read()
if not t.startswith("---"):
    sys.exit("!! SKILL.md does not start with YAML frontmatter")
fm = t.split("---", 2)[1]

fail = 0


def check(cond, msg):
    global fail
    print(("  [ok]   " if cond else "  [FAIL] ") + msg)
    if not cond:
        fail += 1


try:
    import yaml
    d = yaml.safe_load(fm)
    check(isinstance(d, dict), "frontmatter parses as YAML")
    name = (d or {}).get("name", "")
    desc = (d or {}).get("description", "")
except ImportError:
    sys.exit("!! PyYAML not installed:  pip install pyyaml")
except Exception as e:
    print("  [FAIL] frontmatter does not parse: %s: %s" % (type(e).__name__, e))
    print("         a colon-space inside an unquoted description is the usual cause (G3)")
    sys.exit(1)

check(bool(name), "name is present")
check(bool(re.match(r"^[a-z0-9]+(-[a-z0-9]+)*$", name or "")),
      "name is lowercase-kebab (%r)" % name)
check(len(name or "") <= 64, "name <= 64 chars (%d)" % len(name or ""))
check(bool(desc.strip()), "description is non-empty")
check(len(desc or "") <= 1024, "description <= 1024 chars (%d)" % len(desc or ""))
check(os.path.basename(os.path.dirname(SKILL)) == name,
      "directory name matches name (%s)" % os.path.basename(os.path.dirname(SKILL)))

print("")
print("%d problem(s)" % fail)
sys.exit(1 if fail else 0)