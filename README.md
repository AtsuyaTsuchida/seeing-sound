# Spectral Descriptor Space

任意の音（鳥のさえずり・音楽など）を **3D の「音の地図」** に変換します。録音を短い区間に分割し、各区間を音響的な性質で空間に配置して発光するノードにし、ネットワークで結び、再生に同期して光らせます。

Lucio Arese の *Seeing Birdsong* に着想を得た**独立した再実装**です。中身は**解釈可能な記述子空間**（軸が名前のついたスペクトル記述子＝ブラックボックス埋め込みではない）で構成しています。

![demo](docs/demo.png)

---

## 何をするか

```
音 ─▶ 区間分割 ─▶ スペクトル記述子 ─▶ 3D配置 ─▶ 色/サイズ/発光 ─▶ 描画
      (onset)      (centroid, spread,   (選んだ3つの    (centroid→色相,
                    crest, flux …)       記述子=X/Y/Z)   振幅→サイズ,
                                                         再生→発光)
```

- **分割**：録音を音節/音符単位に分割（オンセット検出）。
- **計測**：区間ごとに約16種のスペクトル記述子を算出（spectral centroid, spread, crest, flatness, contrast, slope, flux, rolloff, dominant freq, F0, centroid–F0 gap, tonality, HNR, amplitude …）。
- **配置**：選んだ3つの記述子をX/Y/Z軸にして3D配置（既定：spread × centroid × crest）。軸が実在の記述子なので「なぜそこにあるか」を説明できます。自動で構造を見つけたい場合の UMAP 版も同梱。
- **対応づけ**：残りのチャンネルを見た目に割当て＝色=spectral centroid、サイズ=振幅、エッジ=近傍、そして**再生ヘッドに追従する発光**（区間が鳴る瞬間にそのノードが閃光＝アタックバースト付き）。

**どんな音にも使えます** — 同梱サンプルは合成テスト音ですが、独奏/室内楽のクラシック録音でも試しています。

---

## フロントエンド

結果は2通りで見られます：

1. **Web（Python以外のインストール不要）** — インタラクティブHTML：
   - `viewer.html` — three.jsシーン（発光ノード＋エッジ、ノードをクリックでその区間を再生、再生同期）。
   - `birdsong.html` — Plotly 3D散布（UMAP多様体）。
   - `descriptor_space.html` — 各軸/色に割り当てる**記述子をドロップダウンで選べる** Plotly 3D散布（"Timbre Space"ビュー）。
2. **TouchDesigner** — `td/NHK2026_3Dtest.toe`。開くだけで使えるプロジェクト（インスタンス球＋ブルーム＋環境光、追従カメラ＋周回する俯瞰カメラ、音声再生、画面上の**コントロールパネル**つき＝下記GUI）。TouchDesigner 2025.30060 で作成。

---

## クイックスタート

### 1. インストール（Python 3.11 推奨）

```bash
python3.11 -m venv venv
./venv/bin/pip install -r requirements.txt
```

### 2. データ生成

```bash
# 区間分割 + 特徴量 + UMAP + クラスタ  ->  out/td_points.csv, scene.json, viewer.html ...
./venv/bin/python pipeline.py --audio audio --out out

# ノード位置を「解釈可能な記述子軸」に置き換え + 色/サイズ/ラベル付与
cp out/td_points.csv out/td_points_umap_backup.csv
./venv/bin/python td_descriptor_coords.py \
    --points out/td_points_umap_backup.csv --audio audio \
    --axes spread,centroid,crest --color centroid --out out

# (任意) 軸を切り替えられる記述子ダッシュボード
./venv/bin/python descriptor_space.py --audio audio --out out
```

自分の音源は `audio/` に入れるだけ（wav/flac/mp3/m4a …）。

### 3a. ブラウザで見る

```bash
cd out && python3 -m http.server 8731
# http://localhost:8731/viewer.html を開く（または birdsong.html / descriptor_space.html）
```
（`fetch`と音声のため **HTTP配信が必須**。`file://` はブラウザに弾かれます。）

### 3b. TouchDesignerで見る

`td/NHK2026_3Dtest.toe` を開く。`out/td_points.csv` / `td_edges.csv` と音源を読みます。Python側を再実行して新しいデータを読み込むには、textportで `mod('/seeing_birdsong/td_refresh').refresh()`（テーブル再読込→再センタリング→俯瞰カメラ再フレーミング→再クック）。

---

## GUI（TouchDesigner）

`seeing_birdsong` コンポーネントを選択 → パラメータの **Controls** ページ（コンポーネント内の画面上 `gui` パネルでも操作可）：

| コントロール | 効果 |
|---|---|
| Node Size | 球の基準サイズ |
| Line Thickness | エッジ（リボン）の太さ |
| Density | 全体の密度＝雲のスケール（高いほど密集）|
| Glow | ブルームの強さ |
| Edge Opacity | エッジの不透明度 |
| BG Brightness | 背景グレーの明るさ |
| Orbit Speed | 俯瞰カメラの周回速度 |

---

## 動画書き出し（32:9・音声付き）

「追従カメラ｜俯瞰カメラ」を横並びにした 3840×1080・音声同期の動画を作る決定論的フローを同梱：各フレームを明示的な時間 `T` で連番PNGに描き出し、`ffmpeg` で元音源と多重化します。

```bash
ffmpeg -framerate 30 -i out/frames/f%04d.png -i audio/your.wav \
    -c:v libx264 -pix_fmt yuv420p -crf 18 -c:a aac -shortest out/seeing_birdsong_32x9.mp4
```

（フレーム書き出しの詳細は `docs/DEV_NOTES_ja.md`。TouchDesignerの実時間録画は実時間より速くクックしてA/Vがずれるため、連番PNG＋ffmpeg方式を採用しています。）

---

## ファイル構成

```
pipeline.py             区間分割→特徴→UMAP→クラスタ。TD/Web用データを出力
td_descriptor_coords.py 記述子軸→3D座標（＋色/振幅/ラベル）
descriptor_space.py     フレーム単位の記述子ダッシュボード（軸切替3D散布）
viewer.html             three.jsビューア（発光＋クリック再生＋再生同期）
td/NHK2026_3Dtest.toe   TouchDesignerプロジェクト
audio/                  サンプル入力（合成テスト音）
docs/DEV_NOTES_ja.md    詳細な制作ノート（日本語）
```

---

## クレジット & ライセンス

- コンセプトの着想：**Lucio Arese — *Seeing Birdsong***（独立した再実装。無関係・非公式）。
  - 参照動画：[Seeing Birdsong — Project Overview (YouTube)](https://www.youtube.com/watch?v=a8t9X90s2S0)
- 同梱サンプル音源（`audio/synthetic_*.wav`）は手続き生成。
- クラシックのデモには米国パブリックドメインの1921年録音（Fritz Kreisler / Carl Lamson「To Spring」、Internet Archive Great 78 Project）を使用。**本リポジトリには含めていません** — 各自の音源をご用意ください。
- コード：MIT（`LICENSE` 参照）。
