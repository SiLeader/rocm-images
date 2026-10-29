"""Generate Dockerfiles for every matrix/platform combination of a YAML config."""

import argparse
from dataclasses import dataclass
import hashlib
import itertools
import json
from pathlib import Path
import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
import yaml


class ConfigError(ValueError):
    pass


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


Text = Annotated[str, Field(min_length=1)]
Values = Annotated[list[Text], Field(min_length=1)]


class BaseImage(Model):
    name: Text | None = None
    tag: Text | None = None
    digest: dict[str, Text] | None = None
    source: Text | None = None
    with_matrix: dict[str, Text] | Text | None = Field(default=None, alias="with-matrix")
    use_from: bool = Field(default=False, alias="use-from")

    @model_validator(mode="after")
    def check_reference(self):
        if (self.name is None) == (self.source is None):
            raise ValueError("base-image requires exactly one of name or source")
        if self.source is not None and (self.tag is not None or self.digest is not None):
            raise ValueError("source cannot be combined with tag or digest")
        if self.name is not None and self.with_matrix is not None:
            raise ValueError("with-matrix requires source")
        if self.use_from and self.source is None:
            raise ValueError("use-from requires source")
        return self


class Image(Model):
    name: Text
    tags: Values


class Step(Model):
    name: Text | None = None
    workdir: Text | None = None
    run: Text | None = None
    entrypoint: Values | None = None

    @model_validator(mode="after")
    def check_operation(self):
        if sum(value is not None for value in (self.workdir, self.run, self.entrypoint)) != 1:
            raise ValueError("each step requires exactly one of workdir, run or entrypoint")
        return self


class MatrixFile(Model):
    schema_version: Literal[1] = Field(alias="schema-version")
    matrix: dict[str, Values]


class Config(Model):
    schema_version: Literal[1] = Field(alias="schema-version")
    platforms: Values = Field(default_factory=lambda: ["linux/amd64"])
    vars: dict[str, str] = Field(default_factory=dict)
    matrix: dict[str, Values] = Field(default_factory=dict)
    matrix_from_file: Text | None = Field(default=None, alias="matrix-from-file")
    base_image: BaseImage = Field(alias="base-image")
    image: Image
    steps: list[Step] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_matrix(self):
        if self.matrix and self.matrix_from_file is not None:
            raise ValueError("matrix and matrix-from-file cannot be combined")
        return self


class UniqueKeyLoader(yaml.SafeLoader):
    pass


def construct_mapping(loader, node):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node)
        if not isinstance(key, str):
            raise ConfigError("YAML mapping keys must be strings")
        if key in result:
            raise ConfigError(f"duplicate YAML key: {key}")
        result[key] = loader.construct_object(value_node)
    return result


UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, construct_mapping)


def read_yaml(path):
    try:
        return yaml.load(path.read_text(), Loader=UniqueKeyLoader)
    except (OSError, UnicodeError, yaml.YAMLError, ConfigError) as exc:
        raise ConfigError(f"{path}: {exc}") from exc


def read_model(path, model):
    try:
        return model.model_validate(expand(read_yaml(path), {}, {}, path, yaml_only=True))
    except (OSError, yaml.YAMLError, ValidationError, ConfigError) as exc:
        raise ConfigError(f"{path}: {exc}") from exc


def load_config(path):
    config = read_model(path, Config)
    axes = config.matrix
    if config.matrix_from_file is not None:
        axes = read_model(path.parent / config.matrix_from_file, MatrixFile).matrix
    return config, axes


EXPRESSION = re.compile(r"\$\{\{\s*([^{}]*?)\s*\}\}")


def expand(value, variables, matrix, source=None, *, yaml_only=False):
    def lookup(expression_match):
        expression = expression_match.group(1)
        if expression.startswith("readYaml("):
            match = re.fullmatch(r"readYaml\(\s*(['\"])([^'\"\r\n]+)\1\s*\)((?:\.[\w-]+)*)", expression)
            if match is None or source is None:
                raise ConfigError(f"invalid readYaml expression: {expression}")
            path = source.parent / match.group(2)
            result = read_yaml(path)
            for key in match.group(3).split(".")[1:]:
                if not isinstance(result, dict) or key not in result:
                    raise ConfigError(f"{path}: undefined YAML key in expression: {expression}")
                result = result[key]
            return result
        if yaml_only:
            return expression_match.group(0)
        if expression == "matrix":
            return dict(matrix)
        for prefix, namespace in (("vars.", variables), ("matrix.", matrix)):
            if expression.startswith(prefix) and expression[len(prefix):] in namespace:
                return namespace[expression[len(prefix):]]
        raise ConfigError(f"undefined expression: ${{{{ {expression} }}}}")

    if isinstance(value, str):
        match = EXPRESSION.fullmatch(value)
        if match:
            return lookup(match)

        def replace(match):
            replacement = lookup(match)
            if not isinstance(replacement, str):
                raise ConfigError("non-string expression value cannot be embedded in a string")
            return replacement

        return EXPRESSION.sub(replace, value)
    if isinstance(value, list):
        return [expand(item, variables, matrix, source, yaml_only=yaml_only) for item in value]
    if isinstance(value, dict):
        return {key: expand(item, variables, matrix, source, yaml_only=yaml_only) for key, item in value.items()}
    return value


def select_matrix(axes, selected):
    unknown = selected.keys() - axes.keys()
    if unknown:
        raise ConfigError(f"unknown matrix axes: {', '.join(sorted(unknown))}")
    result = {}
    for key, values in axes.items():
        if key in selected:
            if selected[key] not in values:
                raise ConfigError(f"matrix.{key}: {selected[key]!r} is not in {values!r}")
            result[key] = selected[key]
        elif len(values) == 1:
            result[key] = values[0]
        else:
            raise ConfigError(f"dependency requires with-matrix selection for {key}")
    return result


def single_line(value, label):
    if not value or any(char in value for char in "\r\n\0"):
        raise ConfigError(f"{label} must be a nonempty single line without NUL")
    return value


@dataclass
class BuildTarget:
    source: Path
    platform: str
    matrix: dict[str, str]
    image: Image
    dependencies: list[str]
    inline_sources: list[Path]


class Generator:
    def __init__(self, platform):
        self.platform = platform
        self.stages = []
        self.outputs = {}
        self.targets = {}

    def generate(self, path, matrix, ancestors=()):
        path = path.resolve()
        self.stages = []
        self.outputs = {}
        self.targets = {}
        self.dependencies = []
        self.inline_sources = []
        _, self.config, matrix = self.add_stage(path, matrix, ancestors)
        content = "# syntax=docker/dockerfile:1\n\n" + "\n\n".join(self.stages) + "\n"
        merge_outputs(self.outputs, {output_name(path, self.platform, matrix): content})
        self.targets[output_name(path, self.platform, matrix)] = BuildTarget(
            path, self.platform, matrix, self.config.image,
            list(dict.fromkeys(self.dependencies)), self.inline_sources,
        )
        return content

    def add_stage(self, path, selected, ancestors):
        if path in ancestors:
            raise ConfigError("circular source reference: " + " -> ".join(map(str, (*ancestors, path))))
        config, axes = load_config(path)
        matrix = select_matrix(axes, selected)
        if self.platform not in config.platforms:
            raise ConfigError(f"{path}: platform {self.platform!r} is not supported")
        config = Config.model_validate(expand(config.model_dump(by_alias=True), config.vars, matrix))
        base = config.base_image
        if base.source is not None:
            passed = base.with_matrix if base.with_matrix is not None else {}
            if not isinstance(passed, dict):
                raise ConfigError("with-matrix must expand to a mapping")
            source = (path.parent / base.source).resolve()
            if base.use_from:
                dependency = Generator(self.platform)
                dependency.generate(source, passed, (*ancestors, path))
                image = dependency.config.image
                reference = single_line(image.name, "image.name") + ":" + single_line(image.tags[0], "image.tags[0]")
                if any(char.isspace() for char in reference):
                    raise ConfigError("base image reference cannot contain whitespace")
                merge_outputs(self.outputs, dependency.outputs)
                self.targets.update(dependency.targets)
                self.dependencies.append(next(reversed(dependency.targets)))
            else:
                self.inline_sources.append(source)
                reference, _, _ = self.add_stage(source, passed, (*ancestors, path))
        else:
            reference = single_line(base.name, "base-image.name")
            if base.tag is not None:
                reference += ":" + single_line(base.tag, "base-image.tag")
            if base.digest is not None:
                digest = base.digest.get(self.platform)
                if digest is None:
                    raise ConfigError(f"missing base-image digest for {self.platform}")
                if not re.fullmatch(r"sha256:[0-9a-fA-F]{64}", digest):
                    raise ConfigError(f"invalid SHA-256 digest: {digest}")
                reference += "@" + digest
            if any(char.isspace() for char in reference):
                raise ConfigError("base image reference cannot contain whitespace")
        stage = f"stage_{len(self.stages)}"
        lines = [f"FROM {reference} AS {stage}"]
        for step in config.steps:
            if step.name:
                lines.append("# " + single_line(step.name, "step.name"))
            if step.workdir is not None:
                lines.append("WORKDIR " + single_line(step.workdir, "workdir"))
            elif step.entrypoint is not None:
                lines.append("ENTRYPOINT " + json.dumps(step.entrypoint, ensure_ascii=False))
            else:
                if "\0" in step.run:
                    raise ConfigError("run cannot contain NUL")
                delimiter = "ROCM_IMAGES_RUN"
                while delimiter in step.run.splitlines():
                    delimiter += "_"
                lines.extend([f"RUN <<'{delimiter}'", step.run.rstrip("\n"), delimiter])
        self.stages.append("\n".join(lines))
        return stage, config, matrix


def output_name(path, platform, matrix):
    identity = json.dumps([platform, sorted(matrix.items())], ensure_ascii=True)
    suffix = hashlib.sha256(identity.encode()).hexdigest()[:12]
    parts = [path.stem, platform, *(f"{key}={value}" for key, value in sorted(matrix.items()))]
    readable = re.sub(r"[^A-Za-z0-9_.=-]+", "-", "-".join(parts))[:160]
    return f"{readable}-{suffix}.Dockerfile"


def merge_outputs(outputs, additions):
    for filename, content in additions.items():
        if filename in outputs and outputs[filename] != content:
            raise ConfigError(f"conflicting Dockerfiles for output: {filename}")
        outputs[filename] = content


def generate_all(path):
    path = path.resolve()
    config, axes = load_config(path)
    outputs = {}
    for platform in config.platforms:
        for values in itertools.product(*axes.values()):
            matrix = dict(zip(axes, values))
            generator = Generator(platform)
            generator.generate(path, matrix)
            merge_outputs(outputs, generator.outputs)
    return outputs


def create_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path, help="Image configuration YAML")
    parser.add_argument("--output", "-o", type=Path, default=Path("dockerfiles"), help="Output directory (default: dockerfiles)")
    return parser


def run(args, parser):
    try:
        # Resolve every combination before writing so configuration errors leave no partial output.
        outputs = generate_all(args.config)
        args.output.mkdir(parents=True, exist_ok=True)
        for filename, content in outputs.items():
            target = args.output / filename
            target.write_text(content)
            print(target)
    except (ConfigError, ValidationError, OSError) as exc:
        parser.exit(2, f"error: {exc}\n")


def main(argv=None):
    parser = create_parser()
    run(parser.parse_args(argv), parser)


if __name__ == "__main__":
    main()
