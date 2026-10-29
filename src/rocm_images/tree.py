"""Show image build dependencies as a readable tree, YAML or JSON."""

import argparse
from dataclasses import asdict, dataclass, field
import itertools
import json
from pathlib import Path

from pydantic import ValidationError
import yaml

from . import generate_dockerfile as generator


@dataclass
class DependencyTree:
    # Insertion order is topological: every dependency precedes its consumers.
    targets: dict[str, generator.BuildTarget] = field(default_factory=dict)
    outputs: dict[str, str] = field(default_factory=dict)
    roots: list[str] = field(default_factory=list)

    def to_dict(self):
        targets = {}
        for name, target in self.targets.items():
            data = asdict(target)
            data["source"] = str(target.source)
            data["image"] = target.image.model_dump()
            data["inline_sources"] = [str(path) for path in target.inline_sources]
            targets[name] = data
        return {"roots": self.roots, "build_order": list(self.targets), "targets": targets}

    def format_text(self):
        lines = []

        def visit(name, prefix="", branch=""):
            target = self.targets[name]
            selection = ", ".join(f"{key}={value}" for key, value in target.matrix.items())
            tags = ", ".join(f"{target.image.name}:{tag}" for tag in target.image.tags)
            lines.append(f"{prefix}{branch}{target.source} [{target.platform}"
                         f"{', ' + selection if selection else ''}] -> {tags}")
            children = [(dep, False) for dep in target.dependencies]
            children += [(path, True) for path in target.inline_sources]
            child_prefix = prefix + ("    " if branch == "└── " else "│   " if branch else "")
            for index, (child, inline) in enumerate(children):
                child_branch = "└── " if index == len(children) - 1 else "├── "
                if inline:
                    lines.append(f"{child_prefix}{child_branch}{child} (inline stage)")
                else:
                    visit(child, child_prefix, child_branch)

        for root in self.roots:
            visit(root)
        lines.append("\nBuild order (dependencies first):")
        lines.extend(f"  {index}. {name}" for index, name in enumerate(self.targets, 1))
        return "\n".join(lines) + "\n"


def create_tree(configs):
    """Resolve and validate all variants without writing files or running Docker."""
    tree = DependencyTree()
    for path in configs:
        path = Path(path).resolve()
        config, axes = generator.load_config(path)
        for platform in config.platforms:
            for values in itertools.product(*axes.values()):
                matrix = dict(zip(axes, values))
                instance = generator.Generator(platform)
                instance.generate(path, matrix)
                generator.merge_outputs(tree.outputs, instance.outputs)
                for name, target in instance.targets.items():
                    if name in tree.targets and tree.targets[name] != target:
                        raise generator.ConfigError(f"conflicting build targets for output: {name}")
                    tree.targets[name] = target
                root = generator.output_name(path, platform, matrix)
                if root not in tree.roots:
                    tree.roots.append(root)
    return tree


def create_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("configs", nargs="+", type=Path, help="Image configuration YAML files")
    parser.add_argument("--format", "-f", choices=("text", "yaml", "json"), default="text")
    parser.add_argument("--output", "-o", type=Path, help="Write to a file instead of stdout")
    return parser


def run(args, parser):
    try:
        tree = create_tree(args.configs)
        if args.format == "json":
            content = json.dumps(tree.to_dict(), ensure_ascii=False, indent=2) + "\n"
        elif args.format == "yaml":
            content = yaml.safe_dump(tree.to_dict(), allow_unicode=True, sort_keys=False)
        else:
            content = tree.format_text()
        if args.output is None:
            print(content, end="")
        else:
            args.output.write_text(content)
    except (generator.ConfigError, ValidationError, OSError) as exc:
        parser.exit(2, f"error: {exc}\n")


def main(argv=None):
    parser = create_parser()
    run(parser.parse_args(argv), parser)


if __name__ == "__main__":
    main()
