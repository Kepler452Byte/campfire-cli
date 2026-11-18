"""Validate portable names of local script projects."""

import re

from campfire_cli.common.exceptions import InputError


def validate_project_name(name: str) -> None:
    if (
        not isinstance(name, str)
        or not name
        or len(name) > 128
        or name != name.strip(" .")
        or re.search(r'[<>:"/\\|?*\x00-\x1f]', name)
    ):
        raise InputError(
            "脚本项目必须是 scripts 下的一个顶级文件夹名称",
            code="invalid-script-project",
            field="script_project",
            expected_type="single-directory-name",
            example="personal-growth",
        )
