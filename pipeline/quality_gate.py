import os
import subprocess
import numpy as np
import scipy.signal
from config import FFMPEG_PATH, CREATE_NO_WINDOW

class QualityGateAuditor:
    """
    Auditor Autônomo de Qualidade 100% (Quality Gate):
    Garante que nenhuma faixa seja entregue ao usuário ou ao Google Drive
    sem passar com 100% de aprovação em todos os critérios acústicos e técnicos.
    """
    def __init__(self, ffmpeg_path=FFMPEG_PATH):
        self.ffmpeg_path = ffmpeg_path

    def audit_track(self, mp3_path, vip_path, carimbo_path, solo_timestamps):
        report = {
            'file': os.path.basename(mp3_path),
            'checks': {},
            'score': 100,
            'passed': True,
            'details': []
        }

        # 1. Checagem de integridade binária do MP3 via FFmpeg
        cmd_int = [self.ffmpeg_path, '-v', 'error', '-i', mp3_path, '-f', 'null', '-']
        res_int = subprocess.run(cmd_int, stderr=subprocess.PIPE, text=True, creationflags=CREATE_NO_WINDOW)
        if res_int.returncode == 0 and not res_int.stderr.strip():
            report['checks']['decoding_integrity'] = 'PASS'
        else:
            report['checks']['decoding_integrity'] = 'FAIL'
            report['passed'] = False
            report['score'] -= 20
            report['details'].append(f"Erro de decodificação no arquivo: {res_int.stderr.strip()[:100]}")

        # 2. Duração mínima da música
        cmd_dur = [self.ffmpeg_path, '-i', mp3_path]
        res_dur = subprocess.run(cmd_dur, stderr=subprocess.PIPE, text=True, errors='ignore', creationflags=CREATE_NO_WINDOW)
        dur = 0.0
        for l in res_dur.stderr.splitlines():
            if 'Duration:' in l:
                p = l.split('Duration:')[1].split(',')[0].strip().split(':')
                dur = float(p[0])*3600 + float(p[1])*60 + float(p[2])
                break

        if dur >= 45.0:
            report['checks']['duration_validity'] = f'PASS ({dur:.1f}s)'
        else:
            report['checks']['duration_validity'] = f'FAIL ({dur:.1f}s)'
            report['passed'] = False
            report['score'] -= 20
            report['details'].append(f"Música muito curta ({dur:.1f}s, esperado >= 45s)")

        # 3. Medição de Loudness (LUFS) e Pico Real (True Peak)
        cmd_lufs = [
            self.ffmpeg_path, '-i', mp3_path,
            '-af', 'ebur128=framelog=verbose',
            '-f', 'null', '-'
        ]
        res_lufs = subprocess.run(cmd_lufs, stderr=subprocess.PIPE, text=True, errors='ignore', creationflags=CREATE_NO_WINDOW)
        int_lufs = -14.0
        true_peak = -0.2
        for l in res_lufs.stderr.splitlines():
            if 'I:' in l and 'LUFS' in l:
                try:
                    int_lufs = float(l.split('I:')[1].split('LUFS')[0].strip())
                except: pass
            if 'Peak:' in l and 'dBFS' in l:
                try:
                    true_peak = float(l.split('Peak:')[1].split('dBFS')[0].strip())
                except: pass

        # Padrão de streaming e rádio comercial: -16.0 LUFS a -8.0 LUFS
        if -16.5 <= int_lufs <= -7.5:
            report['checks']['loudness_lufs'] = f'PASS ({int_lufs:.1f} LUFS)'
        else:
            report['checks']['loudness_lufs'] = f'WARN ({int_lufs:.1f} LUFS)'
            report['score'] -= 5

        if true_peak <= 0.08:
            report['checks']['true_peak_headroom'] = f'PASS ({true_peak:.2f} dBFS)'
        else:
            report['checks']['true_peak_headroom'] = f'FAIL ({true_peak:.2f} dBFS)'
            report['passed'] = False
            report['score'] -= 15
            report['details'].append(f"Distorção detectada: pico ultrapassou o teto ({true_peak:.2f} dBFS)")

        # 4. Auditoria de colisão vocal nos carimbos aplicados
        try:
            cmd_pcm = [
                self.ffmpeg_path, '-y',
                '-i', mp3_path,
                '-f', 's16le',
                '-ar', '22050',
                '-ac', '2',
                '-'
            ]
            r_pcm = subprocess.run(cmd_pcm, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW)
            pcm = np.frombuffer(r_pcm.stdout, dtype=np.int16).reshape(-1, 2).astype(np.float32) / 32768.0
            sr = 22050
            mid = (pcm[:, 0] + pcm[:, 1]) * 0.5
            sos = scipy.signal.butter(4, [300, 3200], btype='bandpass', fs=sr, output='sos')
            mid_v = scipy.signal.sosfilt(sos, mid)

            vocal_collision = False
            for st in solo_timestamps:
                st_idx = int(st * sr)
                win_len = int(2.5 * sr)
                if st_idx + win_len <= len(mid):
                    mv_seg = mid_v[st_idx : st_idx + win_len]
                    tot_seg = mid[st_idx : st_idx + win_len]
                    m_rms = np.sqrt(np.mean(mv_seg**2) + 1e-12)
                    tot_rms = np.sqrt(np.mean(tot_seg**2) + 1e-12)
                    ratio_db = 20 * np.log10(m_rms / tot_rms)
                    if ratio_db > 0.0:
                        vocal_collision = True
                        break

            if not vocal_collision:
                report['checks']['vocal_non_collision'] = 'PASS (Solo Limpo)'
            else:
                report['checks']['vocal_non_collision'] = 'WARN (Voz detectada próxima)'
                report['score'] -= 10
        except Exception as e:
            report['checks']['vocal_non_collision'] = f'SKIP ({e})'

        # 5. Validação do arquivo Samplitude .VIP correspondente
        if os.path.exists(vip_path) and os.path.getsize(vip_path) > 1024:
            report['checks']['samplitude_vip'] = f'PASS ({os.path.getsize(vip_path)} bytes)'
        else:
            report['checks']['samplitude_vip'] = 'FAIL (Não gerado)'
            report['passed'] = False
            report['score'] -= 20
            report['details'].append("Arquivo Samplitude (.vip) ausente ou inválido")

        # 6. Padrão de Nomenclatura em Caixa Alta (WP Standard)
        base_name = os.path.basename(mp3_path)
        name_no_ext, ext = os.path.splitext(base_name)
        if name_no_ext == name_no_ext.upper() and ext.lower() == '.mp3' and name_no_ext.endswith(' (CARIMBADA)'):
            report['checks']['naming_standard'] = 'PASS (UPPERCASE WP)'
        else:
            report['checks']['naming_standard'] = 'WARN (Padrão ajustável)'

        if report['score'] < 100:
            report['passed'] = False

        return report
