import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import yaml

from rocm_images import build, tree
from rocm_images.generate_dockerfile import ConfigError


class TreeBuildTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name).resolve()

    def write(self, name, source=None, use_from=False, **changes):
        config = {
            "schema-version": 1,
            "image": {"name": f"example/{Path(name).stem}", "tags": ["v1", "latest"]},
            "base-image": {"name": "ubuntu"} if source is None else {
                "source": source, "use-from": use_from,
            },
        }
        config.update(changes)
        path = self.directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(config))
        return path

    def nested(self):
        base = self.write("base.yaml")
        middle = self.write("middle.yaml", "base.yaml", True)
        child = self.write("child.yaml", "middle.yaml")
        sibling = self.write("sibling.yaml", "base.yaml", True)
        return base, middle, child, sibling

    def test_nested_inline_dependencies_and_shared_base(self):
        base, middle, child, sibling = self.nested()
        plan = tree.create_tree([child, sibling, base, child])
        self.assertEqual([target.source for target in plan.targets.values()], [base, child, sibling])
        names = list(plan.targets)
        self.assertEqual(plan.targets[names[1]].dependencies, [names[0]])
        self.assertEqual(plan.targets[names[1]].inline_sources, [middle])
        self.assertIn("inline stage", plan.format_text())
        self.assertIn("└──", plan.format_text())
        data = plan.to_dict()
        self.assertEqual(data["build_order"], names)
        self.assertEqual(json.loads(json.dumps(data)), yaml.safe_load(yaml.safe_dump(data)))

    def test_matrix_selection_deduplicates_base(self):
        self.write("base.yaml", matrix={"gfx": ["a", "b"]})
        child = self.write("child.yaml", **{
            "matrix": {"variant": ["one", "two"]},
            "base-image": {"source": "base.yaml", "use-from": True, "with-matrix": {"gfx": "b"}},
        })
        plan = tree.create_tree([child])
        self.assertEqual(len(plan.targets), 3)
        self.assertEqual(next(iter(plan.targets.values())).matrix, {"gfx": "b"})

    def test_build_order_all_tags_context_and_default_no_push(self):
        base, _, child, sibling = self.nested()
        output = self.directory / "dockerfiles"
        with patch("rocm_images.build.subprocess.run") as run, contextlib.redirect_stdout(io.StringIO()):
            plan = build.build_images([child, sibling], output, "custom-docker --debug")
        self.assertEqual(run.call_count, 3)
        for call, (name, target) in zip(run.call_args_list, plan.targets.items()):
            args = call.args[0]
            self.assertEqual(args[:3], ["custom-docker", "--debug", "build"])
            self.assertIn(target.platform, args)
            self.assertEqual(args[-1], str(target.source.parent))
            self.assertIn(f"{target.image.name}:v1", args)
            self.assertIn(f"{target.image.name}:latest", args)
            self.assertEqual((output / name).read_text(), plan.outputs[name])
            self.assertTrue(call.kwargs["check"])

    def test_push_only_when_requested_and_context_override(self):
        path = self.write("image.yaml")
        with patch("rocm_images.build.subprocess.run") as run, contextlib.redirect_stdout(io.StringIO()):
            build.build_images([path], self.directory / "out", push=True, context=self.directory / "context")
        commands = [call.args[0] for call in run.call_args_list]
        self.assertEqual(commands[0][-1], str(self.directory / "context"))
        self.assertEqual(commands[1:], [["docker", "push", "example/image:v1"], ["docker", "push", "example/image:latest"]])

    def test_build_failure_stops_before_push_and_dependents(self):
        _, _, child, _ = self.nested()
        with patch("rocm_images.build.subprocess.run", side_effect=subprocess.CalledProcessError(9, ["docker", "build"])) as run:
            with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(subprocess.CalledProcessError):
                build.build_images([child], self.directory / "out", push=True)
        self.assertEqual(run.call_count, 1)

    def test_invalid_plan_has_no_side_effects(self):
        good = self.write("good.yaml")
        bad = self.write("bad.yaml", "bad.yaml", True)
        output = self.directory / "out"
        with patch("rocm_images.build.subprocess.run") as run:
            with self.assertRaisesRegex(ConfigError, "circular"):
                build.build_images([good, bad], output)
        run.assert_not_called()
        self.assertFalse(output.exists())

    def test_platform_variants(self):
        path = self.write("image.yaml", platforms=["linux/amd64", "linux/arm64"])
        plan = tree.create_tree([path])
        self.assertEqual([target.platform for target in plan.targets.values()], ["linux/amd64", "linux/arm64"])

    def test_tree_cli_formats(self):
        path = self.write("image.yaml")
        for format in ("text", "yaml", "json"):
            with self.subTest(format=format), contextlib.redirect_stdout(io.StringIO()) as stdout:
                tree.main([str(path), "--format", format])
                content = stdout.getvalue()
                if format == "text":
                    self.assertIn("Build order", content)
                else:
                    self.assertEqual(len(yaml.safe_load(content)["targets"]), 1)

    def test_build_cli_with_replacement_executable(self):
        _, _, child, sibling = self.nested()
        log = self.directory / "commands.jsonl"
        executable = self.directory / "fake docker"
        executable.write_text(
            f"#!{sys.executable}\n"
            "import json, sys\n"
            f"with open({str(log)!r}, 'a') as stream:\n"
            "    stream.write(json.dumps(sys.argv[1:]) + '\\n')\n"
        )
        executable.chmod(0o755)
        # Quote the executable path to also exercise command-prefix parsing.
        command = [str(Path(sys.executable).with_name("rocm-images")), "build",
                   str(child), str(sibling), "-o", str(self.directory / "out"),
                   "--docker", f"'{executable}'"]
        for push in (False, True):
            with self.subTest(push=push):
                log.write_text("")
                subprocess.run(command + (["--push"] if push else []),
                               check=True, capture_output=True, text=True)
                calls = [json.loads(line) for line in log.read_text().splitlines()]
                self.assertEqual(sum(call[0] == "build" for call in calls), 3)
                self.assertEqual(sum(call[0] == "push" for call in calls), 6 if push else 0)


if __name__ == "__main__":
    unittest.main()
