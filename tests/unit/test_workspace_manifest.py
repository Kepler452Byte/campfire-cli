from __future__ import annotations

import pytest

from campfire_cli.app.workspace.schema.workspace_schema import WorkspaceManifest


def test_manifest_accepts_only_stable_project_domain_identity() -> None:
    current = WorkspaceManifest.model_validate(
        {
            "schema_version": 1,
            "workspace": {"id": "personal", "name": "Personal"},
            "projects": [
                {
                    "id": "campfire-cli",
                    "name": "Campfire CLI",
                    "document_domain_id": "project-campfire-cli",
                }
            ],
        }
    )

    assert current.projects[0].document_domain_id == "project-campfire-cli"


def test_manifest_rejects_removed_project_domain_path_field() -> None:
    with pytest.raises(ValueError, match="document_domain"):
        WorkspaceManifest.model_validate(
            {
                "schema_version": 1,
                "workspace": {"id": "personal", "name": "Personal"},
                "projects": [
                    {
                        "id": "campfire-cli",
                        "name": "Campfire CLI",
                        "document_domain": "mywork/Campfire",
                    }
                ],
            }
        )
