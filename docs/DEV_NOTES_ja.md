# Seeing Birdsong — corpus explorer

鳥のさえずり録音群を「音節セグメント → 埋め込み → 3D多様体」に変換し、
ブラウザで回転・ホバーできるインタラクティブ3D (`out/birdsong.html`) を書き出す。
（YouTube "Seeing Birdsong" のコーパス探索型を、TouchDesigner無し・Python完結で再現）

## flow
```
audio files → segment(onset|fixed) → embed(librosa|birdnet)
            → UMAP(3D) → HDBSCAN(色分け) → Plotly html
```

## 使い方
1. 録音を `audio/` に入れる（wav/flac/mp3/m4a/aiff/ogg、サブフォルダ可）
2. 実行：
   ```bash
   ./venv/bin/python pipeline.py --audio audio --out out
   open out/birdsong.html
   ```

### オプション
| flag | 既定 | 説明 |
|---|---|---|
| `--seg onset` | onset | 音節単位で切る（さえずり向き）。`fixed`=3秒窓(BirdNET風) |
| `--method librosa` | librosa | 常に動く音響特徴(MFCC等62次元)。`birdnet`=実験的(下記) |
| `--no-edges` | off | 近傍グラフの線（あの"ネットワーク状"ルック）を消す |

### 出力 (`out/`)
- `viewer.html` — **three.jsビューア（発光・ブルーム＋クリックで音節再生）** ← オリジナル寄り
- `birdsong.html` — Plotly版（手軽。ホバーで file / 時刻 / Hz / cluster）
- `scene.json` — three.jsビューアが読む点群＋エッジ＋メタ
- `audio/` — クリック再生用にコピーされた録音
- `embedding.csv` / `coords3d.npy` — 各セグメント座標・特徴（他ツール移植用）

## three.jsビューアの起動（発光・ブルーム＋クリック再生）
`fetch`とWeb Audioのため **`file://`では動かない**。HTTPで配信する：
```bash
cd out
python3 -m http.server 8731
# → ブラウザで http://localhost:8731/viewer.html
```
- **▶ play / Space = タイムライン再生**：選択ファイルを頭から流し、時刻に同期して
  該当音節ノードが順に発光（再生ヘッドが多様体上を移動）。右上のセレクタでファイル選択
- ノードを**クリック=その1音節だけ**再生
- ドラッグ=回転 / スクロール=ズーム
- ホバーで file・時刻・重心Hz・f0Hz・クラスタ。色=HDBSCANクラスタ
- 見た目調整は viewer.html 内の `SCALE`、`UnrealBloomPass(strength,radius,threshold)`、
  `PointsMaterial.size`、エッジの `opacity` で

## BirdNET（任意・実験的）
鳥特化のセマンティック埋め込みを使いたい場合：
```bash
./venv/bin/python -m pip install birdnetlib tensorflow
./venv/bin/python pipeline.py --method birdnet --seg fixed
```
※ `_load_birdnet()` は birdnetlib の内部interpreterを叩くため版差で動かない場合あり。
   その時は `--method librosa` に戻せば確実。

## 記述子空間ビュー（元デモ "TIMBRE SPACE" 流）
UMAPではなく**名前付きスペクトル記述子そのもの**を軸にした、軸切替可能な3D散布。各点＝1フレーム。
元 "Seeing Birdsong" の「configurable 2D/3D graphs of spectral descriptors」を再現。
```bash
./venv/bin/python descriptor_space.py --audio audio --out out
open out/descriptor_space.html
```
- 上部ドロップダウンで **X / Y / Z / 色** に割り当てる記述子を選択（16種）
- 既定＝元デモの TIMBRE SPACE（Spread×Centroid×Crest, 色=Centroid–F0 Gap）
- Z に Time を選べば「歌の時間軌跡」(元 TONALITY パネル風) になる
- 記述子: centroid, spread, crest, flatness, contrast, slope, flux, rolloff85/95,
  dominant freq, f0, centroid–f0 gap, tonality, HNR, amplitude(dB), time
- フレーム単位(hop=512)。無音フレームは振幅ゲートで除外。`out/descriptors.csv` も出力
- pipeline.py(UMAP版)とは別物＝**解釈可能ビュー**。両者は相補的（UMAP=自動構造発見 / 記述子空間=説明可能）

### 記述子座標を TD の発光ノードに流す（解析層↔出力層の接続）
`td_descriptor_coords.py` で「3記述子＝XYZ」の `td_points.csv` を作り、TDの発光ノードシステムを
**記述子空間で動かす**（＝元デモの最終出力に最接近）。セグメント/cluster/start-end/発光は維持、位置だけ差替。
```bash
# 元デモの TIMBRE SPACE 軸で、色は Centroid–F0 Gap
./venv/bin/python td_descriptor_coords.py --points out/td_points.csv --audio audio \
    --axes spread,centroid,crest --color centroid_f0_gap --out out
# → TD側で points/edges Table DAT を再読込し、重心で再センタリング、再クック
```
- `--axes` を変えれば空間が別の記述子組に組み替わる（例 `centroid,amp_db,flux` = Tone Map 風）
- `--color` 省略で既存クラスタ色を維持。UMAP座標に戻すなら `td_points_umap_backup.csv` を使用
- TD反映は**1コマンド**（`td_refresh` 関数DAT）:
  - TD textport / ボタン: `mod('/seeing_birdsong/td_refresh').refresh()`
  - MCP/execute_python: `op('/seeing_birdsong/td_refresh').module.refresh()`
  - 中身: points/edges を CSV 再読込 → geo/geo_edges を `-重心` で再センタリング →
    cam_wide を PCA broadside で自動フレーミング → 全体 recook
  - 別 out フォルダなら `refresh(base='/path/to/out')`
- 軸変更フロー全体: ① `td_descriptor_coords.py`(Python) で CSV 更新 → ② TD で `td_refresh` を実行

## 背景・色・サイズ・ラベル（元 Lucio Arese 最終出力に寄せる）
- **背景**: 明るいグレー一色（`bg_base` constant ≈0.32）。`overbg`/`overbg_wide` の input1。
- **ポスト順序**: `render(透過)→bloom→overbg(over bg)→out`（bloomを背景合成の**前**に。後だと
  明るいグレー全体が発光して白飛びする）。`bloomthreshold≈0.85`で発光/バーストノードのみ光る。
- **ノード色＝Spectral Centroid**: `td_descriptor_coords.py --color centroid` で cr/cg/cb を centroid ランプに。
- **ノードサイズ＝振幅**: td_points.csv の `amp` 列(0-1, 正規化エネルギー) を `drive`(callback=`drive_cb3`)が
  基底サイズ `0.45+2.0*amp` に反映（＋発光glow＋バースト）。
- **数値ラベル**: 一度実装したが最終的に削除（`labels`/`matlabel` を destroy、td_refresh からも除外）。
  td_points.csv には `label_hz` 列が残っているので、再導入は容易。
  - 再導入時メモ: `labels`(geometryCOMP)配下に各ノードの子geo `L##`(lookat=cam_wide, forwarddir=posz)
    ＋`textSOP`(`{centroid_kHz:.2f}K`)、MAT は bloom閾値以下の白系。geometryCOMP作成時のデフォルトtorusは
    親子とも必ず除去。ラベルサイズを球連動にするなら `L##.par.scale.expr = op('/seeing_birdsong/drive')['sx'][i]`。

## TouchDesignerへ移植
`out/td_*.csv` を Table DAT で読むだけで取り込める。three.js版と1対1で対応：

| three.js | TouchDesigner |
|---|---|
| 点群(ShaderMaterial) | Geometry COMP **Instancing**（tx/ty/tz, color=cr/cg/cb を td_points.csv から） |
| ノード発光glow | instance の `scale`/`emit色` を CHOP で駆動 |
| UnrealBloomPass | **Bloom TOP** |
| 近傍エッジ | td_edges.csv の p0/p1 → **Add SOP**(line) or Line MAT |
| Web Audio 単発再生 | **Audio File In CHOP** + Trim（click→Render Pick） |
| タイムライン同期発光 | Audio File In の再生秒 t を、各instanceの[start,end]と比較する CHOP式で glow 駆動 |
| OrbitControls | Camera COMP + マウス |

取り込み手順（概略）:
1. `Table DAT` で `td_points.csv` を読む → `DAT to CHOP`(tx,ty,tz,cr,cg,cb) → Geometry COMP の Instancing に接続
2. `td_edges.csv` → Script SOP か Add SOP で line 生成
3. Render TOP → **Bloom TOP** → Out
4. `Audio File In CHOP` で再生、再生秒を `t` とし
   `glow = (t>=start && t<end)` を各instanceで計算 → instance color/scale へ
- ※MCP(port 9981)経由で自動生成も可。TDを起動し `mcp_webserver_base.tox` を有効化すれば、こちらでネットワークを組める。

### MCPで構築済みのネットワーク（/seeing_birdsong）
動作確認済み。ノード構成：
```
points(Table DAT)──instances(DAT to CHOP: chanpercol)──┐
clock(Timer CHOP, len=dur, cycle)──┐                    ├─drive(Script CHOP)──┐
                                    └────────────────────┘  tx/ty/tz,r/g/b,sx/sy/sz │
                                                                                     ▼
audio(Audio File In)──adout(Audio Device Out)        geo(Instancing: pos/color/scale=drive)
                                                          │ +sphere(r=0.06)+mat(constant)
                                                          ▼
                                              render──bloom(Bloom TOP)──out
```
- **drive(Script CHOP)** が肝：`T = timer_fraction × dur` と各音節の[start,end]を比較し、
  該当インスタンスの `sx/sy/sz`(5.5倍) と `r/g/b`(増光) を上げる＝時間同期発光
- 再生（頭出し）: `clock` の `start` をパルス。Timerが画のマスタークロック、audioは実時間ループで同期
- 別ファイルに切替: `audio` の file と、drive内 DUR／points CSV を差し替え
- ※サンプル精密同期にしたい場合は Audio File In を Timer 位置で駆動する形に拡張

#### 追加済み機能（エッジ／カメラ追従／リッチ化）
- **エッジ**: `geo_edges`(geometryCOMP) 内の `lines`(Script SOP) が points/edges テーブルから
  近傍線86本を生成。render の geometry に geo と併記
- **エッジも発光ノードに同期して光る**: `lines`(Script SOP, callback=`lines_glow3`) が毎フレーム
  `drive` の `sx`(発光値) を読み、各線の端点を **頂点カラー Cd** で着色（base*(0.04+glow*6)）。
  発光ノード側は白熱、反対端へ暗くフェード＝エネルギーが流れ込む表現。`matedge` は
  `applypointcolor=on`(Cd使用)。`absTime.frame` 参照で毎フレーム再クック
- **カメラ追従**: `focus`(Script CHOP=最も発光中のインスタンスの中心化座標) → `focuslag`(Lag CHOP)
  → `camtarget`(Null COMP, tx/ty/tz=focuslag) を `cam.lookat` に。cam は focuslag 周りを
  `absTime.seconds*0.18` でゆっくり周回（位置=focus+D·(sin,cos)）。出力=`out`
- **全景カメラ(別系統)**: `cam_wide`(`origin_target`=原点を注視)で全体を見渡す。
  専用レンダー `render_wide`→`bloom_wide`→`overbg_wide`(over bg)→**`out_wide`**。追従カメラと同時に存在。
  本番表示は out / out_wide を選ぶ（Perform/Window で対象TOPを指定）
  - **周回(ターンテーブル)**: tx/tz を `R*sin/cos(absTime.seconds*ORBIT_SPEED)`、ty=H 固定でY軸まわりを周回。
    `td_refresh` 冒頭の `ORBIT_SPEED`(rad/秒, 既定0.13)/`ELEV_DEG`(仰角24)/`DIST_MULT`(距離=雲半径×1.9) で調整。
    距離・仰角は雲サイズから自動算出。固定に戻すなら tx/tz の式を消して定数にする。
- **リッチ化(ポスト処理)**: `render(透過)`→`overbg`(over `bg`濃紺)→`bloom`(Bloom TOP)→`out`
  ※フィードバック残光トレイル(fb/trailfade/addtrail)は試作後に削除（不要との判断）。
    再導入するなら Feedback TOP の**入力にループ出力を接続**するのを忘れずに
- ⚠️ハマり所: instance color を `replace` で r/g/b だけ与えるとアルファ=0になり、透過背景で球が消える。
  → drive に `a`(=1) を出して `geo.instancea='a'`。また各ポストTOPは `outputresolution=custom`(1280x720) で統一

#### 3D質感アップ（球シェーディング）
- ノードは **PBR MAT(`matpbr`)** ＝ `applypointcolor`でインスタンス色をbaseColorに、
  metallic0/roughness0.38/specularlevel0.65、`rimlight`(青)で輪郭発光、`darknessemit`(青)で影側を起こす
- 球(`geo/shape`)は `type=poly, freq=8, normals=on`(642点)で滑らか、半径0.09
- **3灯ライティング**: key(暖色,+5/8/7)・fill(寒色,-7/2/5)・rim(青,0/-3/-9)。色は light の `cr/cg/cb`、強度は `dimmer`。render.lights に3つ列挙
- drive の基底輝度 `bb=1.15(+発光時+2.4)`：非発光ノードも色付き3D球として視認でき、発光ノードは白熱＋bloom
- **アタック・バースト**: 音節オンセット(start)直後だけ `burst=exp(-(T-start)/0.05)`(0.2s窓)で
  スケール(+burst*7)と輝度(+burst*4.5)を瞬間的に跳ね上げ→反応した瞬間に巨大閃光、即収束。
  callback=`drive_cb2`（係数は burst*7=スケール / burst*4.5=輝度 で調整）
- ※constant MATの加算合成（平たい発光ブロブ）から、陰影＋ハイライト＋リムの立体球へ刷新

#### 環境光（IBL）で映り込み＝高級感
- **Environment Light COMP(`envlight`)**：`envlightmap` に手続き生成した環境マップ(equirect 1024x512)を与え、
  PBR球に映り込み(IBL)を付与。`dimmer=2.6`。render.lights に列挙
- 環境マップ＝TOPで合成（HDRファイル不要）: `envbase`(濃紺constant) + `envkey`(上方の白い円・キー光) +
  `envhor`(水平の青い光帯) を `envcomp`(add) → `envblur` → envlightmap
- 反射を明瞭にするため PBR を `roughness=0.22, metallic=0.2` に（数値を上げると曇りガラス、下げると鏡面）
- 映り込みの向きは `envlight` の `envlightmaprotatex/y/z` で回せる

## メモ
- venv は Python 3.11（UMAP=numba / TF 互換のため。3.14では入らない）
- 点が少ないと多様体は団子になりがち。数百〜数千セグメントあると分離が見える
- 拡張パス：`coords3d.npy` を three.js 点群ビューアに読ませれば、発光ノードグラフのルックに寄せられる
