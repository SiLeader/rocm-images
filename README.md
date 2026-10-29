# rocm-images

[English](README.md) | [日本語](README_ja.md)

Container images for AMD ROCm on Ubuntu 26.04. This repository contains Dockerfiles for a shared ROCm base, ComfyUI, and llama.cpp, plus a GitHub Actions workflow for publishing them to GHCR.

## Images

The build targets and tags below are configured in [Publish images](.github/workflows/publish.yml). They describe the configured builds, not whether those tags have already been published. All images target x86-64 (`linux/amd64`).

| Image | Version | ROCm | GPU target | Tag format |
| --- | --- | --- | --- | --- |
| `ghcr.io/sileader/rocm-images/base-ubuntu` | Ubuntu `26.04` | `10.0`, `10.1` | `gfx1201` | `26.04-rocm<rocm>-<gfx>` |
| `ghcr.io/sileader/rocm-images/comfyui` | `v0.43.0` | `10.0`, `10.1` | `gfx1201` | `<comfy-version>-rocm<rocm>-<gfx>` |
| `ghcr.io/sileader/rocm-images/llama.cpp` | `v0.8.0` | `10.0` | `gfx1201` | `<llama-cpp-version>-rocm<rocm>-<gfx>` |

The workflow publishes versioned tags only; it does not publish `latest`.

To pull images after they have been published:

```sh
docker pull ghcr.io/sileader/rocm-images/base-ubuntu:26.04-rocm10.0-gfx1201
docker pull ghcr.io/sileader/rocm-images/comfyui:v0.43.0-rocm10.0-gfx1201
docker pull ghcr.io/sileader/rocm-images/llama.cpp:v0.8.0-rocm10.0-gfx1201
```

- **Base:** installs `amdrocm<rocm>-<gfx>` from AMD's stable APT repository and sets `LD_LIBRARY_PATH=/opt/rocm/lib`.
- **ComfyUI:** uses the shared base, clones the selected ComfyUI version, and installs ROCm PyTorch packages and ComfyUI requirements in a Python virtual environment. Its entrypoint is `/opt/comfyui/venv/bin/python main.py`, with default arguments `--listen 0.0.0.0`.
- **llama.cpp:** uses the shared base and copies prebuilt binaries from the build context. Its entrypoint is `/opt/llama.cpp/llama-server`; supply server arguments when running the container.

## Repository layout

```text
base/
  Dockerfile                 Ubuntu 26.04 with ROCm
  amdrocm-stable.sources     AMD stable APT repository configuration
comfyui/
  Dockerfile                 ComfyUI and ROCm PyTorch packages
llama.cpp/
  Dockerfile                 Image using prebuilt llama.cpp binaries
  download.sh                Download and verify the requested release
.github/workflows/
  publish.yml                Manual build and publish workflow
```

## Local builds

Docker and access to the upstream package and source repositories are required. Run the following commands from the repository root. Build arguments have no defaults, so specify each argument shown.

Build the shared base first. Application Dockerfiles select it by its exact versioned tag.

```sh
docker build --platform linux/amd64 \
  --build-arg ROCM_VERSION=10.0 \
  --build-arg GFX_TARGET=gfx1201 \
  -t ghcr.io/sileader/rocm-images/base-ubuntu:26.04-rocm10.0-gfx1201 \
  ./base
```

### ComfyUI

```sh
docker build --platform linux/amd64 \
  --build-arg ROCM_VERSION=10.0 \
  --build-arg GFX_TARGET=gfx1201 \
  --build-arg COMFY_VERSION=v0.43.0 \
  -t ghcr.io/sileader/rocm-images/comfyui:v0.43.0-rocm10.0-gfx1201 \
  ./comfyui
```

To build the configured ROCm `10.1` variant, change `ROCM_VERSION` and the output tags to `10.1` in both the base and ComfyUI commands.

### llama.cpp

Download the binaries before building. Run this preparation step on an Ubuntu/Debian x86-64 environment with Bash, APT, and root access. The script installs its download dependencies using `apt-get`; it is not a native macOS setup command.

```sh
(cd llama.cpp && sudo bash download.sh v0.8.0 10.0)
```

The script resolves the requested GitHub release, follows `nightly-tag.txt` when present, selects the Ubuntu x64 archive matching the requested ROCm version, and verifies downloaded assets against GitHub's SHA-256 digests. Missing matching assets or valid digests cause the download to fail. It extracts the binaries to `llama.cpp/llama.cpp/` when invoked as above and checks that `llama-server` is executable.

Then build the image:

```sh
docker build --platform linux/amd64 \
  --build-arg ROCM_VERSION=10.0 \
  --build-arg GFX_TARGET=gfx1201 \
  --build-arg LLAMA_CPP_VERSION=v0.8.0 \
  -t ghcr.io/sileader/rocm-images/llama.cpp:v0.8.0-rocm10.0-gfx1201 \
  ./llama.cpp
```

`LLAMA_CPP_VERSION` sets the image's version label. The Dockerfile copies the prepared binaries without downloading them, so use the same version and ROCm value for the download and build steps.

## Publishing with GitHub Actions

[Publish images](.github/workflows/publish.yml) runs manually via `workflow_dispatch`. Select **Actions → Publish images → Run workflow** and choose the ref to publish. The workflow must be on the default branch to appear in the Actions interface.

The workflow builds and pushes the base image matrix first. After the base job succeeds, the ComfyUI and llama.cpp jobs can run in parallel. The llama.cpp job downloads and verifies its binaries before building. The workflow has no test job. Publishing runs are serialized with `cancel-in-progress: false`.

Each job authenticates to GHCR using the repository's `GITHUB_TOKEN` with `packages: write`. Existing GHCR packages must grant this repository Actions write access. Image destinations and version matrices are set in the workflow; update the destinations before publishing from a fork. The application Dockerfiles also reference `ghcr.io/sileader/rocm-images/base-ubuntu`, so update those references if you change the base image namespace.

## License

This project is licensed under the [Apache License 2.0](LICENSE). Software included in container images remains subject to its respective licenses.
