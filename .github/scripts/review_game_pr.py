#!/usr/bin/env python3
"""
Decides if a pull request with a game may be merged automatically.

Runs on GitHub (see .github/workflows/auto-merge-games.yml) from the arcade's
own main branch, so a pull request can't change these rules. It only READS the
game's files through the GitHub API; it never runs them.

A pull request is merged when:
  - it only changes files inside ONE folder: more_games/<name>/
  - that folder is new, or was made by the same person
  - every file follows more_games/game_rules.py (allowed modules, file types, sizes)
  - (and the "Check more games" test already passed, or this doesn't run at all)

Writes the verdict to the file named in $RESULT_FILE and "ok=true/false" plus
"pr=<number>" to $GITHUB_OUTPUT.
"""
import base64
import json
import os
import re
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "more_games"))
import game_rules                                       # noqa: E402

API = "https://api.github.com"
REPO = os.environ["REPO"]                   # owner/name of the arcade
SHA = os.environ["HEAD_SHA"]                # the commit the check ran on
HEAD_OWNER = os.environ["HEAD_OWNER"]       # who owns the fork
HEAD_BRANCH = os.environ["HEAD_BRANCH"]
TOKEN = os.environ["GITHUB_TOKEN"]
TRUSTED = {"OWNER", "MEMBER", "COLLABORATOR"}
FOLDER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_]{0,39}$")


def get(path):
    req = urllib.request.Request(API + path, headers={
        "Authorization": "Bearer " + TOKEN, "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def output(**values):
    with open(os.environ.get("GITHUB_OUTPUT", os.devnull), "a") as f:
        for k, v in values.items():
            f.write("%s=%s\n" % (k, v))


def finish(pr, ok, lines):
    with open(os.environ.get("RESULT_FILE", "result.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    output(ok="true" if ok else "false", pr=pr or "")
    sys.exit(0)


def find_pr():
    prs = get("/repos/%s/pulls?state=open&per_page=100&head=%s:%s"
              % (REPO, HEAD_OWNER, urllib.request.quote(HEAD_BRANCH, safe="")))
    for pr in prs:
        if pr["head"]["sha"] == SHA:
            return pr
    return None


def review(pr):
    n = pr["number"]
    problems = []
    if pr["base"]["ref"] != get("/repos/%s" % REPO)["default_branch"]:
        return ["The pull request must go into the main branch."]
    if pr.get("draft"):
        return ["The pull request is still a draft."]

    files = []
    for page in range(1, 31):
        batch = get("/repos/%s/pulls/%d/files?per_page=100&page=%d" % (REPO, n, page))
        files += batch
        if len(batch) < 100:
            break
    folders = set()
    for f in files:
        for name in (f["filename"], f.get("previous_filename")):
            if not name:
                continue
            parts = name.split("/")
            if len(parts) < 3 or parts[0] != "more_games":
                problems.append("`%s` is outside a game folder in more_games/" % name)
            else:
                folders.add(parts[1])
    if problems:
        return problems
    if len(folders) != 1:
        return ["Change only ONE game folder per pull request (this one changes: %s)."
                % ", ".join(sorted(folders))]
    folder = folders.pop()
    if not FOLDER_RE.match(folder):
        return ["The folder name `%s` may only have letters, numbers and _ "
                "(max 40, not starting with _)." % folder]

    # an existing game may only be changed by the person who made it
    author = pr["user"]["login"]
    if os.path.isdir(os.path.join(ROOT, "more_games", folder)) \
            and pr.get("author_association") not in TRUSTED:
        commits = get("/repos/%s/commits?path=more_games/%s&per_page=100" % (REPO, folder))
        makers = {(c.get("author") or {}).get("login") for c in commits}
        if author not in makers:
            return ["`more_games/%s` is someone else's game. Make your own folder with a "
                    "new name." % folder]

    # the whole folder as it will be after the merge
    head_repo = pr["head"]["repo"]["full_name"]
    tree = get("/repos/%s/git/trees/%s?recursive=1" % (head_repo, SHA))
    if tree.get("truncated"):
        return ["Too many files."]
    prefix = "more_games/%s/" % folder
    blobs = [t for t in tree["tree"] if t["type"] == "blob" and t["path"].startswith(prefix)]
    links = [t for t in tree["tree"] if t["path"].startswith(prefix)
             and t["type"] != "blob" and t["type"] != "tree"]
    if links or any(t.get("mode") == "120000" for t in blobs):
        problems.append("Links (symlinks) and submodules are not allowed.")
    names = [t["path"][len(prefix):] for t in blobs]
    if "game.py" not in names:
        problems.append("There is no `game.py` in `more_games/%s/`." % folder)
    total = 0
    for t, name in zip(blobs, names):
        total += t.get("size", 0)
        problems += game_rules.check_file(name, t.get("size", 0))
    if total > game_rules.MAX_FOLDER_MB * 1e6:
        problems.append("The folder is bigger than %d MB." % game_rules.MAX_FOLDER_MB)
    local = [os.path.splitext(os.path.basename(nm))[0] for nm in names if nm.endswith(".py")]
    for t, name in zip(blobs, names):
        if name.endswith(".py"):
            blob = get("/repos/%s/git/blobs/%s" % (head_repo, t["sha"]))
            source = base64.b64decode(blob["content"]).decode("utf-8", "replace")
            problems += ["`%s` %s" % (name, p) for p in game_rules.scan_code(source, local)]
    return problems


def main():
    pr = find_pr()
    if pr is None:
        print("No open pull request for this commit (maybe a newer push came in).")
        output(ok="false", pr="")
        return
    try:
        problems = review(pr)
    except Exception as exc:                            # API trouble: don't merge
        problems = ["The automatic review could not finish (%s). The arcade owner will "
                    "look at it." % exc]
    if problems:
        finish(pr["number"], False,
               ["### 🕹️ Not merged automatically", "",
                "Your game can't be added automatically yet:", ""]
               + ["- " + p for p in problems[:30]]
               + ["", "Fix these and push again; this is checked again automatically. "
                  "The rules are in `more_games/README.md`."])
    finish(pr["number"], True,
           ["### 🕹️ Game added!", "",
            "Everything checks out, so this is merged automatically. The arcades get it "
            "the next time they start."])


if __name__ == "__main__":
    main()
