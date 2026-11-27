import os
import subprocess
import numpy as np
from config import (
    FFMPEG_PATH,
    DEFAULT_DUCKING_DB,
    DEFAULT_LIMITER_CEILING,
    DEFAULT_FADEOUT_SEC,
    DEFAULT_BITRATE,
    DEFAULT_SAMPLE_RATE,
    CREATE_NO_WINDOW
)

def get_audio_info(audio_path, ffmpeg_path=FFMPEG_PATH):
    cmd = [ffmpeg_path, '-i', audio_path]
    res = subprocess.run(
        cmd,
        stderr=subprocess.PIPE,
        text=True,
        errors='ignore',
        creationflags=CREATE_NO_WINDOW
    )
    duration = 180.0
    for line in res.stderr.splitlines():
        if 'Duration:' in line:
            parts = line.split('Duration:')[1].split(',')[0].strip().split(':')
            duration = float(parts[0])*3600 + float(parts[1])*60 + float(parts[2])
            break
    return {'duration': duration}

def analyze_surgical_cuts(audio_path, ffmpeg_path=FFMPEG_PATH):
    """
    Cortes cirúrgicos de início e fim:
    1. Elimina silêncio inicial digital e ruídos abaixo de -38 dBFS.
    2. Detecta preâmbulos falados/vinhetas de DJ nos primeiros 12s antes do ritmo musical começar.
    3. Detecta silêncio no final.
    4. Detecta bloco de divulgação/propaganda pós-música (pausa longa no final seguida de fala curta).
    Retorna: (trim_start, trim_end, original_duration, has_promo)
    """
    cmd = [ffmpeg_path, '-i', audio_path, '-af', 'silencedetect=noise=-38dB:d=0.2', '-f', 'null', '-']
    res = subprocess.run(cmd, stderr=subprocess.PIPE, text=True, errors='ignore', creationflags=CREATE_NO_WINDOW)

    dur = 0.0
    silences = []
    for line in res.stderr.splitlines():
        if 'Duration:' in line and dur == 0.0:
            parts = line.split('Duration:')[1].split(',')[0].strip().split(':')
            dur = float(parts[0])*3600 + float(parts[1])*60 + float(parts[2])
        if 'silence_start:' in line:
            silences.append(('start', float(line.split('silence_start:')[1].strip())))
        elif 'silence_end:' in line:
            silences.append(('end', float(line.split('silence_end:')[1].split('|')[0].strip())))

    if dur <= 0.0:
        dur = get_audio_info(audio_path, ffmpeg_path)['duration']

    # 1. Silêncio inicial
    leading_silence_end = 0.0
    for i in range(len(silences) - 1):
        if silences[i][0] == 'start' and silences[i][1] <= 0.08 and silences[i+1][0] == 'end':
            leading_silence_end = silences[i+1][1]
            break

    # 2. Silêncio final
    trailing_silence_start = dur
    for i in range(len(silences) - 1, -1, -1):
        if silences[i][0] == 'start' and silences[i][1] >= dur - 6.0:
            trailing_silence_start = silences[i][1]
            break

    # 3. Divulgação/locução final pós-pausa (pausa >= 1.8s nos últimos 35% da música)
    promo_cut = dur
    has_promo = False
    for i in range(len(silences) - 1):
        if silences[i][0] == 'start' and silences[i+1][0] == 'end':
            s_start = silences[i][1]
            s_end = silences[i+1][1]
            gap = s_end - s_start
            if s_start >= dur * 0.65 and gap >= 1.8:
                appended_dur = trailing_silence_start - s_end
                if 2.0 <= appended_dur <= 40.0:
                    promo_cut = s_start
                    has_promo = True
                    break

    # 4. Detecção de preâmbulo falado / vinheta de entrada antes do primeiro acorde/batida musical
    groove_time = 0.0
    cmd_head = [ffmpeg_path, '-i', audio_path, '-t', '12', '-f', 's16le', '-ar', '22050', '-ac', '1', '-']
    r_head = subprocess.run(cmd_head, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW)
    head_pcm = np.frombuffer(r_head.stdout, dtype=np.int16).astype(float) / 32768.0

    sr = 22050
    bin_size = int(0.1 * sr)
    if len(head_pcm) >= bin_size * 10:
        bins = []
        for b in range(0, len(head_pcm), bin_size):
            c = head_pcm[b : b + bin_size]
            rms = np.sqrt(np.mean(c**2) + 1e-12)
            pk = np.max(np.abs(c))
            bins.append((b / sr, 20*np.log10(rms), pk))

        groove_idx = -1
        for idx, (t, db, pk) in enumerate(bins):
            if pk >= 0.70 and db >= -14.0:
                groove_idx = idx
                break

        if groove_idx > 0 and bins[groove_idx][0] >= 1.2:
            before = bins[:groove_idx]
            avg_rms = np.mean([b[1] for b in before])
            diff = bins[groove_idx][1] - avg_rms
            if diff >= 4.5 and avg_rms <= -18.0:
                groove_time = max(0.0, bins[groove_idx][0] - 0.04)

    trim_start = max(leading_silence_end, groove_time)
    trim_end = min(dur, trailing_silence_start + 0.1, promo_cut)

    if trim_end <= trim_start + 10.0:
        trim_start = 0.0
        trim_end = dur

    return round(trim_start, 2), round(trim_end, 2), round(dur, 2), has_promo

def render_mastered_audio(
    music_path,
    carimbo_path,
    output_mp3_path,
    solo_timestamps,
    trim_start=0.0,
    trim_end=None,
    ducking_db=DEFAULT_DUCKING_DB,
    limiter_ceiling=DEFAULT_LIMITER_CEILING,
    fadeout_sec=DEFAULT_FADEOUT_SEC,
    bitrate=DEFAULT_BITRATE,
    sample_rate=DEFAULT_SAMPLE_RATE,
    ffmpeg_path=FFMPEG_PATH
):
    """
    Renderiza áudio masterizado com suporte a carimbos únicos ou múltiplos (1x, 2x, 3x):
    - Cortes cirúrgicos de início e fim
    - Fade-out suave no final
    - Injeção precisa de carimbos nos solos detectados
    - Headroom transparente sem distorção (limitador asc=0)
    """
    if not os.path.exists(music_path):
        raise FileNotFoundError(f"Arquivo de música não encontrado: {music_path}")
    if not os.path.exists(carimbo_path):
        raise FileNotFoundError(f"Arquivo de carimbo não encontrado: {carimbo_path}")

    carimbo_info = get_audio_info(carimbo_path, ffmpeg_path)
    carimbo_dur = carimbo_info['duration']

    music_info = get_audio_info(music_path, ffmpeg_path)
    original_dur = music_info['duration']

    if trim_end is None or trim_end <= 0 or trim_end > original_dur:
        trim_end = original_dur

    trim_start = max(0.0, min(trim_start, trim_end - 5.0))
    net_duration = max(5.0, trim_end - trim_start)

    # Converte timestamp em lista se for único
    if isinstance(solo_timestamps, (int, float)):
        solo_timestamps = [float(solo_timestamps)]
    elif not solo_timestamps:
        solo_timestamps = [trim_start + net_duration * 0.5]

    # Calcula delays relativos dentro do áudio cortado
    relative_solos = []
    for st in solo_timestamps:
        rel = st - trim_start if st >= trim_start else st
        rel = max(0.5, min(rel, net_duration - carimbo_dur - 0.5))
        relative_solos.append(rel)

    fade_d = min(fadeout_sec, net_duration * 0.25)
    fade_st = max(0.0, net_duration - fade_d)

    # 1. Trilha musical
    music_chain = (
        f"[0:a]atrim=start={trim_start:.2f}:end={trim_end:.2f},asetpts=PTS-STARTPTS,"
        f"afade=t=out:st={fade_st:.2f}:d={fade_d:.2f}"
    )

    if abs(ducking_db) >= 0.05:
        # Se usuário solicitar ducking nas janelas dos carimbos
        duck_vol = round(10 ** (ducking_db / 20.0), 4)
        ramp = 0.15
        sub_exprs = []
        for rel in relative_solos:
            s1 = max(0.0, rel - ramp)
            s2 = rel
            e1 = rel + carimbo_dur
            e2 = e1 + ramp
            sub_exprs.append(f"(between(t,{s1:.2f},{e2:.2f}))")
        
        cond_comb = "+".join(sub_exprs)
        vol_expr = f"if({cond_comb},{duck_vol},1.0)"
        music_chain += f",volume=eval=frame:volume='{vol_expr}'[music_cut];"
    else:
        music_chain += "[music_cut];"

    # 2. Trilhas dos carimbos (um canal de delay para cada repetição)
    carimbo_chains = ""
    mix_inputs = ["[music_cut]"]
    for idx, rel in enumerate(relative_solos):
        delay_ms = int(rel * 1000)
        label = f"carimbo_{idx}"
        carimbo_chains += f"[1:a]adelay={delay_ms}|{delay_ms},volume=0.92[{label}];"
        mix_inputs.append(f"[{label}]")

    num_inputs = len(mix_inputs)
    inputs_joined = "".join(mix_inputs)
    filter_complex = (
        f"{music_chain}"
        f"{carimbo_chains}"
        f"{inputs_joined}amix=inputs={num_inputs}:duration=first:dropout_transition=0:normalize=0[mixed];"
        f"[mixed]alimiter=limit={limiter_ceiling}:attack=2:release=20:asc=0[mastered]"
    )

    os.makedirs(os.path.dirname(os.path.abspath(output_mp3_path)), exist_ok=True)

    cmd = [
        ffmpeg_path, '-y',
        '-i', music_path,
        '-i', carimbo_path,
        '-filter_complex', filter_complex,
        '-map', '[mastered]',
        '-c:a', 'libmp3lame',
        '-b:a', bitrate,
        '-ar', str(sample_rate),
        output_mp3_path
    ]

    res = subprocess.run(
        cmd,
        stderr=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        text=True,
        creationflags=CREATE_NO_WINDOW
    )
    if res.returncode != 0:
        raise RuntimeError(f"Erro no FFmpeg: {res.stderr}")

    return {
        'path': os.path.abspath(output_mp3_path),
        'trim_start': trim_start,
        'trim_end': trim_end,
        'duration': round(net_duration, 2),
        'relative_solos': [round(r, 2) for r in relative_solos]
    }
