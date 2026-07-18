import os
from collections import Counter
from copy import deepcopy

from . import gitio


class ManifestError(RuntimeError):
    pass


def build(repo, base, head, commit_map, backup=None):
    return {
        "repoRoot": os.path.abspath(repo),
        "base": base,
        "head": head,
        "backup": backup,
        "themes": deepcopy(commit_map),
    }


def validate(repo, base, head, m):
    expected = set(gitio.rev_list(repo, base, head))
    assigned = [sha for theme in m.get("themes", []) for sha in theme.get("commits", [])]
    counts = Counter(assigned)

    if set(assigned) != expected:
        raise ManifestError("theme commits do not match the reviewed range")
    if any(count != 1 for count in counts.values()):
        raise ManifestError("a commit belongs to more than one theme")

    for theme in m.get("themes", []):
        if "subsections" in theme:
            subsection_commits = [
                sha
                for subsection in theme["subsections"]
                for sha in subsection.get("commits", [])
            ]
            if Counter(subsection_commits) != Counter(theme.get("commits", [])):
                raise ManifestError(f"subsections do not cover theme {theme.get('id', '')}")
