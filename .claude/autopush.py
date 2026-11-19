#!/usr/bin/env python3
"""
Claude Code "Stop" hook: after every Claude reply, save what changed in the
picade folder to git and upload it to GitHub.

- Nothing changed? Then it does nothing.
- Scores and settings never go up (see .gitignore).
- No GitHub link set up yet, or no internet? The change is still saved
  locally and goes up with the next successful push.
Prints one short line for the Claude Code window (as {"systemMessage": ...}).
"""
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRAILER = "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"


def git(*args, timeout=60):
    return subprocess.run(["git", "-C", ROOT] + list(args), capture_output=True,
                          text=True, timeout=timeout)


def say(text):
    print(json.dumps({"systemMessage": text}))


def main():
    if git("rev-parse", "--is-inside-work-tree").returncode != 0:
        return                                            # not a git repository (any more)
    git("add", "-A")
    changed = [l[3:] for l in git("status", "--porcelain").stdout.splitlines() if l.strip()]
    committed = False
    if changed:
        names = sorted({c.split("/")[0] if "/" in c else c for c in changed})
        title = "Update %s" % ", ".join(names[:4]) + (" and more" if len(names) > 4 else "")
        body = "Changed files:\n" + "\n".join("- " + c for c in changed[:40])
        r = git("commit", "-q", "-m", title, "-m", body, "-m", TRAILER)
        if r.returncode != 0:
            say("Auto-save: commit failed: %s" % (r.stderr.strip() or r.stdout.strip())[:200])
            return
        committed = True
    if not git("remote").stdout.strip():
        if committed:
            say("Auto-save: saved locally (%d file%s) - no GitHub link set up yet."
                % (len(changed), "" if len(changed) == 1 else "s"))
        return
    ahead = git("rev-list", "--count", "@{u}..HEAD")
    if not committed and ahead.returncode == 0 and ahead.stdout.strip() == "0":
        return                                            # nothing new, nothing waiting
    try:
        r = git("push", "-u", "origin", "HEAD", timeout=90)
    except subprocess.TimeoutExpired:
        say("Auto-save: saved locally; GitHub upload timed out (it goes up next time).")
        return
    if r.returncode == 0:
        say("Auto-save: uploaded to GitHub%s." % (
            " (%d file%s)" % (len(changed), "" if len(changed) == 1 else "s") if committed else ""))
    else:
        say("Auto-save: saved locally; GitHub upload failed: %s"
            % (r.stderr.strip().splitlines() or ["?"])[-1][:160])


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:                              # never break Claude Code
        say("Auto-save hook error: %s" % exc)
    sys.exit(0)
