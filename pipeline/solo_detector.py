import os
import subprocess
import numpy as np
import scipy.signal
from config import FFMPEG_PATH, CREATE_NO_WINDOW

class SmartSoloDetector:
    """
    Detector Espectral Inteligente de Solos e Trechos Instrumentais.
    Detecta cirurgicamente:
    - Intro (introdução instrumental antes dos vocais)
    - Solo do Meio (ponte instrumental / solo de sanfona, guitarra, etc.)
    - Solo Final / Outro (trecho instrumental pós-refrão antes do fade-out)
    """
    def __init__(self, ffmpeg_path=FFMPEG_PATH):
        self.ffmpeg_path = ffmpeg_path

    def decode_pcm(self, audio_path, sample_rate=22050):
        cmd = [
            self.ffmpeg_path, '-y',
            '-i', audio_path,
            '-f', 's16le',
            '-ar', str(sample_rate),
            '-ac', '2',
            '-'
        ]
        res = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            creationflags=CREATE_NO_WINDOW
        )
        if not res.stdout or len(res.stdout) < sample_rate * 4:
            raise ValueError(f"Áudio inválido ou muito curto para análise: {audio_path}")

        audio = np.frombuffer(res.stdout, dtype=np.int16).reshape(-1, 2).astype(np.float32) / 32768.0
        return audio, sample_rate

    def detect_best_spot(self, mid, side, mid_v, side_v, sr, start_sec, end_sec, jingle_duration):
        win_len = int((jingle_duration + 0.4) * sr)
        step = int(0.1 * sr)

        start_idx = max(0, int(start_sec * sr))
        end_idx = min(len(mid), int(end_sec * sr))

        if end_idx <= start_idx + win_len:
            mid_sec = (start_sec + end_sec) / 2.0
            return {'time': round(mid_sec, 2), 'score': 0.0}

        best_score = 999.0
        best_t = (start_sec + end_sec) / 2.0

        for i in range(start_idx, end_idx - win_len, step):
            t = i / sr
            tot = mid[i : i + win_len]
            tot_rms = np.sqrt(np.mean(tot**2) + 1e-12)
            tot_db = 20 * np.log10(tot_rms)
            if tot_db < -36.0:
                continue

            mv = mid_v[i : i + win_len]
            sv = side_v[i : i + win_len]
            m_rms = np.sqrt(np.mean(mv**2) + 1e-12)
            s_rms = np.sqrt(np.mean(sv**2) + 1e-12)

            vocal_to_tot = 20 * np.log10(m_rms / tot_rms)
            ms_ratio = np.clip(20 * np.log10((m_rms + 1e-6) / (s_rms + 1e-6)), -10.0, 10.0)
            score = vocal_to_tot + 0.5 * ms_ratio

            if score < best_score:
                best_score = score
                best_t = t + 0.2

        return {'time': round(best_t, 2), 'score': round(float(best_score), 2)}

    def detect_spots(self, audio_path, jingle_duration=3.0, trim_start=0.0, trim_end=None, spots=None):
        """
        Calcula as posições de carimbo conforme os spots solicitados:
        spots: lista contendo 'intro', 'solo_meio', 'outro' (ou derivados)
        """
        audio, sr = self.decode_pcm(audio_path)
        total_dur = len(audio) / sr

        if trim_end is None or trim_end <= 0 or trim_end > total_dur:
            trim_end = total_dur

        body_start = max(0.0, trim_start)
        body_end = min(total_dur, trim_end)
        body_len = body_end - body_start

        mid = (audio[:, 0] + audio[:, 1]) * 0.5
        side = (audio[:, 0] - audio[:, 1]) * 0.5

        # Filtro passa-faixa Butterworth 4ª ordem na faixa vocal (300 - 3200 Hz)
        sos_vocal = scipy.signal.butter(4, [300, 3200], btype='bandpass', fs=sr, output='sos')
        mid_v = scipy.signal.sosfilt(sos_vocal, mid)
        side_v = scipy.signal.sosfilt(sos_vocal, side)

        if not spots:
            spots = ['solo_meio']

        # Normalização dos identificadores
        normalized_spots = []
        for s in spots:
            s_clean = s.lower().strip()
            if 'intro' in s_clean or 'começo' in s_clean or 'inicio' in s_clean:
                normalized_spots.append('intro')
            elif 'fim' in s_clean or 'outro' in s_clean or 'final' in s_clean:
                normalized_spots.append('outro')
            else:
                normalized_spots.append('solo_meio')

        detected_list = []
        for spot_type in normalized_spots:
            if spot_type == 'intro':
                s_start = body_start + 0.5
                s_end = min(body_start + 35.0, body_start + body_len * 0.28)
            elif spot_type == 'outro':
                s_start = max(body_start + body_len * 0.68, body_end - 45.0)
                s_end = max(s_start + 5.0, body_end - jingle_duration - 4.0)
            else: # solo_meio
                s_start = body_start + body_len * 0.35
                s_end = body_start + body_len * 0.68

            res = self.detect_best_spot(mid, side, mid_v, side_v, sr, s_start, s_end, jingle_duration)
            detected_list.append({
                'spot_type': spot_type,
                'time': res['time'],
                'vocal_score': res['score']
            })

        # Ordena por ordem cronológica e previne colisões muito próximas (< 18s)
        detected_list.sort(key=lambda x: x['time'])
        filtered_list = []
        for item in detected_list:
            if not filtered_list or (item['time'] - filtered_list[-1]['time'] >= 18.0):
                filtered_list.append(item)

        return filtered_list
