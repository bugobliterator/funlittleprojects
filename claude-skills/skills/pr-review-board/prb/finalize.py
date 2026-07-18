from collections import defaultdict, deque
from copy import deepcopy

from . import gitio, manifest


class FinalizeError(RuntimeError):
    pass


def _restore(repo, branch, backup_tag):
    try:
        gitio.git(repo, "rebase", "--abort")
    except gitio.GitError:
        pass
    gitio.git(repo, "checkout", "-B", branch, backup_tag)


def _regenerate(repo, base, new_head, manifest_dict, backup_tag):
    themes = deepcopy(manifest_dict.get("themes", []))
    old_commits = {sha for theme in themes for sha in theme.get("commits", [])}
    old_order = [sha for sha in gitio.rev_list(repo, base, backup_tag) if sha in old_commits]

    new_by_subject = defaultdict(deque)
    for sha in gitio.rev_list(repo, base, new_head):
        subject = gitio.git(repo, "log", "--format=%s", "-1", sha)
        new_by_subject[subject].append(sha)

    replacements = {}
    for sha in old_order:
        subject = gitio.git(repo, "log", "--format=%s", "-1", sha)
        if not new_by_subject[subject]:
            raise FinalizeError(f"cannot map commit after autosquash: {sha}")
        replacements[sha] = new_by_subject[subject].popleft()
    if set(replacements) != old_commits:
        raise FinalizeError("manifest contains commits outside the finalized range")

    for theme in themes:
        theme["commits"] = [replacements[sha] for sha in theme.get("commits", [])]
        for subsection in theme.get("subsections", []):
            subsection["commits"] = [replacements[sha] for sha in subsection.get("commits", [])]
    return manifest.build(repo, base, new_head, themes, backup_tag)


def run(repo, base, head_branch, manifest_dict):
    if gitio.git(repo, "rev-parse", "--abbrev-ref", "HEAD") != head_branch:
        raise FinalizeError("head branch is not checked out")

    pre_head = gitio.git(repo, "rev-parse", "HEAD")
    backup_tag = f"prb-finalize-backup-{pre_head[:12]}"
    try:
        gitio.git(repo, "tag", "-f", backup_tag, pre_head)
    except gitio.GitError as error:
        raise FinalizeError(str(error)) from error

    try:
        pre_tree = gitio.tree_hash(repo, "HEAD")
        gitio.git(repo, "-c", "sequence.editor=:", "rebase", "--autosquash", "-i", base)
        new_head = gitio.git(repo, "rev-parse", "HEAD")
        if gitio.tree_hash(repo, new_head) != pre_tree:
            raise FinalizeError("finalized tree differs from backup")
        result = _regenerate(repo, base, new_head, manifest_dict, backup_tag)
        manifest.validate(repo, base, new_head, result)
        gitio.git(repo, "tag", "-d", backup_tag)
        return result
    except (gitio.GitError, manifest.ManifestError, FinalizeError) as error:
        try:
            _restore(repo, head_branch, backup_tag)
        except gitio.GitError as restore_error:
            raise FinalizeError(f"{error}; restore failed: {restore_error}") from restore_error
        if isinstance(error, FinalizeError):
            raise
        raise FinalizeError(str(error)) from error
