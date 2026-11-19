"""
Blocks slurs and other nasty words in high score names.

is_allowed(name) is False when the name contains a banned word. Tricks like
N1GG3R, spaces between letters (N I G G E R) or repeated letters (NIIIGGER)
are caught too.

To ban more words, put them in banned_names.txt next to this file (one per
line, lower case). Those are blocked anywhere in a name.
"""
import os
import re

# Blocked anywhere in the name (long enough to not appear in normal names).
BANNED_ANYWHERE = (
    # English
    "nigger", "nigga", "nigg", "negro", "chink", "wetback", "kike", "raghead",
    "towelhead", "faggot", "fagot", "tranny", "retard", "beaner", "kaffir",
    "cunt", "whore", "slut", "rapist", "pedo", "hitler", "nazi", "heil", "kkk",
    # Dutch
    "neger", "nikker", "kanker", "kenker", "tyfus", "flikker",
    "mongool", "makak", "zigeuner", "kankerjood",
)
# Blocked only as a whole word / whole name (short, so they hide inside normal
# words: "spic" in SPICY, "coon" in RACCOON, ...).
BANNED_WORDS = (
    "fag", "fags", "jap", "japs", "spic", "spics", "coon", "coons", "paki",
    "pakis", "dyke", "homo", "mof", "moffen", "kut", "isis", "gook",
    "hoer", "hoeren", "tering",         # "hoera", "catering" are fine
)

# look-alike digits and symbols -> letters
LEET = str.maketrans("013457@$!9", "oieastasig")


def _squash(text):
    """'niiigger' -> 'niger': repeated letters count as one."""
    return re.sub(r"(.)\1+", r"\1", text)


def _extra_words():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "banned_names.txt")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return tuple(w.strip().lower() for w in f
                         if w.strip() and not w.startswith("#"))
    except OSError:
        return ()


EXTRA = _extra_words()


def is_allowed(name):
    s = str(name).lower().translate(LEET)
    words = re.findall(r"[a-z]+", s)
    letters = "".join(words)                 # "N I G" -> "nig"
    squashed = _squash(letters)
    for bad in BANNED_ANYWHERE + EXTRA:
        sq = _squash(bad)
        if bad in letters or (len(sq) >= 4 and sq in squashed):
            return False
    for word in words + [letters]:
        if word in BANNED_WORDS or _squash(word) in BANNED_WORDS:
            return False
    return True
