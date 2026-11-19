#!/usr/bin/env python3
"""
Update the arcade on your Raspberry Pis from this PC, over your home network.

Only the Pis listed in pis.txt (next to this file) are updated - nothing on
the network is searched or touched otherwise.

What it does for every Pi in the list:
  1. packs this picade folder (without scores, settings and junk),
  2. sends it over SSH and unpacks it next to the old version,
  3. copies that Pi's own config.json and highscores*.json into the new one
     (so every Pi keeps its own controls, name and scoreboards),
  4. swaps the new version in; the previous one stays as a backup
     (<folder>.old) until the next update.
The arcade on that Pi uses the new version the next time it starts
(or right away with --restart, which reboots the Pi).

Use (on Windows: double-click update_pis.bat, or run it in a terminal):
    py update_pis.py                 update every Pi in pis.txt
    py update_pis.py --only arcade1  update just that one
    py update_pis.py --restart       ... and reboot them afterwards
    py update_pis.py --dry-run       only show what would be sent where
    py update_pis.py --setup-keys    once: log in without typing passwords
"""
import argparse
import io
import os
import re
import subprocess
import sys
import tarfile
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                     # the picade folder
LIST = os.path.join(HERE, "pis.txt")

# never sent: this tool, scores and settings (every Pi keeps its own), junk
SKIP_DIRS = {"update", "__pycache__", ".idea", ".git"}
SKIP_FILES = re.compile(r"^(config\.json|highscores.*\.json|game\.log|.*\.pyc|.*\.tmp)$")
SAFE = re.compile(r"^[A-Za-z0-9._-]+$")          # host / user names
SAFE_DIR = re.compile(r"^[A-Za-z0-9._/-]+$")     # folder (inside the Pi user's home)

# runs ON the Pi (bash). The archive arrives on stdin.
REMOTE = r'''set -e
D="$HOME/{folder}"
T="$(mktemp /tmp/picade_update.XXXXXX)"
cat > "$T"
rm -rf "$D.new"
mkdir -p "$D.new"
tar -xzf "$T" -C "$D.new"
rm -f "$T"
if [ -d "$D/main" ]; then
    for f in "$D"/main/config.json "$D"/main/highscores*.json; do
        [ -f "$f" ] && cp -p "$f" "$D.new/main/"
    done
fi
# keep the link to GitHub (installed with git clone): it still updates
# itself from GitHub when the arcade starts
if [ -d "$D/.git" ]; then cp -a "$D/.git" "$D.new/.git"; fi
rm -rf "$D.old"
if [ -d "$D" ]; then mv "$D" "$D.old"; fi
mv "$D.new" "$D"
chmod +x "$D"/main/*.sh 2>/dev/null || true
echo "UPDATED $D"
'''


def read_list():
    """[(host, user, folder)] from pis.txt."""
    if not os.path.exists(LIST):
        sys.exit("pis.txt not found next to this script.")
    pis = []
    with open(LIST, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
            parts = line.split()
            host = parts[0]
            user = parts[1] if len(parts) > 1 else "pi"
            folder = parts[2] if len(parts) > 2 else "picade"
            if not SAFE.match(host) or not SAFE.match(user) or not SAFE_DIR.match(folder) \
                    or ".." in folder.split("/"):
                sys.exit("pis.txt line %d looks wrong: %r" % (n, line))
            pis.append((host, user, folder))
    return pis


def build_archive():
    """The picade folder as a .tar.gz in memory (+ the list of files in it)."""
    buf = io.BytesIO()
    names = []
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for dirpath, dirnames, filenames in os.walk(ROOT):
            dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
            for fn in sorted(filenames):
                if SKIP_FILES.match(fn):
                    continue
                full = os.path.join(dirpath, fn)
                rel = os.path.relpath(full, ROOT).replace(os.sep, "/")
                info = tar.gettarinfo(full, arcname=rel)
                info.mode = 0o755 if fn.endswith(".sh") else 0o644    # (Windows has no x bit)
                info.uid = info.gid = 0
                info.uname = info.gname = ""
                with open(full, "rb") as fh:
                    tar.addfile(info, fh)
                names.append(rel)
    return buf.getvalue(), names


def ssh_base(host, user):
    return ["ssh", "-o", "ConnectTimeout=8", "-o", "StrictHostKeyChecking=accept-new",
            "%s@%s" % (user, host)]


def update_one(host, user, folder, data, restart):
    print("\n=== %s (%s, ~/%s) ===" % (host, user, folder))
    cmd = ssh_base(host, user) + ["bash -c '%s'" % REMOTE.format(folder=folder).replace("'", "'\\''")]
    with tempfile.TemporaryFile() as tmp:
        tmp.write(data)
        tmp.seek(0)
        r = subprocess.run(cmd, stdin=tmp)
    if r.returncode != 0:
        print("!! %s: update FAILED (is it switched on, is SSH enabled, right name / user?)" % host)
        return False
    print("%s: updated." % host)
    if restart:
        subprocess.run(ssh_base(host, user) + ["sudo -n reboot || echo 'could not reboot (needs a password)'"])
    return True


def setup_keys(pis):
    """Make a key on this PC (once) and put it on every Pi in the list, so
    updates don't ask for passwords any more."""
    home = os.path.expanduser("~")
    key = os.path.join(home, ".ssh", "id_ed25519")
    if not os.path.exists(key + ".pub"):
        os.makedirs(os.path.dirname(key), exist_ok=True)
        print("Making a key for this PC (no passphrase) ...")
        subprocess.run(["ssh-keygen", "-t", "ed25519", "-N", "", "-f", key], check=True)
    with open(key + ".pub", "rb") as f:
        pub = f.read()
    for host, user, _folder in pis:
        print("\n=== %s: type that Pi's password one last time ===" % host)
        r = subprocess.run(ssh_base(host, user) + [
            "mkdir -p ~/.ssh && chmod 700 ~/.ssh && cat >> ~/.ssh/authorized_keys"
            " && chmod 600 ~/.ssh/authorized_keys"], input=pub)
        print("%s: %s" % (host, "key installed" if r.returncode == 0 else "FAILED"))


def local_test(data, home, folder):
    """Run the Pi side here with bash, in a fake home folder (for testing)."""
    env = dict(os.environ, HOME=home)
    script = REMOTE.format(folder=folder)
    r = subprocess.run(["bash", "-c", script], input=data, env=env)
    return r.returncode == 0


def main():
    ap = argparse.ArgumentParser(description="Update the arcade on the Pis in pis.txt.")
    ap.add_argument("--only", help="update only this Pi (as written in pis.txt)")
    ap.add_argument("--restart", action="store_true", help="reboot the Pis after updating")
    ap.add_argument("--dry-run", action="store_true", help="only show what would happen")
    ap.add_argument("--setup-keys", action="store_true", help="once: no more password typing")
    ap.add_argument("--local-test", metavar="HOME", help=argparse.SUPPRESS)
    args = ap.parse_args()

    data, names = build_archive()
    if args.local_test:
        ok = local_test(data, args.local_test, "picade")
        sys.exit(0 if ok else 1)

    pis = read_list()
    if args.only:
        pis = [p for p in pis if p[0] == args.only]
    if not pis:
        sys.exit("No Pis to update: put your arcade Pis in pis.txt (see the examples there).")
    if args.setup_keys:
        setup_keys(pis)
        return
    print("Arcade package: %d files, %.0f KB (scores and settings are not included)."
          % (len(names), len(data) / 1024.0))
    print("Pis to update: %s" % ", ".join(h for h, _u, _f in pis))
    if args.dry_run:
        for h, u, f in pis:
            print("  would update %s@%s:~/%s" % (u, h, f))
        return
    done = [h for h, u, f in pis if update_one(h, u, f, data, args.restart)]
    failed = [h for h, _u, _f in pis if h not in done]
    print("\nUpdated: %s" % (", ".join(done) or "none"))
    if failed:
        print("Failed:  %s" % ", ".join(failed))
    if done and not args.restart:
        print("The new version starts the next time the arcade starts (or reboot the Pi).")


if __name__ == "__main__":
    main()
