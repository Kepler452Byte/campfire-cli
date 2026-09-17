from pathlib import PureWindowsPath

from campfire_cli.app.base.schema.operation_schema import maintenance_sync_follow_up


def test_maintenance_follow_up_normalizes_windows_path_scopes() -> None:
    follow_up = maintenance_sync_follow_up(
        "test",
        [PureWindowsPath("mynote/知识/网络代理"), "mynote/知识/网络代理/子领域"],
    )

    assert [item.model_dump() for item in follow_up] == [
        {"command": "maintenance sync", "workspace": "test", "scope": "mynote/知识/网络代理"}
    ]
