# daily-proof

1日1つ、命題とその証明を書いて続けるための個人サイト。毎日のコミットが、そのまま継続の記録(GitHub の草)になる。

## 仕組み

- `proofs/YYYY-MM-DD.md` に1日分を書く(1ファイル1証明)。
- `make build` が `docs/` に静的サイトを生成する。GitHub Pages は `docs/` を配信する設定にする。
- 各日は `docs/YYYY-MM-DD.html` になり、スクロールに応じて命題→証明が少しずつ現れる(blur/fade のリビールアニメーション)。
- ルート `docs/index.html` は、存在する日からランダムに1つ選んでその日ページへ飛ばすだけの中継ページ。専用ホームは持たない。
- カレンダーは全日ページ共通で下部に表示。証明した日はハイライトされ、他の日へリンクし、左右の矢印で前後の月へ移動できる。
- 数式はクライアント側で [MathJax](https://www.mathjax.org/) が描画する(`$...$`、`$$...$$`)。

## 使い方

```sh
make new     # 今日の proofs/YYYY-MM-DD.md を雛形から作成
make build   # docs/ を生成
make serve   # ビルドして http://localhost:8000 でプレビュー
```

direnv を使っていれば、ディレクトリに入ると `flake.nix` の開発環境(python3, make)が自動で有効になる。

## 1日分の書き方

日付はファイル名から取るので、本文は見出し2つだけでよい。

```markdown
# 命題

ここに主張を書く。

# 証明

ここに証明を書く。
```

## GitHub Pages の設定

リポジトリの Settings → Pages で、Source を `main` ブランチの `/docs` フォルダに設定する。
