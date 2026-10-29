import itertools
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from pydantic import ValidationError
import yaml

from rocm_images import generate_dockerfile as generator

ROOT = Path(__file__).resolve().parents[1] / "manifests"


class GeneratorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)

    def write(self, name, **changes):
        config = {
            "schema-version": 1,
            "base-image": {"name": "ubuntu", "tag": "26.04"},
            "image": {"name": "example/test", "tags": ["test"]},
            "steps": [],
        }
        config.update(changes)
        path = self.directory / name
        path.write_text(yaml.safe_dump(config))
        return path

    def test_all_matrix_and_platform_combinations(self):
        path = self.write("image.yaml", platforms=["linux/amd64", "linux/arm64"],
                          matrix={"gfx": ["a/b", "a-b"], "rocm": ["9.9", "10.1"]},
                          steps=[{"run": "echo ${{ matrix.gfx }} ${{ matrix.rocm }}"}])
        outputs = generator.generate_all(path)
        self.assertEqual(len(outputs), 8)
        for gfx in ("a/b", "a-b"):
            for rocm in ("9.9", "10.1"):
                self.assertEqual(sum(f"echo {gfx} {rocm}\n" in text for text in outputs.values()), 2)
        self.assertTrue(all("/" not in name for name in outputs))

    def test_dependency_matrix_and_variable_scope(self):
        self.write("base.yaml", matrix={"gfx": ["a", "b"]}, vars={"version": "base"},
                   steps=[{"run": "echo ${{ vars.version }} ${{ matrix.gfx }}"}])
        path = self.write("child.yaml", matrix={"gfx": ["a", "b"]}, vars={"version": "child"},
                          **{"base-image": {"source": "base.yaml", "with-matrix": "${{ matrix }}"}},
                          steps=[{"run": "echo ${{ vars.version }} ${{ matrix.gfx }}"}])
        outputs = generator.generate_all(path)
        self.assertEqual(len(outputs), 2)
        for text in outputs.values():
            self.assertIn("FROM ubuntu:26.04 AS stage_0", text)
            self.assertIn("FROM stage_0 AS stage_1", text)
            self.assertIn("echo base", text)
            self.assertIn("echo child", text)

    def test_real_configs_and_shell_syntax(self):
        for name in ("base.yaml", "comfyui.yaml", "llama.cpp.yaml"):
            config, axes = generator.load_config(ROOT / name)
            matrices = [dict(zip(axes, values)) for values in itertools.product(*axes.values())]
            outputs = generator.generate_all(ROOT / name)
            self.assertEqual(len(outputs), len(matrices) * (1 if name == "base.yaml" else 2))
            for text in outputs.values():
                self.assertNotIn("${{", text)
            self.assertTrue(any("ubuntu:26.04@sha256:" in text for text in outputs.values()))
            if name != "base.yaml":
                for matrix in matrices:
                    child = outputs[generator.output_name(ROOT / name, "linux/amd64", matrix)]
                    self.assertIn(f"FROM ghcr.io/sileader/rocm-images/base-ubuntu:26.04-rocm{matrix['rocm']}-{matrix['gfx']} AS stage_0", child)
                    self.assertNotIn("Install ROCm", child)
        config = generator.read_model(ROOT / "llama.cpp.yaml", generator.Config)
        run = next(step.run for step in config.steps if step.run)
        run = generator.expand(run, config.vars, {"gfx": "gfx1201", "rocm": "10.1"})
        self.assertIn('${asset_digest#sha256:}', run)
        subprocess.run(["/bin/sh", "-n"], input=run, text=True, check=True)

    def test_use_from_separates_base_and_expands_image_reference(self):
        base = self.write("base.yaml", platforms=["linux/amd64", "linux/arm64"],
                          matrix={"gfx": ["a", "b"]}, vars={"registry": "example"},
                          image={"name": "${{ vars.registry }}/base", "tags": ["gfx-${{ matrix.gfx }}", "latest"]},
                          steps=[{"run": "echo base ${{ matrix.gfx }}"}])
        child = self.write("child.yaml", platforms=["linux/amd64", "linux/arm64"],
                           matrix={"gfx": ["a", "b"]},
                           **{"base-image": {"source": "base.yaml", "with-matrix": "${{ matrix }}", "use-from": True}},
                           steps=[{"run": "echo child"}])
        outputs = generator.generate_all(child)
        self.assertEqual(len(outputs), 8)
        for platform in ("linux/amd64", "linux/arm64"):
            for gfx in ("a", "b"):
                matrix = {"gfx": gfx}
                base_text = outputs[generator.output_name(base, platform, matrix)]
                child_text = outputs[generator.output_name(child, platform, matrix)]
                self.assertIn("FROM ubuntu:26.04 AS stage_0", base_text)
                self.assertIn(f"echo base {gfx}", base_text)
                self.assertIn(f"FROM example/base:gfx-{gfx} AS stage_0", child_text)
                self.assertNotIn("echo base", child_text)
                self.assertIn("echo child", child_text)
        self.assertEqual(generator.generate_all(base), {key: value for key, value in outputs.items() if key.startswith("base-")})

    def test_use_from_deduplicates_shared_base(self):
        self.write("base.yaml", matrix={"gfx": ["a"]})
        child = self.write("child.yaml", matrix={"variant": ["one", "two"]},
                           **{"base-image": {"source": "base.yaml", "use-from": True}},
                           steps=[{"run": "echo ${{ matrix.variant }}"}])
        outputs = generator.generate_all(child)
        self.assertEqual(len(outputs), 3)
        self.assertEqual(sum(name.startswith("base-") for name in outputs), 1)

    def test_nested_use_from_and_inline_sources(self):
        self.write("base.yaml", image={"name": "example/base", "tags": ["v1"]},
                   steps=[{"run": "echo base"}])
        self.write("middle.yaml", image={"name": "example/middle", "tags": ["v2"]},
                   **{"base-image": {"source": "base.yaml", "use-from": True}},
                   steps=[{"run": "echo middle"}])
        for use_from in (False, True):
            with self.subTest(use_from=use_from):
                child = self.write("child.yaml", **{"base-image": {"source": "middle.yaml", "use-from": use_from}})
                outputs = generator.generate_all(child)
                text = outputs[generator.output_name(child, "linux/amd64", {})]
                self.assertEqual(len(outputs), 3 if use_from else 2)
                self.assertIn("FROM example/middle:v2" if use_from else "FROM example/base:v1", text)
                self.assertEqual("echo middle" in text, not use_from)
                self.assertNotIn("echo base", text)

    def test_use_from_requires_dependency_image_name(self):
        for image in ({"tags": ["v1"]}, {"name": "", "tags": ["v1"]}):
            with self.subTest(image=image):
                self.write("base.yaml", image=image)
                child = self.write("child.yaml", **{"base-image": {"source": "base.yaml", "use-from": True}})
                with self.assertRaisesRegex(generator.ConfigError, r"image\.name"):
                    generator.generate_all(child)

    def test_use_from_validation(self):
        for base_image in ({"name": "ubuntu", "use-from": True},
                           {"source": "child.yaml", "use-from": True},
                           {"source": "child.yaml", "use-from": "true"}):
            with self.subTest(base_image=base_image):
                child = self.write("child.yaml", **{"base-image": base_image})
                with self.assertRaises(generator.ConfigError):
                    generator.generate_all(child)
        self.write("base.yaml", **{"base-image": {"source": "child.yaml"}})
        child = self.write("child.yaml", **{"base-image": {"source": "base.yaml", "use-from": True}})
        with self.assertRaisesRegex(generator.ConfigError, "circular source reference"):
            generator.generate_all(child)

    def test_use_from_retains_dependency_validation(self):
        cases = [
            {"platforms": ["linux/arm64"]},
            {"matrix": {"gfx": ["a", "b"]}},
            {"image": {"name": "example/base\nRUN true", "tags": ["v1"]}},
            {"image": {"name": "example/base", "tags": ["bad tag"]}},
        ]
        for changes in cases:
            with self.subTest(changes=changes):
                self.write("base.yaml", **changes)
                child = self.write("child.yaml", **{"base-image": {"source": "base.yaml", "use-from": True}})
                with self.assertRaises(generator.ConfigError):
                    generator.generate_all(child)

    def test_heredoc_delimiter_collision(self):
        run = "cat <<'EOF'\nROCM_IMAGES_RUN\nEOF\n"
        path = self.write("image.yaml", steps=[{"run": run}])
        text = next(iter(generator.generate_all(path).values()))
        self.assertIn("RUN <<'ROCM_IMAGES_RUN_'", text)
        self.assertIn(run, text)

    def test_invalid_configs(self):
        cases = [
            {"unknown": True},
            {"steps": [{"run": "true", "workdir": "/tmp"}]},
            {"steps": [{"run": "echo ${{ vars.missing }}"}]},
            {"base-image": {"source": "image.yaml"}},
            {"base-image": {"name": "ubuntu", "digest": {"linux/arm64": "sha256:" + "a" * 64}}},
            {"matrix": {"gfx": []}},
        ]
        for changes in cases:
            with self.subTest(changes=changes):
                path = self.write("image.yaml", **changes)
                with self.assertRaises((generator.ConfigError, ValidationError)):
                    generator.generate_all(path)

    def test_external_matrix_relative_to_config(self):
        (self.directory / "matrix.yaml").write_text("schema-version: 1\nmatrix:\n  gfx: [a, b]\n")
        path = self.write("image.yaml", **{"matrix-from-file": "matrix.yaml"})
        self.assertEqual(len(generator.generate_all(path)), 2)

    def test_read_yaml_matrix_relative_to_config(self):
        (self.directory / "matrix.yaml").write_text("matrix:\n  gfx: [a, b]\n")
        path = self.write("image.yaml", matrix={"gfx": "${{ readYaml('matrix.yaml').matrix.gfx }}"},
                          steps=[{"run": "echo ${{ matrix.gfx }}"}])
        outputs = generator.generate_all(path)
        self.assertEqual(len(outputs), 2)
        for gfx in ("a", "b"):
            self.assertTrue(any(f"echo {gfx}\n" in text for text in outputs.values()))

    def test_read_yaml_mapping_and_string(self):
        (self.directory / "data.yaml").write_text("matrix:\n  gfx: [a]\nversion: v1\n")
        path = self.write("image.yaml", matrix='${{ readYaml("data.yaml").matrix }}',
                          vars={"version": "${{ readYaml('data.yaml').version }}"},
                          image={"name": "example/test", "tags": ["tag-${{ readYaml('data.yaml').version }}"]},
                          steps=[{"run": "echo ${{ vars.version }} ${{ matrix.gfx }}"}])
        config, axes = generator.load_config(path)
        self.assertEqual(axes, {"gfx": ["a"]})
        self.assertEqual(config.image.tags, ["tag-v1"])
        self.assertIn("echo v1 a\n", next(iter(generator.generate_all(path).values())))

    def test_read_yaml_preserves_deferred_expressions(self):
        run = "echo ${{vars.version}} ${{ matrix.gfx}}"
        path = self.write("image.yaml", matrix={"gfx": ["a"]}, vars={"version": "v1"},
                          steps=[{"run": run}])
        config, _ = generator.load_config(path)
        self.assertEqual(config.steps[0].run, run)
        self.assertIn("echo v1 a\n", next(iter(generator.generate_all(path).values())))

    def test_read_yaml_dependency_relative_to_own_manifest(self):
        (self.directory / "base").mkdir()
        (self.directory / "base" / "matrix.yaml").write_text("gfx: [a, b]\n")
        self.write("base/image.yaml", matrix={"gfx": "${{ readYaml('matrix.yaml').gfx }}"},
                   steps=[{"run": "echo base ${{ matrix.gfx }}"}])
        for use_from in (False, True):
            with self.subTest(use_from=use_from):
                path = self.write("image.yaml", **{"base-image": {
                    "source": "base/image.yaml", "with-matrix": {"gfx": "b"}, "use-from": use_from,
                }})
                outputs = generator.generate_all(path)
                self.assertTrue(any("echo base b\n" in text for text in outputs.values()))

    def test_read_yaml_invalid_references(self):
        (self.directory / "data.yaml").write_text("matrix:\n  gfx: [a]\n")
        for expression, message in (
            ("readYaml('missing.yaml').matrix.gfx", "missing.yaml"),
            ("readYaml('data.yaml').matrix.missing", "undefined YAML key"),
            ("readYaml('data.yaml').matrix.gfx.missing", "undefined YAML key"),
            ("readYaml(data.yaml).matrix.gfx", "invalid readYaml expression"),
        ):
            with self.subTest(expression=expression):
                path = self.write("image.yaml", matrix={"gfx": "${{ " + expression + " }}"})
                with self.assertRaisesRegex(generator.ConfigError, message):
                    generator.generate_all(path)

    def test_read_yaml_retains_validation(self):
        for content in ("gfx: []\n", "gfx: [1]\n", "gfx: [a]\ngfx: [b]\n", "gfx: [\n"):
            with self.subTest(content=content):
                (self.directory / "data.yaml").write_text(content)
                path = self.write("image.yaml", matrix={"gfx": "${{ readYaml('data.yaml').gfx }}"})
                with self.assertRaises(generator.ConfigError):
                    generator.generate_all(path)
        path = self.write("image.yaml", steps=[{"run": "echo ${{ readYaml('data.yaml') }}"}])
        (self.directory / "data.yaml").write_text("gfx: [a]\n")
        with self.assertRaisesRegex(generator.ConfigError, "cannot be embedded"):
            generator.generate_all(path)

    def test_duplicate_keys(self):
        path = self.directory / "bad.yaml"
        path.write_text("schema-version: 1\nschema-version: 1\n")
        with self.assertRaisesRegex(generator.ConfigError, "duplicate YAML key"):
            generator.generate_all(path)

    def test_cli_directory_and_no_partial_output(self):
        path = self.write("image.yaml", matrix={"gfx": ["a", "b"]})
        output = self.directory / "nested" / "dockerfiles"
        command = [str(Path(sys.executable).with_name("rocm-images")), "generate-dockerfile", str(path), "-o", str(output)]
        subprocess.run(command, check=True, capture_output=True, text=True)
        self.assertEqual(len(list(output.glob("*.Dockerfile"))), 2)
        path = self.write("image.yaml", steps=[{"run": "${{ vars.missing }}"}])
        failed_output = self.directory / "failed"
        command[-1] = str(failed_output)
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertFalse(failed_output.exists())
        self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
