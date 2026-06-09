#!/usr/bin/env python
"""
Descriptor Space (元 "Seeing Birdsong" 流)
------------------------------------------
UMAPのような学習埋め込みではなく、**名前のついたスペクトル記述子そのもの**を
X/Y/Z/色の軸にした、設定可能な3D散布図を作る。各点＝1フレーム。

元デモの "TIMBRE SPACE"(Spectral Spread × Centroid × Crest, 色=Centroid–F0 Gap) や
"TONE MAP"(Amplitude × Centroid, 色=Flux) を、軸ドロップダウンで自由に組み替えられる。

usage:
    ./venv/bin/python descriptor_space.py --audio audio --out out
"""
import argparse
import glob
import os

import numpy as np
import pandas as pd

AUDIO_EXTS = ("*.wav", "*.WAV", "*.flac", "*.mp3", "*.m4a", "*.aif", "*.aiff", "*.ogg")

# 散布の軸に使える記述子（表示名 -> 列名）
DESCRIPTORS = [
    ("Spectral Centroid (Hz)", "centroid"),
    ("Spectral Spread (Hz)", "spread"),
    ("Spectral Crest", "crest"),
    ("Spectral Flatness", "flatness"),
    ("Spectral Contrast (dB)", "contrast"),
    ("Spectral Slope", "slope"),
    ("Spectral Flux", "flux"),
    ("Rolloff 85% (Hz)", "rolloff85"),
    ("Rolloff 95% (Hz)", "rolloff95"),
    ("Dominant Freq (Hz)", "domfreq"),
    ("F0 (Hz)", "f0"),
    ("Centroid–F0 Gap (Hz)", "centroid_f0_gap"),
    ("Tonality", "tonality"),
    ("Harmonic/Noise Ratio", "hnr"),
    ("Amplitude (dB)", "amp_db"),
    ("Time (s)", "time"),
]


def frame_descriptors(y, sr, n_fft=2048, hop=512):
    """1フレームごとのスペクトル記述子を辞書(np.array)で返す。"""
    import librosa

    S = np.abs(librosa.stft(y, n_fft=n_fft, hop_length=hop)) + 1e-10
    freqs = librosa.fft_frequencies(sr=sr, n_fft=n_fft)
    T = S.shape[1]
    eps = 1e-10

    centroid = librosa.feature.spectral_centroid(S=S, sr=sr)[0]
    spread = librosa.feature.spectral_bandwidth(S=S, sr=sr)[0]
    rolloff85 = librosa.feature.spectral_rolloff(S=S, sr=sr, roll_percent=0.85)[0]
    rolloff95 = librosa.feature.spectral_rolloff(S=S, sr=sr, roll_percent=0.95)[0]
    flatness = librosa.feature.spectral_flatness(S=S)[0]
    contrast = librosa.feature.spectral_contrast(S=S, sr=sr).mean(0)
    crest = S.max(0) / (S.mean(0) + eps)

    # spectral slope（周波数に対する振幅の傾き）
    fmean = freqs.mean()
    dfq = freqs - fmean
    num = (dfq[:, None] * (S - S.mean(0)[None, :])).sum(0)
    slope = num / (dfq ** 2).sum() * 1e3  # スケール見やすく

    # flux（隣接フレームのスペクトル差）
    flux = np.sqrt((np.diff(S, axis=1) ** 2).sum(0))
    flux = np.concatenate([[flux[0] if len(flux) else 0.0], flux])[:T]

    rms = librosa.feature.rms(S=S)[0]
    amp_db = librosa.amplitude_to_db(rms + eps)

    domfreq = freqs[S.argmax(0)]

    try:
        f0 = librosa.yin(y, fmin=300, fmax=12000, sr=sr, hop_length=hop)
        f0 = np.resize(f0, T)
    except Exception:
        f0 = np.full(T, np.nan)
    centroid_f0_gap = centroid - f0

    tonality = 1.0 - flatness  # 0=ノイズ的, 1=トーン的

    # harmonic/noise ratio（HPSSで近似）
    try:
        H, P = librosa.decompose.hpss(S)
        hnr = 10.0 * np.log10((H.sum(0) + eps) / (P.sum(0) + eps))
    except Exception:
        hnr = np.zeros(T)

    time = librosa.frames_to_time(np.arange(T), sr=sr, hop_length=hop)

    return dict(
        centroid=centroid, spread=spread, crest=crest, flatness=flatness,
        contrast=contrast, slope=slope, flux=flux, rolloff85=rolloff85,
        rolloff95=rolloff95, domfreq=domfreq, f0=f0,
        centroid_f0_gap=centroid_f0_gap, tonality=tonality, hnr=hnr,
        amp_db=amp_db, time=time,
    )


def collect(audio_dir, sr_target=48000, gate_db=45.0):
    import librosa

    files = []
    for ext in AUDIO_EXTS:
        files += glob.glob(os.path.join(audio_dir, "**", ext), recursive=True)
    files = sorted(set(files))
    if not files:
        raise SystemExit(f"[!] {audio_dir}/ に音声がありません。")

    rows = []
    for fp in files:
        try:
            y, sr = librosa.load(fp, sr=sr_target, mono=True)
        except Exception as e:
            print(f"  [skip] {os.path.basename(fp)}: {e}")
            continue
        if y.size == 0:
            continue
        d = frame_descriptors(y, sr)
        n = len(d["time"])
        # 無音フレームを除外（ノイズフロアを落とす）
        keep = d["amp_db"] > (d["amp_db"].max() - gate_db)
        sub = pd.DataFrame({k: v[:n] for k, v in d.items()})
        sub = sub[keep].copy()
        sub["file"] = os.path.basename(fp)
        rows.append(sub)
        print(f"  [ok] {os.path.basename(fp)} -> {len(sub)}/{n} frames")
    df = pd.concat(rows, ignore_index=True)
    return df


def make_viewer(df, out_html):
    import plotly.graph_objects as go

    # 初期表示 = 元デモの TIMBRE SPACE
    ix, iy, iz, ic = "spread", "centroid", "crest", "centroid_f0_gap"

    def col(name):
        return df[name].astype(float).tolist()

    fig = go.Figure(
        go.Scatter3d(
            x=col(ix), y=col(iy), z=col(iz), mode="markers",
            marker=dict(
                size=2.5, color=col(ic), colorscale="Turbo",
                opacity=0.8, showscale=True,
                colorbar=dict(title=dict(text="Centroid–F0 Gap", side="right"),
                              thickness=10, len=0.5),
            ),
            customdata=df[["file", "time"]].values,
            hovertemplate="%{customdata[0]}<br>t=%{customdata[1]:.2f}s<extra></extra>",
        )
    )

    def label_of(colname):
        return next(l for l, c in DESCRIPTORS if c == colname)

    def axis_menu(axis_key, scene_axis, default_col, x=0.0):
        buttons = []
        for lbl, c in DESCRIPTORS:
            buttons.append(dict(
                label=lbl, method="update",
                args=[{axis_key: [col(c)]},
                      {f"scene.{scene_axis}.title.text": lbl}],
            ))
        active = [c for _, c in DESCRIPTORS].index(default_col)
        return dict(buttons=buttons, active=active, x=x, y=1.08,
                    xanchor="left", yanchor="top", showactive=True,
                    bgcolor="#14182c", font=dict(size=10, color="#cfe0ff"),
                    bordercolor="#4a5a90")

    def color_menu(default_col, x=0.0):
        buttons = []
        for lbl, c in DESCRIPTORS:
            buttons.append(dict(
                label=lbl, method="restyle",
                args=[{"marker.color": [col(c)],
                       "marker.colorbar.title.text": lbl}],
            ))
        active = [c for _, c in DESCRIPTORS].index(default_col)
        return dict(buttons=buttons, active=active, x=x, y=1.16,
                    xanchor="left", yanchor="top", showactive=True,
                    bgcolor="#241430", font=dict(size=10, color="#ffd9f0"),
                    bordercolor="#90537a")

    fig.update_layout(
        updatemenus=[
            axis_menu("x", "xaxis", ix, x=0.00),
            axis_menu("y", "yaxis", iy, x=0.25),
            axis_menu("z", "zaxis", iz, x=0.50),
            color_menu(ic, x=0.78),
        ],
        annotations=[
            dict(text="X", x=0.00, y=1.13, xref="paper", yref="paper",
                 showarrow=False, font=dict(color="#8fb4ff", size=11)),
            dict(text="Y", x=0.25, y=1.13, xref="paper", yref="paper",
                 showarrow=False, font=dict(color="#8fb4ff", size=11)),
            dict(text="Z", x=0.50, y=1.13, xref="paper", yref="paper",
                 showarrow=False, font=dict(color="#8fb4ff", size=11)),
            dict(text="COLOR", x=0.78, y=1.21, xref="paper", yref="paper",
                 showarrow=False, font=dict(color="#ff9fd0", size=11)),
        ],
        template="plotly_dark", title="Seeing Birdsong — descriptor space",
        scene=dict(
            xaxis=dict(title=dict(text=label_of(ix)), backgroundcolor="#06070a"),
            yaxis=dict(title=dict(text=label_of(iy)), backgroundcolor="#06070a"),
            zaxis=dict(title=dict(text=label_of(iz)), backgroundcolor="#06070a"),
            bgcolor="#06070a",
        ),
        paper_bgcolor="#06070a", font=dict(color="#cfd8ff"),
        margin=dict(l=0, r=0, t=70, b=0),
    )
    fig.write_html(out_html, include_plotlyjs="cdn")
    print(f"[✓] wrote {out_html}  ({len(df)} frames, axes configurable)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio", default="audio")
    ap.add_argument("--out", default="out")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    df = collect(args.audio)
    df.to_csv(os.path.join(args.out, "descriptors.csv"), index=False)
    print(f"[i] {len(df)} frames, {len(DESCRIPTORS)} descriptors")
    make_viewer(df, os.path.join(args.out, "descriptor_space.html"))


if __name__ == "__main__":
    main()
