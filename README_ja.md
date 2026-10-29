# rocm-images

[English](README.md) | [日本語](README_ja.md)

AMD ROCm 向けのコンテナイメージを配布するリポジトリです。イメージのビルド設定を YAML で管理し、Python 製のツールで Dockerfile の生成、依存関係の解決、イメージのビルドと公開を行います。

## イメージ

以下のイメージ名とタグ形式は、[`manifests/`](manifests/) に定義しています。

| マニフェスト | イメージ | タグ |
| --- | --- | --- |
| [`base.yaml`](manifests/base.yaml) | `ghcr.io/sileader/rocm-images/base-ubuntu` | `26.04-rocm<rocm>-<gfx>` |
| [`comfyui.yaml`](manifests/comfyui.yaml) | `ghcr.io/sileader/rocm-images/comfyui` | `latest`、`<comfy-version>-rocm<rocm>-<gfx>` |
| [`llama.cpp.yaml`](manifests/llama.cpp.yaml) | `ghcr.io/sileader/rocm-images/llama.cpp` | `latest`、`<llama-cpp-version>-rocm<rocm>-<gfx>` |

ベースイメージには Ubuntu 上に ROCm をインストールします。ComfyUI と llama.cpp はこの共通ベースを使用し、それぞれ ComfyUI の `main.py` と `llama-server` をエントリーポイントに設定します。

[`manifests/matrix.yaml`](manifests/matrix.yaml) で、3 つのイメージに共通する ROCm バージョンと GPU ターゲットを定義しています。現在の matrix は ROCm `10.1` と `gfx1201`、既定の platform は `linux/amd64` です。アプリケーションのバージョンは各マニフェストで指定します。これらはビルド対象の設定であり、タグの公開状況を示すものではありません。

公開済みのイメージは、次のように取得できます。

```sh
docker pull ghcr.io/sileader/rocm-images/base-ubuntu:26.04-rocm10.1-gfx1201
```

## リポジトリ構成

```text
manifests/          イメージのビルド設定と共通のビルド matrix
src/rocm_images/   マニフェストの解釈、Dockerfile 生成、依存関係の解決、ビルド用 CLI
tests/             ビルドツールのテスト
test-data/         テスト用データ
```

## 必要な環境とセットアップ

- Python 3.14 以上
- 以下のコマンド例で使用する `uv`
- イメージのビルドには BuildKit 対応の Docker（生成する Dockerfile で heredoc を使用します）
- イメージのプッシュにはレジストリへの認証

リポジトリのルートで実行してください。

```sh
uv sync
uv run rocm-images --help
```

マニフェストの確認と Dockerfile の生成には、Docker デーモンの起動は不要です。

## 依存関係の確認

```sh
uv run rocm-images tree manifests/comfyui.yaml manifests/llama.cpp.yaml
uv run rocm-images tree manifests/comfyui.yaml --format yaml
uv run rocm-images tree manifests/comfyui.yaml --format json -o dependencies.json
```

既定のテキスト出力では、依存ツリーと依存先を先に並べたビルド順序を表示します。共通のビルド対象は重複を除き、matrix と platform の組み合わせごとに別の対象として扱います。埋め込みステージは `inline stage` と表示し、個別にはビルドしません。

YAML / JSON 出力には `roots`、`build_order`、`targets` を含みます。各対象には、元マニフェスト、platform、matrix の値、展開済みのイメージ名とタグ、個別ビルドが必要な依存先、埋め込み元を出力します。

## Dockerfile の生成

```sh
uv run rocm-images generate-dockerfile manifests/comfyui.yaml -o generated/comfyui
```

`--output` / `-o` で出力ディレクトリを指定します。既定値は `dockerfiles` です。matrix の直積と platform の全組み合わせについて Dockerfile を生成し、個別のイメージとして参照するベースもあわせて生成します。ファイル名にはマニフェスト名、platform、matrix の値、識別用ハッシュを含みます。

再生成時には同じファイルを上書きしますが、古い組み合わせのファイルは削除しません。このコマンドは Dockerfile の生成のみを行い、ビルド、タグ付け、プッシュは行いません。

## ビルドと公開

```sh
uv run rocm-images build manifests/comfyui.yaml manifests/llama.cpp.yaml -o generated
uv run rocm-images build manifests/comfyui.yaml --push
```

`build` は依存関係全体を検証し、Dockerfile を生成して、依存先から順に `docker build` を実行します。`image.tags` にあるすべてのタグを付けます。出力先の既定値は `dockerfiles`、ビルドコンテキストの既定値は各対象の元マニフェストがあるディレクトリです。

`--context` で全対象に共通のコンテキストを指定できます。`--docker-command`（別名 `--docker`）では、Docker の実行ファイルやコマンドのプレフィックスを指定できます。

```sh
uv run rocm-images build manifests/comfyui.yaml --context .
uv run rocm-images build manifests/comfyui.yaml --docker-command 'docker --context my-builder'
```

Docker コマンドは引数に分割して実行し、シェル展開は行いません。依存するイメージがベースを再利用できるよう、ビルド結果を同じ Docker デーモンから参照できる環境で実行してください。

プッシュは `--push` を指定した場合のみ実行します。指定時は、依存先を含む各対象のビルド成功直後に、その対象のすべてのタグをプッシュします。ビルドまたはプッシュに失敗すると、残りの処理を停止します。

platform ごとに個別にビルドとプッシュを行い、複数 platform をまとめるイメージマニフェストは作成しません。複数の matrix 値や platform で同じタグを使うと、後のビルドとプッシュでそのタグが更新されます。特定の ROCm バージョンや GPU ターゲットを選ぶ場合は、それらを含むタグを使用してください。

## マニフェストの形式

イメージのマニフェストは `schema-version: 1` を使用し、次のフィールドに対応します。

| フィールド | 用途 |
| --- | --- |
| `vars` | `${{ vars.NAME }}` で参照する文字列変数 |
| `matrix` | 文字列の候補を持つ軸。すべての組み合わせを生成 |
| `matrix-from-file` | インラインの `matrix` の代わりに使用する共通 matrix ファイル |
| `platforms` | 対象 platform。既定値は `[linux/amd64]` |
| `base-image` | 外部イメージまたは別のマニフェストへの参照 |
| `image` | 必須のイメージ名 `name` と、空でないタグのリスト `tags` |
| `steps` | 順番に実行する Dockerfile の操作 |

matrix の値は `${{ matrix.AXIS }}` で参照します。シェルの `${NAME}` などは保持します。共通 matrix ファイルには `schema-version: 1` と `matrix` を記述します。

`${{ readYaml('matrix.yaml').matrix.gfx }}` は、記述したマニフェストからの相対パスで YAML を読み込み、ドット区切りのキーで入れ子の値を参照します。式単独では値の型を保持するため、リストを matrix の軸として利用できます。文字列への埋め込みは文字列の値のみ可能です。これらの参照はマニフェストの検証前に解決します。

`matrix-from-file` と `base-image.source` のパスは、それぞれを記述したマニフェストのディレクトリを基準に解決します。アプリケーションのマニフェストでは、次のように共通ベースを参照しています。

```yaml
base-image:
  source: ./base.yaml
  with-matrix: ${{ matrix }}
  use-from: true
```

`use-from: true` の場合、ベースを別の Dockerfile として生成し、その展開済みイメージ名と先頭のタグを子側の `FROM` に使います。省略時または `false` の場合は、参照先を同じ Dockerfile の前段ステージとして埋め込みます。`with-matrix` には現在の matrix 全体、または個別のマッピングを渡せます。省略した依存先の軸は、候補が 1 つの場合のみ補完します。依存先も対象 platform に対応している必要があります。

外部ベースには `base-image.name`、任意の `tag`、任意の platform ごとの SHA-256 `digest` マッピングを指定します。`digest` を指定した場合は、対象となるすべての platform の値が必要です。

各 step には `run`、`workdir`、`entrypoint` のいずれか 1 つと、任意の `name` を指定します。それぞれ `RUN`、`WORKDIR`、exec 形式の `ENTRYPOINT` を生成します。各 `run` は既定のシェルを使う独立した命令です。複数行のスクリプトは BuildKit の heredoc で保持します。

未知のキー、未定義の式、重複した YAML キー、循環する参照はエラーになります。

## 開発

### CI

- [Tests](.github/workflows/test.yml) は各 PR で実行します。Python 3.14 でロック済みの依存関係をインストールし、テストと全イメージのマニフェストからの Dockerfile 生成を検証します。コンテナイメージのビルドやプッシュは行いません。
- [Publish images](.github/workflows/publish.yml) は `workflow_dispatch` による手動実行専用です。GitHub Actions で **Publish images** → **Run workflow** を選び、公開する ref を指定してください。テスト成功後、ベース・ComfyUI・llama.cpp を依存順にビルドし、マニフェストに定義されたすべてのタグを GHCR にプッシュします。公開処理は同じタグを同時更新しないよう直列化しています。

公開時の認証には、`packages: write` 権限を付与したリポジトリの `GITHUB_TOKEN` を使用し、別途レジストリ用シークレットを設定する必要はありません。既存の GHCR パッケージには、このリポジトリの Actions からの書き込みを許可してください。公開先はマニフェストのイメージ名（現在は `ghcr.io/sileader/rocm-images/*`）で決まるため、フォークから公開する場合は事前に変更してください。手動ワークフローを GitHub Actions に表示するには、デフォルトブランチに配置する必要があります。

ビルドツールのテストを実行するには、次のコマンドを使用します。

```sh
uv run python -m unittest discover -s tests -v
```

## ライセンス

このプロジェクトは [Apache License 2.0](LICENSE) のもとで公開しています。コンテナイメージに含まれるソフトウェアには、それぞれのライセンスが適用されます。
