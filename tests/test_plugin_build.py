import importlib.util
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from rackmarshal.agent.investigator import HEALTH_INSTRUCTIONS
from rackmarshal.agent.openai_client import build_request
spec = importlib.util.spec_from_file_location("plugin_build", Path(__file__).resolve().parents[1] / "scripts/build-investigator-plugin.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)

class PluginBuildTests(unittest.TestCase):
    def test_health_contract_reaches_runtime_and_both_packaged_surfaces(self):
        # This checks policy delivery/parity, not live model compliance.
        self.assertIn(HEALTH_INSTRUCTIONS, build_request("Is RackMarshal healthy?", "tunnel_test")["instructions"])
        canonical = (builder.ROOT / "skills/rackmarshal-investigator/SKILL.md").read_text()
        self.assertIn(HEALTH_INSTRUCTIONS, canonical)
        with tempfile.TemporaryDirectory() as temp:
            for surface in ("local", "cloud"):
                with self.subTest(surface=surface):
                    output = Path(temp) / (surface + ".zip")
                    builder.build(surface, output, "asdk_" + "app_" + "a"*32 if surface == "cloud" else None)
                    with zipfile.ZipFile(output) as archive:
                        prefix = "plugins/rackmarshal-investigator/" if surface == "local" else ""
                        policy = archive.read(prefix + "skills/rackmarshal-investigator/SKILL.md").decode()
                    self.assertIn(HEALTH_INSTRUCTIONS, policy)
                    if surface == "local":
                        self.assertEqual(policy, canonical)
                    else:
                        self.assertTrue(policy.startswith(canonical + "\n## Business connection binding\n"))

    def test_local_reproducible_and_complete(self):
        with tempfile.TemporaryDirectory() as temp:
            a, b = Path(temp)/"a.zip", Path(temp)/"b.zip"
            builder.build("local", a); builder.build("local", b)
            self.assertEqual(a.read_bytes(), b.read_bytes())
            with zipfile.ZipFile(a) as archive:
                names = archive.namelist()
                self.assertFalse(any(".app.json" in n for n in names))
                market = json.loads(archive.read(".agents/plugins/marketplace.json"))
                prefix = market["plugins"][0]["source"]["path"].removeprefix("./") + "/"
                self.assertIn(prefix + ".codex-plugin/plugin.json", names)
                self.assertEqual(archive.read(prefix + "skills/rackmarshal-investigator/SKILL.md"),
                    (builder.ROOT / "skills/rackmarshal-investigator/SKILL.md").read_bytes())
            with self.assertRaises(FileExistsError): builder.build("local", a)
    def test_cloud_binding_stays_private(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)/"cloud.zip"
            binding = "asdk_" + "app_" + "a"*32
            builder.build("cloud", out, binding)
            self.assertEqual(out.stat().st_mode & 0o777, 0o600)
            with zipfile.ZipFile(out) as archive:
                self.assertNotIn(".mcp.json", archive.namelist())
                self.assertIn(".app.json", archive.namelist())
            with self.assertRaises(ValueError): builder.build("cloud", builder.ROOT/"public.zip", binding)
            with self.assertRaises(ValueError): builder.build("local", Path(temp)/"local.zip", binding)
            with self.assertRaises(ValueError): builder.build("cloud", Path(temp)/"invalid.zip", "wrong")
