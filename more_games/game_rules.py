"""
The safety rules for games in more_games/.

Games that follow these rules are merged automatically (see
.github/workflows/auto-merge-games.yml), so the arcade Pis run them without
anyone reading the code first. These rules keep a game inside its own little
box: it can use pygame and some harmless Python modules, read its own files,
and nothing else - no running programs, no internet, no deleting files.

This file only READS the code, it never runs it.
"""
import ast
import os

ALLOWED_EXT = {".py", ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".wav", ".ogg", ".mp3",
               ".ttf", ".otf", ".txt", ".md", ".json"}
MAX_FILE_MB = 5
MAX_FOLDER_MB = 20

# the Python modules a game may import (plus its own .py files)
ALLOWED_MODULES = {"pygame", "math", "random", "time", "os", "json", "collections",
                   "dataclasses", "itertools", "functools", "enum", "typing", "copy",
                   "colorsys", "string", "re", "statistics", "fractions", "decimal",
                   "heapq", "bisect", "array"}
# of "os", only os.path may be used (to find the game's own pictures and sounds)
OS_ALLOWED = {"path"}
BANNED_NAMES = {"eval", "exec", "compile", "__import__", "globals", "locals", "vars",
                "getattr", "setattr", "delattr", "breakpoint", "input", "exit", "quit",
                "__builtins__", "memoryview"}
OK_DUNDERS = {"__init__", "__name__", "__file__", "__doc__"}
# attribute names that lead to dangerous things (e.g. random._os.system)
BANNED_ATTRS = {"os", "_os", "sys", "_sys", "builtins", "subprocess", "_subprocess", "shutil",
                "system", "popen", "spawnl", "spawnv", "execv", "execl", "modules",
                "import_module", "f_globals", "f_locals", "f_back", "gi_frame", "cr_frame",
                "tb_frame", "func_globals", "unlink", "rmdir", "rmtree", "chmod"}
BANNED_PYGAME = ("pygame.display.set_mode", "pygame.display.flip", "pygame.display.update",
                 "pygame.event.get", "pygame.event.post", "pygame.quit", "pygame.display.quit")


def _dotted(node):
    """pygame.display.flip -> "pygame.display.flip" (None if not a plain name chain)."""
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return None


def scan_code(source, local_modules=()):
    """Problems (a list of strings) in one .py file. Empty list = fine."""
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return ["Python error on line %s: %s" % (exc.lineno, exc.msg)]
    problems = []
    allowed = ALLOWED_MODULES | set(local_modules)

    def bad(node, text):
        problems.append("line %d: %s" % (getattr(node, "lineno", 0), text))

    # "os" may only be used as os.path.something (not passed around: x = os)
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.Name) and child.id == "os" and not (
                    isinstance(node, ast.Attribute) and node.attr in OS_ALLOWED):
                bad(child, "os may only be used as os.path")

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] not in allowed:
                    bad(node, "import %s is not allowed" % alias.name)
                elif alias.name.split(".")[0] == "os" and alias.name not in ("os", "os.path"):
                    bad(node, "import %s is not allowed (only os.path)" % alias.name)
                elif alias.name == "os" and alias.asname:
                    bad(node, "import os as ... is not allowed")
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if node.level or mod.split(".")[0] not in allowed:
                bad(node, "from %s import ... is not allowed" % (mod or "."))
            elif mod == "os" and any(a.name not in OS_ALLOWED for a in node.names):
                bad(node, "from os you may only import path")
            elif any(a.name == "*" for a in node.names):
                bad(node, "from %s import * is not allowed" % mod)
        elif isinstance(node, ast.Name):
            if node.id in BANNED_NAMES:
                bad(node, "%s is not allowed" % node.id)
        elif isinstance(node, ast.Attribute):
            if (node.attr.startswith("__") and node.attr not in OK_DUNDERS) \
                    or node.attr in BANNED_ATTRS:
                bad(node, ".%s is not allowed" % node.attr)
            name = _dotted(node)
            if name and name.startswith("os.") and name.split(".")[1] not in OS_ALLOWED:
                bad(node, "%s is not allowed (only os.path)" % name)
            if name in BANNED_PYGAME:
                bad(node, "%s is not allowed (the arcade does that for you)" % name)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                and node.func.id == "open":
            mode = node.args[1] if len(node.args) > 1 else next(
                (k.value for k in node.keywords if k.arg == "mode"), None)
            if mode is not None and not (isinstance(mode, ast.Constant)
                                         and isinstance(mode.value, str)
                                         and not set(mode.value) & set("wax+")):
                bad(node, "open() may only read files")
    return problems


def check_file(path, size):
    """Problems with one file of a game (by its name and size in bytes)."""
    ext = os.path.splitext(path)[1].lower()
    if ext not in ALLOWED_EXT:
        return ["%s: files like this (%s) are not allowed" % (path, ext or "no extension")]
    if size > MAX_FILE_MB * 1e6:
        return ["%s: bigger than %d MB" % (path, MAX_FILE_MB)]
    return []


def check_folder(folder):
    """All problems in a game folder on disk (used by check_games.py)."""
    problems, total = [], 0
    files = []
    for root, _dirs, names in os.walk(folder):
        if "__pycache__" in root:
            continue
        for n in names:
            full = os.path.join(root, n)
            files.append(full)
            total += os.path.getsize(full)
            problems += check_file(os.path.relpath(full, folder), os.path.getsize(full))
    if total > MAX_FOLDER_MB * 1e6:
        problems.append("the folder is bigger than %d MB" % MAX_FOLDER_MB)
    local = [os.path.splitext(os.path.basename(f))[0] for f in files if f.endswith(".py")]
    for f in files:
        if f.endswith(".py"):
            with open(f, encoding="utf-8", errors="replace") as fh:
                for p in scan_code(fh.read(), local):
                    problems.append("%s %s" % (os.path.relpath(f, folder), p))
    return problems
