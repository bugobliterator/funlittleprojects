import os

from . import gitio


def unit_diff(repo, base, commits):
    if not commits:
        return {"raw": "", "files": []}

    paths = []
    for sha in commits:
        for path in gitio.git(repo, "diff", "--name-only", f"{sha}^", sha).splitlines():
            if path not in paths:
                paths.append(path)

    parent = gitio.git(repo, "rev-parse", f"{commits[0]}^")
    args = (parent, commits[-1], "--", *paths)
    raw = gitio.git(repo, "diff", *args)
    files = []
    for line in gitio.git(repo, "diff", "--numstat", *args).splitlines():
        added, deleted, path = line.split("\t", 2)
        files.append({
            "path": path,
            "added": int(added) if added.isdigit() else 0,
            "deleted": int(deleted) if deleted.isdigit() else 0,
        })
    return {"raw": raw, "files": files}


def vscode_link(repo_root, path, line):
    absolute = os.path.abspath(os.path.join(repo_root, path)).lstrip("/")
    return f"vscode://file/{absolute}:{line}"
