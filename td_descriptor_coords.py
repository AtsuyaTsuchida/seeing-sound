#!/usr/bin/env python
"""
TD用に「3つのスペクトル記述子＝XYZ座標」を書き出す。
既存の td_points.csv（セグメント・start/end・cluster・色）を再利用し、
位置(tx,ty,tz)だけを選んだ記述子に差し替える。TDの発光ノードシステムが
そのまま"記述子空間"で動く＝解析層(descriptor)と出力層(TDの3D)の接続。

usage:
  ./venv/bin/python td_descriptor_coords.py --points out/td_points.csv \
      --audio audio --axes spread,centroid,crest --out out
"""
import argparse
import os

import numpy as np
import pandas as pd

from descriptor_space import frame_descriptors, DESCRIPTORS
from pipeline import knn_edges

VALID = {c for _, c in DESCRIPTORS}


def robust_norm(v, lo_pct=2, hi_pct=98, span=10.0):
    """外れ値に強い min-max を [-span/2, span/2] に。"""
    v = np.asarray(v, float)
    lo, hi = np.nanpercentile(v, [lo_pct, hi_pct])
    if hi - lo < 1e-9:
        return np.zeros_like(v)
    n = (np.clip(v, lo, hi) - lo) / (hi - lo)
    return n * span - span / 2.0


def ramp_color(t):
    """0..1 を blue→cyan→green→yellow→red の簡易ランプ(RGB 0-1)。"""
    t = float(np.clip(t, 0, 1))
    stops = [(0.0, (0.15, 0.25, 1.0)), (0.25, (0.0, 0.8, 1.0)),
             (0.5, (0.1, 1.0, 0.3)), (0.75, (1.0, 0.85, 0.1)),
             (1.0, (1.0, 0.2, 0.1))]
    for (t0, c0), (t1, c1) in zip(stops[:-1], stops[1:]):
        if t <= t1:
            f = (t - t0) / (t1 - t0 + 1e-9)
            return tuple(c0[i] + (c1[i] - c0[i]) * f for i in range(3))
    return stops[-1][1]


def seg_descriptor(d, start, end, name):
    """フレーム記述子 d から区間[start,end]の平均を取る。"""
    tm = d["time"]
    m = (tm >= start) & (tm < end)
    if not m.any():  # 短すぎ → 最近傍フレーム
        m = np.array([np.argmin(np.abs(tm - (start + end) / 2))])
        return float(d[name][m][0])
    return float(np.nanmean(d[name][m]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--points", required=True, help="既存 td_points.csv")
    ap.add_argument("--audio", required=True)
    ap.add_argument("--out", default="out")
    ap.add_argument("--axes", default="spread,centroid,crest",
                    help="X,Y,Z に使う記述子（カンマ区切り）")
    ap.add_argument("--color", default="", help="色に使う記述子（空=既存クラスタ色を維持）")
    args = ap.parse_args()

    axes = [a.strip() for a in args.axes.split(",")]
    assert len(axes) == 3, "--axes は3つ指定"
    for a in axes + ([args.color] if args.color else []):
        assert a in VALID, f"未知の記述子: {a}（有効: {sorted(VALID)}）"

    import librosa

    pts = pd.read_csv(args.points)
    # ファイルごとにフレーム記述子をキャッシュ
    cache = {}
    for f in pts["file"].unique():
        fp = os.path.join(args.audio, f)
        y, sr = librosa.load(fp, sr=48000, mono=True)
        cache[f] = frame_descriptors(y, sr)
        print(f"  [an] {f}")

    # セグメントごとに記述子を集計（色/軸＋ラベル用centroid・サイズ用amp_dbを常に含める）
    need = set(axes + ([args.color] if args.color else []) + ["centroid", "amp_db"])
    cols = {a: [] for a in need}
    for _, row in pts.iterrows():
        d = cache[row["file"]]
        for name in cols:
            cols[name].append(seg_descriptor(d, float(row.start), float(row.end), name))

    out = pts.copy()
    # サイズ用: 振幅(dB)→線形→ロバスト正規化[0,1]
    lin = 10.0 ** (np.asarray(cols["amp_db"], float) / 20.0)
    lo, hi = np.nanpercentile(lin, [2, 98])
    out["amp"] = np.clip((lin - lo) / (hi - lo + 1e-12), 0, 1).round(4)
    # ラベル用: セグメントの spectral centroid (Hz)
    out["label_hz"] = np.round(cols["centroid"], 1)
    coords = np.zeros((len(out), 3), float)
    for i, a in enumerate(axes):
        coords[:, i] = robust_norm(cols[a])
    out["tx"], out["ty"], out["tz"] = coords[:, 0], coords[:, 1], coords[:, 2]

    if args.color:
        cv = np.asarray(cols[args.color], float)
        lo, hi = np.nanpercentile(cv, [2, 98])
        for k, v in enumerate(cv):
            r, g, b = ramp_color((np.clip(v, lo, hi) - lo) / (hi - lo + 1e-9))
            out.at[k, "cr"], out.at[k, "cg"], out.at[k, "cb"] = round(r, 4), round(g, 4), round(b, 4)

    os.makedirs(args.out, exist_ok=True)
    out.to_csv(os.path.join(args.out, "td_points.csv"), index=False)
    # 記述子空間での近傍グラフ
    edges = knn_edges(coords)
    pd.DataFrame([{"p0": int(a), "p1": int(b)} for a, b in edges]).to_csv(
        os.path.join(args.out, "td_edges.csv"), index=False)
    print(f"[✓] td_points.csv / td_edges.csv 更新: axes={axes} color={args.color or 'cluster'} "
          f"({len(out)} pts, {len(edges)} edges)")


if __name__ == "__main__":
    main()
