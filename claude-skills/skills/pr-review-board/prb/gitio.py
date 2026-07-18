import subprocess
from pathlib import Path


class GitError(RuntimeError):
    def __init__(self, cmd: list[str], stderr: str):
        self.cmd = cmd
        self.stderr = stderr
        super().__init__(f"{' '.join(cmd)}: {stderr}")


def _run(repo: str | Path, *args: str) -> subprocess.CompletedProcess[str]:
    cmd = ["git", "-C", str(repo), *args]
    return subprocess.run(cmd, capture_output=True, text=True)


def git(repo: str | Path, *args: str) -> str:
    result = _run(repo, *args)
    if result.returncode:
        raise GitError(result.args, result.stderr.strip())
    return result.stdout.strip()


def rev_list(repo: str | Path, base: str, head: str) -> list[str]:
    output = git(repo, "rev-list", "--reverse", f"{base}..{head}")
    return output.splitlines() if output else []


def tree_hash(repo: str | Path, ref: str) -> str:
    return git(repo, "rev-parse", f"{ref}^{{tree}}")


def diff_empty(repo: str | Path, a: str, b: str) -> bool:
    result = _run(repo, "diff", "--quiet", a, b)
    if result.returncode > 1:
        raise GitError(result.args, result.stderr.strip())
    return result.returncode == 0
