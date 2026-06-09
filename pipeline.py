#!/usr/bin/env python
"""
Seeing Birdsong (corpus-explorer edition)
-----------------------------------------
鳥のさえずり録音群を「音節セグメント -> 埋め込み -> 3D多様体」に変換し、
ブラウザで回転・ホバーできるインタラクティブ3Dとして書き出す。

flow:  audio files -> segment(onset|fixed) -> embed(librosa|birdnet)
       -> UMAP(3D) -> HDBSCAN(color) -> Plotly html

usage:
    ./venv/bin/python pipeline.py --audio audio --out out
    ./venv/bin/python pipeline.py --audio audio --method birdnet --seg fixed
"""
import argparse
import glob
import json
import math
import os
import shutil

import numpy as np
import pandas as pd


# --------------------------------------------------------------------------
# 1. segmentation : 1ファイルを音節(またはfixed窓)の区間リストに分ける
# --------------------------------------------------------------------------
def segment_onset(y, sr, min_dur=0.08, max_dur=1.5):
    """onset検出で音節っぽい区間を切り出す。 returns list of (start_s, end_s)."""
    import librosa

    onsets = librosa.onset.onset_detect(
        y=y, sr=sr, units="time", backtrack=True, hop_length=256
    )
    if len(onsets) == 0:
        return [(0.0, len(y) / sr)]
    bounds = list(onsets) + [len(y) / sr]
    segs = []
    for a, b in zip(bounds[:-1], bounds[1:]):
        dur = b - a
        if dur < min_dur:
            continue
        segs.append((a, min(b, a + max_dur)))
    return segs or [(0.0, len(y) / sr)]


def segment_fixed(y, sr, win=3.0, hop=1.5):
    """BirdNET風の固定窓(3s, 50%ホップ)。"""
    total = len(y) / sr
    segs = []
    t = 0.0
    while t < total:
        segs.append((t, min(t + win, total)))
        t += hop
    return segs


# --------------------------------------------------------------------------
# 2. embedding
# --------------------------------------------------------------------------
def embed_librosa(y, sr):
    """librosaの音響特徴を要約した固定長ベクトル(常に動く既定パス)。"""
    import librosa

    if len(y) < sr * 0.05:  # 短すぎる区間は無効
        return None
    feats = []
    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=20)
    feats += [mfcc.mean(1), mfcc.std(1)]
    for fn in (
        librosa.feature.spectral_centroid,
        librosa.feature.spectral_bandwidth,
        librosa.feature.spectral_rolloff,
        librosa.feature.spectral_flatness,
        librosa.feature.zero_crossing_rate,
    ):
        try:
            v = fn(y=y) if fn is not librosa.feature.zero_crossing_rate else fn(y=y)
        except TypeError:
            v = fn(y)
        feats += [v.mean(1), v.std(1)]
    chroma = librosa.feature.chroma_stft(y=y, sr=sr)
    feats += [chroma.mean(1)]
    return np.concatenate([np.atleast_1d(f).ravel() for f in feats]).astype(np.float32)


def human_scalars(y, sr):
    """ホバー表示用の人間に読める値(重心Hz・基本周波数Hz・長さ)。"""
    import librosa

    cent = float(np.mean(librosa.feature.spectral_centroid(y=y, sr=sr)))
    try:
        f0 = librosa.yin(y, fmin=500, fmax=12000, sr=sr)
        f0 = float(np.nanmedian(f0))
    except Exception:
        f0 = float("nan")
    return cent, f0, len(y) / sr


# --------------------------------------------------------------------------
# main pipeline
# --------------------------------------------------------------------------
AUDIO_EXTS = ("*.wav", "*.WAV", "*.flac", "*.mp3", "*.m4a", "*.aif", "*.aiff", "*.ogg")


def collect_segments(audio_dir, method, seg_mode, sr_target=48000):
    import librosa

    files = []
    for ext in AUDIO_EXTS:
        files += glob.glob(os.path.join(audio_dir, "**", ext), recursive=True)
    files = sorted(set(files))
    if not files:
        raise SystemExit(f"[!] {audio_dir}/ に音声ファイルがありません。録音を入れてください。")

    print(f"[i] {len(files)} files / method={method} / seg={seg_mode}")

    rows, vecs = [], []
    birdnet = None
    if method == "birdnet":
        birdnet = _load_birdnet()

    for fp in files:
        try:
            y, sr = librosa.load(fp, sr=sr_target, mono=True)
        except Exception as e:
            print(f"  [skip] {os.path.basename(fp)}: {e}")
            continue
        if y.size == 0:
            continue
        segs = segment_fixed(y, sr) if seg_mode == "fixed" else segment_onset(y, sr)
        for (a, b) in segs:
            seg = y[int(a * sr):int(b * sr)]
            if method == "birdnet":
                vec = birdnet(seg, sr)
            else:
                vec = embed_librosa(seg, sr)
            if vec is None:
                continue
            cent, f0, dur = human_scalars(seg, sr)
            vecs.append(vec)
            rows.append(
                dict(
                    file=os.path.basename(fp),
                    start=round(a, 3),
                    end=round(b, 3),
                    centroid_hz=round(cent, 1),
                    f0_hz=round(f0, 1),
                    dur_s=round(dur, 3),
                )
            )
        print(f"  [ok] {os.path.basename(fp)} -> {len(segs)} seg")

    # 長さ揃え(librosaは固定長、birdnetも固定長。念のため)
    dim = max(len(v) for v in vecs)
    X = np.zeros((len(vecs), dim), np.float32)
    for i, v in enumerate(vecs):
        X[i, : len(v)] = v
    return pd.DataFrame(rows), X


def _load_birdnet():
    """birdnetlibが入っていれば3s窓の埋め込み関数を返す。"""
    from birdnetlib.analyzer import Analyzer  # noqa
    import tensorflow as tf  # noqa

    an = Analyzer()
    interp = an.embedding_interpreter  # tflite interpreter for embeddings

    def emb(seg, sr):
        import librosa

        if len(seg) < sr * 0.5:
            return None
        # BirdNETは48k/3s固定入力
        s = librosa.util.fix_length(seg, size=int(3 * sr))
        inp = interp.get_input_details()[0]
        out = interp.get_output_details()[0]
        interp.resize_tensor_input(inp["index"], [1, len(s)])
        interp.allocate_tensors()
        interp.set_tensor(inp["index"], s.reshape(1, -1).astype(np.float32))
        interp.invoke()
        return interp.get_tensor(out["index"]).ravel().astype(np.float32)

    return emb


def reduce_and_cluster(X, n_dims=3, seed=42):
    from sklearn.preprocessing import StandardScaler
    import umap

    Xs = StandardScaler().fit_transform(X)
    reducer = umap.UMAP(
        n_components=n_dims, n_neighbors=15, min_dist=0.1, random_state=seed
    )
    emb = reducer.fit_transform(Xs)

    labels = np.zeros(len(emb), int)
    try:
        import hdbscan

        labels = hdbscan.HDBSCAN(min_cluster_size=8).fit_predict(emb)
    except Exception as e:
        print(f"  [i] hdbscan skip ({e}) -> single cluster")
    return emb, labels


def knn_edges(emb, k=4):
    """近傍グラフのエッジ(あの"ネットワーク状"の線)。returns list of (i,j)."""
    from sklearn.neighbors import NearestNeighbors

    nn = NearestNeighbors(n_neighbors=min(k + 1, len(emb))).fit(emb)
    _, idx = nn.kneighbors(emb)
    edges = set()
    for i, row in enumerate(idx):
        for j in row[1:]:
            edges.add((min(i, j), max(i, j)))
    return list(edges)


def make_plot(df, emb, labels, out_html, draw_edges=True):
    import plotly.graph_objects as go

    df = df.copy()
    df["x"], df["y"], df["z"] = emb[:, 0], emb[:, 1], emb[:, 2]
    df["cluster"] = labels

    traces = []
    if draw_edges:
        ex, ey, ez = [], [], []
        for i, j in knn_edges(emb):
            ex += [emb[i, 0], emb[j, 0], None]
            ey += [emb[i, 1], emb[j, 1], None]
            ez += [emb[i, 2], emb[j, 2], None]
        traces.append(
            go.Scatter3d(
                x=ex, y=ey, z=ez, mode="lines",
                line=dict(color="rgba(120,160,255,0.12)", width=1),
                hoverinfo="skip", showlegend=False,
            )
        )

    hover = (
        "<b>%{customdata[0]}</b><br>"
        "t=%{customdata[1]}–%{customdata[2]}s<br>"
        "centroid=%{customdata[3]} Hz · f0=%{customdata[4]} Hz<br>"
        "cluster=%{customdata[5]}<extra></extra>"
    )
    traces.append(
        go.Scatter3d(
            x=df.x, y=df.y, z=df.z, mode="markers",
            marker=dict(
                size=4, color=df.cluster, colorscale="Turbo",
                opacity=0.9, line=dict(width=0),
            ),
            customdata=df[
                ["file", "start", "end", "centroid_hz", "f0_hz", "cluster"]
            ].values,
            hovertemplate=hover, showlegend=False,
        )
    )

    fig = go.Figure(traces)
    fig.update_layout(
        template="plotly_dark",
        title="Seeing Birdsong — vocalization manifold",
        scene=dict(
            xaxis=dict(visible=False), yaxis=dict(visible=False),
            zaxis=dict(visible=False), bgcolor="#06070a",
        ),
        margin=dict(l=0, r=0, t=40, b=0),
        paper_bgcolor="#06070a", font=dict(color="#cfd8ff"),
    )
    fig.write_html(out_html, include_plotlyjs="cdn")
    print(f"[✓] wrote {out_html}  ({len(df)} points)")


def _cluster_rgb(c):
    """viewerと同じ黄金角HSL配色をRGB(0-1)で返す。"""
    import colorsys

    if c < 0:
        return (0.30, 0.32, 0.46)
    return colorsys.hls_to_rgb((c * 0.61803398875) % 1.0, 0.62, 0.85)


def export_td(df, emb, labels, out_dir):
    """TouchDesigner用CSV: Table DATで読めばInstancing/Lineにそのまま使える。"""
    d = df.reset_index(drop=True)
    files = list(dict.fromkeys(d["file"].tolist()))  # 出現順のファイル一覧
    fidx = {f: i for i, f in enumerate(files)}
    rows = []
    for i, row in d.iterrows():
        r, g, b = _cluster_rgb(int(labels[i]))
        rows.append(
            dict(
                i=i, tx=float(emb[i, 0]), ty=float(emb[i, 1]), tz=float(emb[i, 2]),
                cr=round(r, 4), cg=round(g, 4), cb=round(b, 4),
                cluster=int(labels[i]), start=float(row.start), end=float(row.end),
                fileidx=fidx[row.file], file=row.file,
            )
        )
    pd.DataFrame(rows).to_csv(os.path.join(out_dir, "td_points.csv"), index=False)
    pd.DataFrame([{"p0": int(a), "p1": int(b)} for a, b in knn_edges(emb)]).to_csv(
        os.path.join(out_dir, "td_edges.csv"), index=False
    )
    pd.DataFrame([{"fileidx": i, "file": f} for f, i in fidx.items()]).to_csv(
        os.path.join(out_dir, "td_files.csv"), index=False
    )
    print(f"[✓] wrote td_points.csv / td_edges.csv / td_files.csv (TouchDesigner)")


def export_scene(df, emb, labels, audio_dir, out_dir):
    """three.jsビューア用に scene.json を書き、参照音声を out/audio/ にコピー。"""
    # basename -> 実体パス を再構築して音声をコピー
    srcmap = {}
    for ext in AUDIO_EXTS:
        for fp in glob.glob(os.path.join(audio_dir, "**", ext), recursive=True):
            srcmap.setdefault(os.path.basename(fp), fp)
    adst = os.path.join(out_dir, "audio")
    os.makedirs(adst, exist_ok=True)
    for name in df["file"].unique():
        src = srcmap.get(name)
        if src and os.path.abspath(src) != os.path.abspath(os.path.join(adst, name)):
            shutil.copy(src, os.path.join(adst, name))

    def clean(v):
        return None if (v is None or (isinstance(v, float) and math.isnan(v))) else v

    points = []
    for i, row in df.reset_index(drop=True).iterrows():
        points.append(
            dict(
                x=float(emb[i, 0]), y=float(emb[i, 1]), z=float(emb[i, 2]),
                file=row.file, start=float(row.start), end=float(row.end),
                centroid_hz=clean(float(row.centroid_hz)),
                f0_hz=clean(float(row.f0_hz)),
                cluster=int(labels[i]),
            )
        )
    scene = dict(points=points, edges=[[int(a), int(b)] for a, b in knn_edges(emb)])
    with open(os.path.join(out_dir, "scene.json"), "w") as f:
        json.dump(scene, f)

    tmpl = os.path.join(os.path.dirname(os.path.abspath(__file__)), "viewer.html")
    if os.path.exists(tmpl):
        shutil.copy(tmpl, os.path.join(out_dir, "viewer.html"))
    print(f"[✓] wrote scene.json + audio/ ({len(points)} pts) -> three.js viewer")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio", default="audio", help="録音フォルダ")
    ap.add_argument("--out", default="out", help="出力フォルダ")
    ap.add_argument("--method", choices=["librosa", "birdnet"], default="librosa")
    ap.add_argument("--seg", choices=["onset", "fixed"], default="onset")
    ap.add_argument("--no-edges", action="store_true")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    df, X = collect_segments(args.audio, args.method, args.seg)
    print(f"[i] {len(df)} segments, feature dim={X.shape[1]} -> UMAP 3D")
    emb, labels = reduce_and_cluster(X, n_dims=3)

    df.to_csv(os.path.join(args.out, "embedding.csv"), index=False)
    np.save(os.path.join(args.out, "coords3d.npy"), emb)
    make_plot(df, emb, labels, os.path.join(args.out, "birdsong.html"),
              draw_edges=not args.no_edges)
    export_scene(df, emb, labels, args.audio, args.out)
    export_td(df, emb, labels, args.out)


if __name__ == "__main__":
    main()
