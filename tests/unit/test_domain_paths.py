from pathlib import Path

import pytest

from campfire_cli.app.workspace.service.structure_service import DomainService
from campfire_cli.common.exceptions import ConfigurationError
from campfire_cli.config.settings import campfire_home
from campfire_cli.container import AppContainer


def test_task_and_record_directories_can_be_domains(workspace: Path) -> None:
    domains = DomainService(workspace, campfire_home())
    created = domains.create(
        domain_id="tasks",
        name="任务",
        path="mywork/任务",
        domain_type="work-domain",
        project_id=None,
        confirm=True,
    )
    assert created.status == "created"
    assert (workspace / "mywork/任务/_领域.md").is_file()

    records = workspace / "mywork/记录"
    records.mkdir()
    (records / "记录-示例.md").write_text("已有记录。\n", encoding="utf-8")
    issues = domains.discover()[1]
    assert {item["code"] for item in issues if item["path"] == "mywork/记录"} == {
        "undeclared-domain-directory"
    }

    adopted = AppContainer.build("test").adoption.adopt(
        records,
        target_path=None,
        domain_id="records",
        name="记录",
        domain_type="work-domain",
        confirm=True,
    )
    assert adopted.status == "adopted"
    assert (records / "_领域.md").is_file()
    assert not [item for item in domains.discover()[1] if item["path"] == "mywork/记录"]


@pytest.mark.parametrize(
    "path, reserved",
    [("mywork/_generated/子领域", "_generated"), ("mywork/_任意系统区", "_任意系统区")],
)
def test_reserved_domain_path_reports_the_matching_directory(
    workspace: Path, path: str, reserved: str
) -> None:
    with pytest.raises(ConfigurationError) as failure:
        DomainService(workspace, campfire_home()).create(
            domain_id="blocked",
            name="Blocked",
            path=path,
            domain_type="work-domain",
            project_id=None,
            confirm=False,
        )

    payload = failure.value.payload()
    assert payload["code"] == "reserved-directory"
    assert payload["path"] == path
    assert payload["reserved_directory"] == reserved
    assert payload["hint"]


@pytest.mark.parametrize("name", ["assets", "archive", "generated", "a_skill"])
def test_plain_directory_names_can_be_domains(workspace: Path, name: str) -> None:
    created = DomainService(workspace, campfire_home()).create(
        domain_id=name.replace("_", "-"),
        name=name,
        path=f"mywork/{name}",
        domain_type="work-domain",
        project_id=None,
        confirm=True,
    )

    assert created.status == "created"
    assert (workspace / f"mywork/{name}/_领域.md").is_file()
