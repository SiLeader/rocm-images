"""Generate Dockerfiles, build images in dependency order and optionally push them."""

import argparse
from pathlib import Path
import shlex
import subprocess

from pydantic import ValidationError

from . import generate_dockerfile as generator
from .tree import create_tree


def build_images(configs, output=Path("dockerfiles"), docker_command="docker", push=False, context=None):
    """Validate the complete plan before writing Dockerfiles or invoking Docker."""
    command = shlex.split(docker_command)
    if not command:
        raise generator.ConfigError("docker command must not be empty")
    tree = create_tree(configs)
    references = {}
    for name, target in tree.targets.items():
        tags = []
        for tag in target.image.tags:
            reference = generator.single_line(target.image.name, "image.name") + ":" + generator.single_line(tag, "image.tags")
            if any(char.isspace() for char in reference) or reference.startswith("-"):
                raise generator.ConfigError(f"invalid image reference: {reference!r}")
            if reference not in tags:
                tags.append(reference)
        references[name] = tags
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    for name, content in tree.outputs.items():
        (output / name).write_text(content)
    for name, target in tree.targets.items():
        build_context = Path(context).resolve() if context is not None else target.source.parent
        arguments = [*command, "build", "--platform", target.platform, "-f", str(output / name)]
        for reference in references[name]:
            arguments.extend(["-t", reference])
        arguments.append(str(build_context))
        print(shlex.join(arguments), flush=True)
        subprocess.run(arguments, check=True)
        if push:
            for reference in references[name]:
                arguments = [*command, "push", reference]
                print(shlex.join(arguments), flush=True)
                subprocess.run(arguments, check=True)
    return tree


def create_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("configs", nargs="+", type=Path, help="Image configuration YAML files")
    parser.add_argument("--output", "-o", type=Path, default=Path("dockerfiles"), help="Dockerfile output directory (default: dockerfiles)")
    parser.add_argument("--push", action="store_true", help="Push every built image tag, including dependencies")
    parser.add_argument("--docker-command", "--docker", default="docker", help="Docker executable or command prefix (default: docker)")
    parser.add_argument("--context", type=Path, help="Build context for all images (default: each source YAML directory)")
    return parser


def run(args, parser):
    try:
        build_images(args.configs, args.output, args.docker_command, args.push, args.context)
    except subprocess.CalledProcessError as exc:
        parser.exit(1, f"error: command failed with exit code {exc.returncode}: {shlex.join(exc.cmd)}\n")
    except (generator.ConfigError, ValidationError, OSError, ValueError) as exc:
        parser.exit(2, f"error: {exc}\n")


def main(argv=None):
    parser = create_parser()
    run(parser.parse_args(argv), parser)


if __name__ == "__main__":
    main()
