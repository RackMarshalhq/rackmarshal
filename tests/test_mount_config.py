import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from rackmarshal.core.config import ConfigError
from rackmarshal.domains.mount import collector


class MountConfiguration(unittest.TestCase):
    def test_node_resolves_from_site_config_with_no_environment_override(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "site.conf"
            config.write_text("PVE_NODE=fictional-node\n")
            with patch.dict(os.environ, {"RACKMARSHAL_CONFIG": str(config)}, clear=True):
                with patch.object(collector, "api_get", return_value={}) as request:
                    collector.fetch_lxc_mps({}, "103")
                    self.assertEqual(request.call_args.args[1], "/nodes/fictional-node/lxc/103/config")

    def test_environment_node_overrides_site_config_and_is_path_encoded(self):
        with patch.dict(os.environ, {"PVE_NODE": "node/segment"}):
            self.assertEqual(collector.pve_node(), "node%2Fsegment")

    def test_missing_node_fails_before_request(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch.object(collector, "load_site_config", return_value={}):
                with patch.object(collector, "api_get") as request:
                    with self.assertRaises(ConfigError):
                        collector.fetch_lxc_mps({}, "103")
                    request.assert_not_called()

    def test_guest_agent_uses_same_configured_node(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch.object(collector, "load_site_config", return_value={"PVE_NODE": "fictional-node"}):
                with patch.object(collector, "api_request", side_effect=RuntimeError("fixture stop")) as request:
                    result = collector.fetch_qemu_findmnt({}, "201")
                    self.assertEqual(request.call_args.args[2], "/nodes/fictional-node/qemu/201/agent/exec")
                    self.assertIn("_error", result)

    def test_mount_settings_honor_selected_config_and_existing_environment(self):
        with patch.dict(os.environ, {"MOUNT_SSH_HOST": "override"}, clear=True):
            with patch.object(collector, "load_site_config", return_value={
                "MOUNT_SSH_HOST": "configured", "MOUNT_CATALOG_FILE": "/fictional/catalog.toml"}):
                collector.apply_conf_env()
                self.assertEqual(os.environ["MOUNT_SSH_HOST"], "override")
                self.assertEqual(os.environ["MOUNT_CATALOG_FILE"], "/fictional/catalog.toml")


if __name__ == "__main__":
    unittest.main()
