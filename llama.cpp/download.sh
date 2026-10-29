#!/usr/bin/env bash

apt-get update
apt-get install -y --no-install-recommends ca-certificates curl jq coreutils tar gzip
rm -rf /var/lib/apt/lists/*

download_dir=$(mktemp -d)
trap 'rm -rf "$download_dir"' EXIT

# The archive must match GitHub's SHA-256 digest.
download_asset() {
  asset_url=$(printf '%s' "$1" | jq -er '.browser_download_url | select(type == "string" and length > 0)')
  asset_digest=$(printf '%s' "$1" | jq -er '.digest | select(type == "string") | select(test("^sha256:[0-9a-fA-F]{64}$"))')
  curl --fail --show-error --location --retry 3 "$asset_url" -o "$2"
  printf '%s  %s\n' "${asset_digest#sha256:}" "$2" | sha256sum --check --strict -
}

releases_url=https://api.github.com/repos/ggml-org/llama.cpp/releases
fetch_release() {
  encoded_tag=$(printf '%s' "$1" | jq -sRr '@uri')
  curl --fail --show-error --location --retry 3 \
    -H "Accept: application/vnd.github+json" \
    -H "X-GitHub-Api-Version: 2026-03-10" "$releases_url/tags/$encoded_tag"
}

release_tag='${{ vars.llama-cpp-version }}'
release=$(fetch_release "$release_tag")

# Versioned releases point to their binary release via nightly-tag.txt.
nightly_asset=$(printf '%s' "$release" | jq -c '[.assets[] | select(.name == "nightly-tag.txt")] | .[0] // empty')
if [ -n "$nightly_asset" ]; then
  download_asset "$nightly_asset" "$download_dir/nightly-tag.txt"
  release_tag=$(jq -Rers 'select(test("^b[0-9]+\n?$")) | rtrimstr("\n")' "$download_dir/nightly-tag.txt")
  release=$(fetch_release "$release_tag")
fi

# Select the archive matching the requested ROCm version.
rocm_asset=$(printf '%s' "$release" | jq -ec --arg tag "$release_tag" --arg rocm '${{ matrix.rocm }}' '
  [.assets[]
    | select(.name | startswith("llama-" + $tag + "-bin-ubuntu-rocm-"))
    | select(.name | test("-rocm-[0-9]+(\\.[0-9]+)*-x64\\.tar\\.gz$"))
    | select((.name | capture("-rocm-(?<version>[0-9.]+)-x64").version) == $rocm)]
  | if length > 0 then .[0] else error("No Ubuntu x64 ROCm archive found for requested version") end')
download_asset "$rocm_asset" "$download_dir/llama.tar.gz"

# Release archives contain a top-level directory.
mkdir -p /opt/llama.cpp
tar -xzf "$download_dir/llama.tar.gz" -C ./llama.cpp --strip-components=1
test -x ./llama.cpp/llama-server
 
