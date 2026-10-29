import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from rocm_images import generate_dockerfile as generator


@unittest.skipUnless(shutil.which("jq") and shutil.which("sha256sum"), "requires jq and sha256sum")
class ManifestDownloadTests(unittest.TestCase):
    def run_download(self, *, indirect=True, nightly_tag="b11960\n", corrupt=False,
                     archive_versions=("9.9", "10.0", "10.1")):
        config = generator.read_model(
            Path(__file__).resolve().parents[1] / "manifests/llama.cpp.yaml", generator.Config,
        )
        script = next(step.run for step in config.steps if step.run)
        script = generator.expand(script, config.vars, {"gfx": "gfx1201", "rocm": "10.1"})
        # Execute the actual download logic without apt installation or extraction into /opt.
        script = script[script.index("# The archive must match"):script.index("# Release archives contain")]
        api = "https://api.github.com/repos/ggml-org/llama.cpp/releases/tags/"
        responses = {}

        def asset(name, content):
            url = "https://example.test/" + name
            responses[url] = content
            return {"name": name, "browser_download_url": url,
                    "digest": "sha256:" + hashlib.sha256(content.encode()).hexdigest()}

        tag = "b11960" if indirect else config.vars["llama-cpp-version"]
        binary_assets = [asset(f"llama-{tag}-bin-ubuntu-rocm-{version}-x64.tar.gz", version)
                         for version in archive_versions]
        if indirect:
            pointer = asset("nightly-tag.txt", nightly_tag)
            if corrupt:
                responses[pointer["browser_download_url"]] = "b99999\n"
            responses[api + config.vars["llama-cpp-version"]] = json.dumps({"assets": [pointer]})
            responses[api + "b11960"] = json.dumps({"assets": binary_assets})
        else:
            responses[api + tag] = json.dumps({"assets": binary_assets})

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "responses.json").write_text(json.dumps(responses))
            curl = root / "curl"
            curl.write_text(
                f"#!{sys.executable}\n"
                "import json, pathlib, sys\n"
                "args = sys.argv[1:]\n"
                "url = next(arg for arg in args if arg.startswith('https://'))\n"
                "with open('requests.txt', 'a') as log: log.write(url + '\\n')\n"
                "content = json.loads(pathlib.Path('responses.json').read_text())[url]\n"
                "if '-o' in args: pathlib.Path(args[args.index('-o') + 1]).write_text(content)\n"
                "else: sys.stdout.write(content)\n"
            )
            curl.chmod(0o755)
            result = subprocess.run(
                ["/bin/sh", "-eu"], input='download_dir="$PWD"\n' + script,
                cwd=root, env={**os.environ, "PATH": directory + os.pathsep + os.environ["PATH"]},
                text=True, capture_output=True,
            )
            requests = (root / "requests.txt").read_text().splitlines()
            archive = root / "llama.tar.gz"
            return result, requests, archive.read_text() if archive.exists() else None

    def test_versioned_release_resolves_binary_release(self):
        result, requests, archive = self.run_download()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("https://api.github.com/repos/ggml-org/llama.cpp/releases/tags/b11960", requests)
        self.assertEqual(archive, "10.1")

    def test_binary_release_can_be_used_directly(self):
        result, _, archive = self.run_download(indirect=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(archive, "10.1")

    def test_pointer_digest_mismatch_stops_before_binary_lookup(self):
        result, requests, archive = self.run_download(corrupt=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(requests), 2)
        self.assertIsNone(archive)

    def test_invalid_pointer_stops_before_binary_lookup(self):
        for tag in ("latest\n", "b11960\nb11961\n"):
            with self.subTest(tag=tag):
                result, requests, archive = self.run_download(nightly_tag=tag)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(len(requests), 2)
                self.assertIsNone(archive)

    def test_missing_requested_rocm_archive_fails(self):
        result, _, archive = self.run_download(archive_versions=("9.9", "10.0"))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("No Ubuntu x64 ROCm archive found for requested version", result.stderr)
        self.assertIsNone(archive)
