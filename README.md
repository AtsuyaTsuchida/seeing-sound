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

## 必要環境

- **Python 3.11 推奨**（`umap-learn` / `numba` のホイールの都合。3.14等の最新版では入らないことがあります）
- **ffmpeg**（mp3/m4a等のデコード、および動画書き出しに使用。`brew install ffmpeg` など）
- TouchDesigner で見る場合：**TouchDesigner 2025.30060 以降**

---

## 実行方法

### 1. セットアップ

```bash
git clone https://github.com/AtsuyaTsuchida/spectral-descriptor-space.git
cd spectral-descriptor-space

python3.11 -m venv venv
./venv/bin/pip install -r requirements.txt
```

### 2. 音源を置く

`audio/` フォルダに音声ファイルを入れます（`wav` / `flac` / `mp3` / `m4a` / `aiff` / `ogg`、サブフォルダ可）。
同梱の合成サンプル（`audio/synthetic_0.wav`, `synthetic_1.wav`）でそのまま試せます。
**長い曲は重い**ので、まずは冒頭 30〜60 秒に切ったファイルから始めるのがおすすめです（例 `ffmpeg -ss 0 -t 45 -i in.mp3 -ac 1 -ar 48000 audio/clip.wav`）。

### 3. データ生成（2 ステップ）

**3-1. 区間分割＋特徴抽出（`pipeline.py`）**

```bash
./venv/bin/python pipeline.py --audio audio --out out
```
`out/` に次が生成されます：
- `td_points.csv` / `td_edges.csv` / `td_files.csv` … TouchDesigner 取込用（座標・色・近傍）
- `scene.json` / `viewer.html` … three.js ビューア用
- `birdsong.html` … Plotly（UMAP 多様体）
- `embedding.csv` / `coords3d.npy` … 解析データ
- `out/audio/` … 再生・書き出し用にコピーされた音源

オプション：
- `--seg onset`（既定）= 音の立ち上がりで分割／`--seg fixed` = 3秒固定窓（管弦楽など密な音はこちらが見やすい）

**3-2. 記述子を 3D 座標に（`td_descriptor_coords.py`）**

`pipeline.py` の UMAP 座標を、**解釈可能な記述子軸**に置き換え、色・サイズ・周波数ラベル列を付与します。

```bash
cp out/td_points.csv out/td_points_umap_backup.csv
./venv/bin/python td_descriptor_coords.py \
    --points out/td_points_umap_backup.csv --audio audio \
    --axes spread,centroid,crest --color centroid --out out
```
- `--axes X,Y,Z` … 3軸に使う記述子（既定 `spread,centroid,crest`）。例：`centroid,amp_db,flux`
- `--color 記述子` … 色に使う記述子（既定なら元のクラスタ色を維持。例 `centroid`）
- **UMAP 配置に戻したい**ときは、TouchDesigner に `out/td_points_umap_backup.csv` を読ませます。

使える記述子名：`centroid, spread, crest, flatness, contrast, slope, flux, rolloff85, rolloff95, domfreq, f0, centroid_f0_gap, tonality, hnr, amp_db, time`

**（任意）軸を切り替えられるダッシュボード（`descriptor_space.py`）**

```bash
./venv/bin/python descriptor_space.py --audio audio --out out
# -> out/descriptor_space.html（X/Y/Z/色に割り当てる記述子をドロップダウンで変更可）
```

### 4. 見る

#### 4a. ブラウザ

```bash
cd out && python3 -m http.server 8731
```
ブラウザで開く：
- `http://localhost:8731/viewer.html` … three.js（**ドラッグ=回転 / ホイール=ズーム / ノードをクリック=その区間を再生 / ▶ or Space=タイムライン同期再生**）
- `http://localhost:8731/birdsong.html` … UMAP 多様体（Plotly）
- `http://localhost:8731/descriptor_space.html` … 記述子ダッシュボード（軸ドロップダウン）

> ⚠️ `fetch` と Web Audio のため **HTTP 配信が必須**です。`file://` で直接開くとブラウザに弾かれます。

#### 4b. TouchDesigner

1. `td/NHK2026_3Dtest.toe` を開く。
2. `seeing_birdsong` コンポーネント内が本体。`out/td_points.csv` / `td_edges.csv` と音源を読みます。
   - パスが違う場合は、`audio`（Audio File In）の **File** を自分の音源に、`clock`（Timer）の **Length** を曲の長さ（秒）に設定。
3. **データを更新したとき**（Python を再実行した後など）は、textport で：
   ```python
   mod('/seeing_birdsong/td_refresh').refresh()
   ```
   → テーブル再読込 → 再センタリング → 俯瞰カメラ再フレーミング → 再クック を一括実行。
   別フォルダを読むなら `refresh(base='/path/to/out')`。
4. 出力 TOP：`out`（追従カメラ）と `out_wide`（周回する俯瞰カメラ）。Perform/Window で表示対象を選択。

### 5. 動画書き出し（32:9・音声付き／任意）

「追従カメラ｜俯瞰カメラ」を横並びにした 3840×1080・音声同期の動画を作れます。手順は **TouchDesigner 側でフレームを連番 PNG に書き出し**（時間 `T` を 1 フレームずつ進める決定論的レンダリング。詳細は `docs/DEV_NOTES_ja.md`）→ **ffmpeg で元音源と多重化**：

```bash
ffmpeg -framerate 30 -i out/frames/f%04d.png -i audio/your.wav \
    -c:v libx264 -pix_fmt yuv420p -crf 18 -c:a aac -shortest out/output_32x9.mp4
```
> TouchDesigner の実時間録画は実時間より速くクックして音と映像がずれるため、この「連番 PNG ＋ ffmpeg」方式を採用しています。

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

## トラブルシュート

- **`file://` で何も出ない / 音が鳴らない** → `python3 -m http.server` で HTTP 配信してから開く。
- **`umap-learn` / `numba` が入らない** → Python 3.11 を使う（最新版は未対応のことあり）。
- **mp3/m4a が読めない** → `ffmpeg` をインストール。
- **長い曲が重い / 密すぎる** → 冒頭を短く切る、`--seg fixed` を試す、GUI の **Density** で見やすさ調整。
- **TouchDesigner で配置が更新されない** → `mod('/seeing_birdsong/td_refresh').refresh()` を実行。

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
