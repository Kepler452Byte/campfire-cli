"""
SPEC:
  name: release_check
  purpose: 发布前只读比较本地与远端标签对象、目标提交，禁止静默替换
  idempotent: true
  side_effects: []
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


def git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True, timeout=30
    ).stdout.strip()


def check_release(root: Path, tag: str, remote: str = "origin", target: str = "HEAD") -> dict:
    git(root, "check-ref-format", f"refs/tags/{tag}")
    commit = git(root, "rev-parse", "--verify", f"{target}^{{commit}}")
    local_ref = git(root, "for-each-ref", "--format=%(refname)", f"refs/tags/{tag}")
    local = None
    if f"refs/tags/{tag}" in local_ref.splitlines():
        local = {
            "object": git(root, "rev-parse", f"refs/tags/{tag}"),
            "commit": git(root, "rev-parse", f"refs/tags/{tag}^{{commit}}"),
        }
    refs = {}
    for line in git(
        root, "ls-remote", remote, f"refs/tags/{tag}", f"refs/tags/{tag}^{{}}"
    ).splitlines():
        oid, ref = line.split()
        refs[ref] = oid
    remote_object = refs.get(f"refs/tags/{tag}")
    remote_tag = (
        {"object": remote_object, "commit": refs.get(f"refs/tags/{tag}^{{}}", remote_object)}
        if remote_object
        else None
    )
    code = "tag-ready"
    action = "reuse" if remote_tag else "push-existing" if local else "create"
    if any(item and item["commit"] != commit for item in (local, remote_tag)):
        code, action = "tag-commit-conflict", "stop"
    elif remote_tag and not local:
        code, action = "tag-local-missing", "stop"
    elif remote_tag and local and remote_tag["object"] != local["object"]:
        code, action = "tag-object-conflict", "stop"
    return {
        "status": "blocked" if action == "stop" else "ok",
        "code": code,
        "tag": tag,
        "target_commit": commit,
        "local": local,
        "remote": remote_tag,
        "action": action,
        "write_performed": False,
        "hint": "冲突时核对指定标签，不重建或强推；远端已有但本地缺失时先获取原标签。",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="只读发布标签检查，不创建、推送或覆盖标签")
    parser.add_argument("--tag", required=True)
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--target", default="HEAD")
    args = parser.parse_args()
    try:
        result = check_release(
            Path(__file__).resolve().parents[1], args.tag, args.remote, args.target
        )
    except (subprocess.SubprocessError, OSError, ValueError) as exc:
        print(json.dumps({"status": "error", "code": "tag-check-failed", "message": str(exc)}))
        raise SystemExit(1) from exc
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["status"] == "ok" else 1)


if __name__ == "__main__":
    main()
