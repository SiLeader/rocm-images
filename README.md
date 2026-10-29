# rocm-images

[English](README.md) | [日本語](README_ja.md)

Container images for AMD ROCm, with YAML manifests and Python tools for generating Dockerfiles, resolving build dependencies, and building and publishing images.

## Images

The image names and tag formats below are defined in [`manifests/`](manifests/).

| Manifest | Image | Tags |
| --- | --- | --- |
| [`base.yaml`](manifests/base.yaml) | `ghcr.io/sileader/rocm-images/base-ubuntu` | `26.04-rocm<rocm>-<gfx>` |
| [`comfyui.yaml`](manifests/comfyui.yaml) | `ghcr.io/sileader/rocm-images/comfyui` | `latest`, `<comfy-version>-rocm<rocm>-<gfx>` |
| [`llama.cpp.yaml`](manifests/llama.cpp.yaml) | `ghcr.io/sileader/rocm-images/llama.cpp` | `latest`, `<llama-cpp-version>-rocm<rocm>-<gfx>` |

The base image installs ROCm on Ubuntu. ComfyUI and llama.cpp use this shared base, with entrypoints for ComfyUI's `main.py` and `llama-server`, respectively.

[`manifests/matrix.yaml`](manifests/matrix.yaml) defines the ROCm versions and GPU targets used by all three images. The current matrix contains ROCm `10.1` and `gfx1201`; the default platform is `linux/amd64`. Application versions are defined in each application's manifest. These settings describe the build targets; they do not establish whether a tag has already been published.

To pull an image after it has been published:

```sh
docker pull ghcr.io/sileader/rocm-images/base-ubuntu:26.04-rocm10.1-gfx1201
```

## Repository layout

```text
manifests/          Image build configurations and shared build matrix
src/rocm_images/   Manifest parser, Dockerfile generator, dependency resolver, and build CLI
tests/             Tests for the build tools
test-data/         Test fixtures
```

## Requirements and setup

- Python 3.14 or later
- `uv` for the commands below
- Docker with BuildKit support for building images (generated Dockerfiles use heredocs)
- Registry authentication when pushing images

Run the following commands from the repository root:

```sh
uv sync
uv run rocm-images --help
```

Inspecting manifests and generating Dockerfiles do not require a running Docker daemon.

## Inspect dependencies

```sh
uv run rocm-images tree manifests/comfyui.yaml manifests/llama.cpp.yaml
uv run rocm-images tree manifests/comfyui.yaml --format yaml
uv run rocm-images tree manifests/comfyui.yaml --format json -o dependencies.json
```

The default text output shows the dependency tree and build order, with dependencies first. Shared build targets are deduplicated, and each matrix/platform combination is a separate target. Embedded stages are labeled `inline stage` and are not built separately.

YAML and JSON output contain `roots`, `build_order`, and `targets`. Each target includes its source manifest, platform, matrix values, expanded image name and tags, separate build dependencies, and inline sources.

## Generate Dockerfiles

```sh
uv run rocm-images generate-dockerfile manifests/comfyui.yaml -o generated/comfyui
```

`--output` / `-o` selects the output directory; the default is `dockerfiles`. A Dockerfile is generated for every combination of matrix values and platforms, together with any separately referenced base images. Filenames contain the manifest name, platform, matrix values, and an identifying hash.

Generating again overwrites matching files but does not remove files for old combinations. This command only generates Dockerfiles; it does not build, tag, or push images.

## Build and publish

```sh
uv run rocm-images build manifests/comfyui.yaml manifests/llama.cpp.yaml -o generated
uv run rocm-images build manifests/comfyui.yaml --push
```

The `build` command validates the complete dependency plan, generates Dockerfiles, and invokes `docker build` in dependency order. It applies every tag in `image.tags`. The default output directory is `dockerfiles`, and each target uses its source manifest's directory as the build context.

Use `--context` to set one context for all targets, or `--docker-command` (alias `--docker`) to select a Docker executable or command prefix:

```sh
uv run rocm-images build manifests/comfyui.yaml --context .
uv run rocm-images build manifests/comfyui.yaml --docker-command 'docker --context my-builder'
```

The Docker command is split into arguments and executed without shell expansion. Build results must be available to subsequent builds through the same Docker daemon so dependent images can reuse their base images.

Images are pushed only when `--push` is supplied. In that case, all tags for each target, including dependencies, are pushed immediately after that target builds successfully. A build or push failure stops the remaining work.

Each platform is built and pushed separately; the tool does not create multi-platform image manifests. Reusing a tag across matrix values or platforms causes later builds and pushes to update that tag. Use variant-specific tags when selecting a particular ROCm version or GPU target.

## Manifest format

Image manifests use `schema-version: 1` and support these fields:

| Field | Purpose |
| --- | --- |
| `vars` | String variables referenced as `${{ vars.NAME }}` |
| `matrix` | Axes of string values; all combinations are generated |
| `matrix-from-file` | Shared matrix file, used instead of an inline `matrix` |
| `platforms` | Target platforms; defaults to `[linux/amd64]` |
| `base-image` | External image reference or another manifest |
| `image` | Required image `name` and nonempty list of `tags` |
| `steps` | Ordered Dockerfile operations |

Matrix values are referenced as `${{ matrix.AXIS }}`. Ordinary shell expressions such as `${NAME}` are preserved. A shared matrix file contains `schema-version: 1` and `matrix`.

`matrix-from-file` and `base-image.source` paths are resolved relative to the manifest that declares them. For example, the application manifests reference the common base as follows:

```yaml
base-image:
  source: ./base.yaml
  with-matrix: ${{ matrix }}
  use-from: true
```

With `use-from: true`, the base is generated as a separate Dockerfile, and its expanded image name and first tag become the child's `FROM` reference. Without it, the referenced manifest is embedded as an earlier stage in the same Dockerfile. `with-matrix` can pass the full current matrix or an explicit mapping. Omitted dependency axes are inferred only when they have a single candidate, and dependencies must support the requested platform.

An external base uses `base-image.name`, an optional `tag`, and an optional platform-to-SHA-256 `digest` mapping. When `digest` is specified, it must include every requested platform.

Each step has exactly one of `run`, `workdir`, or `entrypoint`, plus an optional `name`. These generate `RUN`, `WORKDIR`, and an exec-form `ENTRYPOINT`, respectively. Every `run` is an independent instruction using the default shell. Multiline scripts are preserved using BuildKit heredocs.

Unknown keys, undefined expressions, duplicate YAML keys, and circular source references are rejected.

## Development

Run the build-tool tests:

```sh
uv run python -m unittest discover -s tests -v
```

## License

This project is licensed under the [Apache License 2.0](LICENSE). Software included in container images remains subject to its respective licenses.
