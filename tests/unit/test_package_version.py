from __future__ import annotations

import io
import json
import unittest
from unittest import mock

from campfire_cli.common.package_version import fetch_latest_version, is_newer_version


class VersionComparisonTests(unittest.TestCase):
    def test_numeric_segments_compare(self) -> None:
        self.assertTrue(is_newer_version("0.1.5", "0.1.4"))
        self.assertTrue(is_newer_version("0.2.0", "0.1.9"))
        self.assertTrue(is_newer_version("1.0.0", "0.9.9"))
        self.assertFalse(is_newer_version("0.1.4", "0.1.4"))
        self.assertFalse(is_newer_version("0.1.3", "0.1.4"))

    def test_non_numeric_segments_fall_back_to_inequality(self) -> None:
        self.assertTrue(is_newer_version("0.1.5.dev1", "0.1.4"))
        self.assertFalse(is_newer_version("0.1.4", "0.1.4.dev1"))


class FetchLatestVersionTests(unittest.TestCase):
    def test_parses_version_from_pypi_payload(self) -> None:
        payload = io.BytesIO(json.dumps({"info": {"version": "0.1.5"}}).encode("utf-8"))
        with mock.patch(
            "campfire_cli.common.package_version.urllib.request.urlopen", return_value=payload
        ):
            self.assertEqual("0.1.5", fetch_latest_version("campfire-cli"))

    def test_network_failure_returns_none(self) -> None:
        with mock.patch(
            "campfire_cli.common.package_version.urllib.request.urlopen",
            side_effect=OSError("offline"),
        ):
            self.assertIsNone(fetch_latest_version("campfire-cli"))

    def test_invalid_payload_returns_none(self) -> None:
        payload = io.BytesIO(b"not json")
        with mock.patch(
            "campfire_cli.common.package_version.urllib.request.urlopen", return_value=payload
        ):
            self.assertIsNone(fetch_latest_version("campfire-cli"))


if __name__ == "__main__":
    unittest.main()
