import re
from collections import Counter

from . import gitio


class RestructureError(RuntimeError):
    pass


def propose(repo, base, head):
    groups = {}
    for sha in gitio.rev_list(repo, base, head):
        subject = gitio.git(repo, "log", "--format=%s", "-1", sha)
        match = re.match(r"^(\w+)(?:\(([^)]*)\))?:", subject)
        kind, scope = match.groups() if match else ("other", None)
        key = scope or kind
        if key not in groups:
            groups[key] = {
                "id": key,
                "title": key.replace("-", " ").title(),
                "summary": "",
                "userImpact": "",
                "affectedRoles": [],
                "commits": [],
            }
        groups[key]["commits"].append(sha)
    return list(groups.values())


def _restore(repo, branch, backup_tag):
    try:
        gitio.git(repo, "cherry-pick", "--abort")
    except gitio.GitError:
        pass
    gitio.git(repo, "checkout", "-B", branch, backup_tag)


def _restore_and_raise(repo, branch, backup_tag, error):
    try:
        _restore(repo, branch, backup_tag)
    except gitio.GitError as restore_error:
        raise RestructureError(f"{error}; restore failed: {restore_error}") from restore_error
    if isinstance(error, RestructureError):
        raise error
    raise RestructureError(str(error)) from error


def apply(repo, base, head, commit_map, backup_tag):
    branch = gitio.git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    if branch == "HEAD":
        raise RestructureError("restructure requires a checked-out branch")

    head_sha = gitio.git(repo, "rev-parse", head)
    if gitio.git(repo, "rev-parse", "HEAD") != head_sha:
        raise RestructureError("head is not checked out")

    expected = gitio.rev_list(repo, base, head_sha)
    ordered = [sha for theme in commit_map for sha in theme.get("commits", [])]
    if set(ordered) != set(expected) or any(count != 1 for count in Counter(ordered).values()):
        raise RestructureError("commit map must contain every commit exactly once")

    try:
        gitio.git(repo, "tag", backup_tag, head_sha)
        gitio.git(repo, "checkout", "--detach", base)
        for sha in ordered:
            gitio.git(repo, "cherry-pick", sha)
        new_head = gitio.git(repo, "rev-parse", "HEAD")
    except gitio.GitError as error:
        _restore_and_raise(repo, branch, backup_tag, error)

    try:
        identical = gitio.diff_empty(repo, backup_tag, new_head)
    except gitio.GitError as error:
        _restore_and_raise(repo, branch, backup_tag, error)

    if not identical:
        _restore_and_raise(
            repo,
            branch,
            backup_tag,
            RestructureError("restructured tree differs from backup"),
        )

    try:
        gitio.git(repo, "checkout", "-B", branch, new_head)
    except gitio.GitError as error:
        _restore_and_raise(repo, branch, backup_tag, error)
    return new_head
