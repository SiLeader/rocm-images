# rocm-images

[English](README.md) | [日本語](README_ja.md)

Ubuntu 26.04 上で AMD ROCm を利用するためのコンテナイメージです。共通の ROCm ベース、ComfyUI、llama.cpp の Dockerfile と、GHCR に公開するための GitHub Actions ワークフローを管理しています。

## イメージ

以下のビルド対象とタグは、[Publish images](.github/workflows/publish.yml) に設定しています。これらはビルド設定であり、タグの公開状況を示すものではありません。すべてのイメージは x86-64（`linux/amd64`）向けです。

| イメージ | バージョン | ROCm | GPU ターゲット | タグ形式 |
| --- | --- | --- | --- | --- |
| `ghcr.io/sileader/rocm-images/base-ubuntu` | Ubuntu `26.04` | `10.0`、`10.1` | `gfx1201` | `26.04-rocm<rocm>-<gfx>` |
| `ghcr.io/sileader/rocm-images/comfyui` | `v0.43.0` | `10.0`、`10.1` | `gfx1201` | `<comfy-version>-rocm<rocm>-<gfx>` |
| `ghcr.io/sileader/rocm-images/llama.cpp` | `v0.8.0` | `10.0` | `gfx1201` | `<llama-cpp-version>-rocm<rocm>-<gfx>` |

ワークフローはバージョン付きのタグのみを公開し、`latest` は公開しません。

公開済みのイメージは、次のように取得できます。

```sh
docker pull ghcr.io/sileader/rocm-images/base-ubuntu:26.04-rocm10.0-gfx1201
docker pull ghcr.io/sileader/rocm-images/comfyui:v0.43.0-rocm10.0-gfx1201
docker pull ghcr.io/sileader/rocm-images/llama.cpp:v0.8.0-rocm10.0-gfx1201
```

- **ベース:** AMD の stable APT リポジトリから `amdrocm<rocm>-<gfx>` をインストールし、`LD_LIBRARY_PATH=/opt/rocm/lib` を設定します。
- **ComfyUI:** 共通ベースを使用し、指定したバージョンの ComfyUI を取得して、Python 仮想環境に ROCm 向け PyTorch パッケージと ComfyUI の依存パッケージをインストールします。エントリーポイントは `/opt/comfyui/venv/bin/python main.py`、既定の引数は `--listen 0.0.0.0` です。
- **llama.cpp:** 共通ベースを使用し、ビルドコンテキストからビルド済みバイナリをコピーします。エントリーポイントは `/opt/llama.cpp/llama-server` です。サーバーの引数はコンテナ実行時に指定してください。

## リポジトリ構成

```text
base/
  Dockerfile                 Ubuntu 26.04 と ROCm
  amdrocm-stable.sources     AMD stable APT リポジトリ設定
comfyui/
  Dockerfile                 ComfyUI と ROCm 向け PyTorch パッケージ
llama.cpp/
  Dockerfile                 ビルド済み llama.cpp バイナリを使うイメージ
  download.sh                指定したリリースのダウンロードと検証
.github/workflows/
  publish.yml                手動実行のビルド・公開ワークフロー
```

## ローカルビルド

Docker と、取得元のパッケージ・ソースリポジトリへのアクセスが必要です。以下のコマンドはリポジトリのルートで実行してください。ビルド引数には既定値がないため、記載した引数をそれぞれ指定します。

最初に共通ベースをビルドします。アプリケーションの Dockerfile は、バージョン付きタグでこのベースを参照します。

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

設定済みの ROCm `10.1` 向けをビルドする場合は、ベースと ComfyUI の両方のコマンドで `ROCM_VERSION` と出力タグを `10.1` に変更してください。

### llama.cpp

ビルド前にバイナリをダウンロードします。この準備手順は、Bash、APT、root 権限を利用できる Ubuntu/Debian の x86-64 環境で実行してください。スクリプトは `apt-get` でダウンロードに必要なパッケージをインストールするため、macOS 上で直接実行するためのコマンドではありません。

```sh
(cd llama.cpp && sudo bash download.sh v0.8.0 10.0)
```

スクリプトは指定された GitHub リリースを取得し、`nightly-tag.txt` があれば参照先のリリースをたどります。その後、指定した ROCm バージョンに一致する Ubuntu x64 アーカイブを選び、ダウンロードしたファイルを GitHub の SHA-256 ダイジェストで検証します。一致するアーカイブや有効なダイジェストがない場合は失敗します。上記の実行方法では `llama.cpp/llama.cpp/` にバイナリを展開し、`llama-server` が実行可能であることを確認します。

続いてイメージをビルドします。

```sh
docker build --platform linux/amd64 \
  --build-arg ROCM_VERSION=10.0 \
  --build-arg GFX_TARGET=gfx1201 \
  --build-arg LLAMA_CPP_VERSION=v0.8.0 \
  -t ghcr.io/sileader/rocm-images/llama.cpp:v0.8.0-rocm10.0-gfx1201 \
  ./llama.cpp
```

`LLAMA_CPP_VERSION` はイメージのバージョンラベルを設定します。Dockerfile は準備済みのバイナリをコピーするだけでダウンロードは行わないため、ダウンロード時とビルド時でバージョンと ROCm の値をそろえてください。

## GitHub Actions での公開

[Publish images](.github/workflows/publish.yml) は `workflow_dispatch` による手動実行です。**Actions → Publish images → Run workflow** を選び、公開する ref を指定してください。Actions の画面に表示するには、ワークフローをデフォルトブランチに配置する必要があります。

最初にベースイメージの全組み合わせをビルドしてプッシュします。ベースのジョブが成功した後、ComfyUI と llama.cpp のジョブは並列に実行できます。llama.cpp のジョブではビルド前にバイナリをダウンロードして検証します。このワークフローにテストジョブはありません。公開ワークフローの実行は `cancel-in-progress: false` で直列化しています。

各ジョブは `packages: write` 権限を付与したリポジトリの `GITHUB_TOKEN` で GHCR に認証します。既存の GHCR パッケージには、このリポジトリの Actions からの書き込みを許可してください。公開先とバージョンの組み合わせはワークフローで指定しているため、フォークから公開する場合は公開先を変更してください。アプリケーションの Dockerfile も `ghcr.io/sileader/rocm-images/base-ubuntu` を参照しているため、ベースイメージの名前空間を変更する場合は参照先も更新してください。

## ライセンス

このプロジェクトは [Apache License 2.0](LICENSE) のもとで公開しています。コンテナイメージに含まれるソフトウェアには、それぞれのライセンスが適用されます。
