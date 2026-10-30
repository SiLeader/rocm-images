# rocm-images

[English](README.md) | [日本語](README_ja.md)

Ubuntu 26.04 上で AMD ROCm を利用するためのコンテナイメージです。共通の ROCm ベース、ComfyUI、llama.cpp の Dockerfile と、GHCR に公開するための GitHub Actions ワークフローを管理しています。

## イメージ

以下のビルド対象とタグは、[Publish images](.github/workflows/publish.yml) に設定しています。これらはビルド設定であり、タグの公開状況を示すものではありません。すべてのイメージは x86-64（`linux/amd64`）向けです。

| イメージ | バージョン | ROCm | GPU ターゲット | タグ形式 |
| --- | --- | --- | --- | --- |
| `ghcr.io/sileader/rocm-images/base-ubuntu` | Ubuntu `26.04` | `10.0`、`10.1` | `target.yaml` | `26.04-rocm<rocm>-<gfx>` |
| `ghcr.io/sileader/rocm-images/comfyui` | `v0.43.0` | `10.0`、`10.1` | `target.yaml` | `<comfy-version>-rocm<rocm>-<gfx>` |
| `ghcr.io/sileader/rocm-images/llama.cpp` | `v0.8.0` | `10.0` | `target.yaml` | `<llama-cpp-version>-rocm<rocm>-<gfx>` |

すべてのイメージのビルド対象 GPU は [target.yaml](target.yaml) の `gfx1201`、`gfx1102`、`gfx1101`、`gfx1100`、`gfx1151`、`gfx1150`、`gfx950`、`gfx942`、`gfx90a` です。以下のコマンドでは `gfx1201` を例にしています。他の設定済みターゲット向けにビルドする場合は、`GFX_TARGET` と関連するすべてのイメージタグの GPU 接尾辞を変更してください。

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

### 実行方法

#### ComfyUI

以下が実行例です。

```sh
docker run --rm \
  --device /dev/kfd \
  --device /dev/dri \
  --volume /path/to/models:/opt/comfyui/ComfyUI/models \
  --volume /path/to/user:/opt/comfyui/ComfyUI/user \
  --volume /path/to/output:/opt/comfyui/ComfyUI/output \
  -p 8188:8188 \
  ghcr.io/sileader/rocm-images/comfyui:v0.43.0-rocm10.0-gfx1201
```

#### llama.cpp

以下が実行例です。

```sh
docker run --rm \
  --device /dev/kfd \
  --device /dev/dri \
  --volume /path/to/model:/container/model \
  -p 8080:8080 \
  ghcr.io/sileader/rocm-images/llama.cpp:v0.8.0-rocm10.0-gfx1201 \
  -m /container/model/model.gguf \
  --port 8080 \
  --host 0.0.0.0
```

コンテナ内からGPUが見えているかは以下で確認できます。

```sh
docker run --rm \
  --device /dev/kfd \
  --device /dev/dri \
  ghcr.io/sileader/rocm-images/llama.cpp:v0.8.0-rocm10.0-gfx1201 \
  --list-devices
```

例えば以下のように表示されます。

```
Available devices:
  ROCm0: AMD Radeon AI PRO R9700 (32624 MiB, 32558 MiB free)
```

#### amd-smiやbash
AMD ROCmのインストール時に`amd-smi`コマンドがインストールされます。
以下のコマンドでそれを実行できます。llama.cppもcomfyuiも同じように起動します。

```sh
docker run --rm \
  --device /dev/kfd \
  --device /dev/dri \
  --entrypoint /usr/bin/amd-smi \
  ghcr.io/sileader/rocm-images/llama.cpp:v0.8.0-rocm10.0-gfx1201
```

またベースイメージがubuntuであるため、bashもインストールされています。
以下のコマンドで対話モードのbashを実行できます。

```sh
docker run --rm -it \
  --device /dev/kfd \
  --device /dev/dri \
  --entrypoint /bin/bash \
  ghcr.io/sileader/rocm-images/llama.cpp:v0.8.0-rocm10.0-gfx1201
```


## リポジトリ構成

```text
target.yaml                  全イメージのビルド対象 GPU
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

ComfyUI では、ベースの ROCm バージョン、PyTorch パッケージの ROCm 接尾辞、torchvision のバージョンを個別に指定します。ワークフローで使用している組み合わせは次のとおりです。

| `ROCM_VERSION` | `PYTORCH_ROCM_VERSION` | `TORCHVISION_VERSION` |
| --- | --- | --- |
| `10.0` | `10.0.0` | `0.29.0` |
| `10.1` | `10.1.0` | `0.29.0a0` |

Dockerfile は torch を `2.14.0`、torchaudio を `2.11.0.3` に固定し、それぞれに `+rocm<PYTORCH_ROCM_VERSION>` の接尾辞を付けます。torch と torchvision には `device-<GFX_TARGET>` の extra も指定します。

```sh
docker build --platform linux/amd64 \
  --build-arg ROCM_VERSION=10.0 \
  --build-arg GFX_TARGET=gfx1201 \
  --build-arg PYTORCH_ROCM_VERSION=10.0.0 \
  --build-arg TORCHVISION_VERSION=0.29.0 \
  --build-arg COMFY_VERSION=v0.43.0 \
  -t ghcr.io/sileader/rocm-images/comfyui:v0.43.0-rocm10.0-gfx1201 \
  ./comfyui
```

設定済みの ROCm `10.1` 向けをビルドする場合は、ベースと ComfyUI の両方のコマンドで `ROCM_VERSION` と出力タグを `10.1` に変更してください。ComfyUI のコマンドでは、さらに `PYTORCH_ROCM_VERSION=10.1.0` と `TORCHVISION_VERSION=0.29.0a0` を指定します。

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

最初に `target.yaml` から GPU ターゲットを読み込み、その後ベースイメージの全組み合わせをビルドしてプッシュします。ベースのジョブが成功した後、ComfyUI と llama.cpp のジョブは並列に実行できます。llama.cpp のジョブではビルド前にバイナリをダウンロードして検証します。このワークフローにテストジョブはありません。公開ワークフローの実行は `cancel-in-progress: false` で直列化しています。

各公開ジョブは `packages: write` 権限を付与したリポジトリの `GITHUB_TOKEN` で GHCR に認証します。既存の GHCR パッケージには、このリポジトリの Actions からの書き込みを許可してください。GPU ターゲットは `target.yaml`、公開先とバージョンの組み合わせはワークフローで指定しているため、フォークから公開する場合は公開先を変更してください。アプリケーションの Dockerfile も `ghcr.io/sileader/rocm-images/base-ubuntu` を参照しているため、ベースイメージの名前空間を変更する場合は参照先も更新してください。

## ライセンス

このプロジェクトは [Apache License 2.0](LICENSE) のもとで公開しています。コンテナイメージに含まれるソフトウェアには、それぞれのライセンスが適用されます。
