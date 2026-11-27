import struct
import os
import subprocess
from config import FFMPEG_PATH, CREATE_NO_WINDOW

def get_audio_duration(file_path, ffmpeg_path=FFMPEG_PATH):
    cmd = [ffmpeg_path, '-i', file_path]
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
    return duration

def build_phys_entry(file_path):
    # 1. ufil chunk (UTF-16LE with null-terminator)
    utf16_bytes = (file_path + '\x00').encode('utf-16le')
    ufil = b'ufil' + struct.pack('<I', len(utf16_bytes)) + utf16_bytes
    if len(utf16_bytes) % 2 != 0:
        ufil += b'\x00'
    
    # 2. file chunk (fixed 520 bytes payload)
    dirname = os.path.dirname(os.path.abspath(file_path))
    base = os.path.splitext(os.path.basename(file_path))[0]
    hmp = f'{base}.HMP'
    full = os.path.abspath(file_path)
    
    payload = bytearray(520)
    def put_str(buf, offset, max_len, text):
        enc = text.encode('latin1', errors='replace')[:max_len-1]
        buf[offset:offset+len(enc)] = enc
    
    put_str(payload, 0, 130, dirname)
    put_str(payload, 130, 130, hmp)
    put_str(payload, 260, 260, full)
    
    file_chunk = b'file' + struct.pack('<I', 520) + bytes(payload)
    return ufil + file_chunk

def create_samplitude_vip(
    template_path,
    output_path,
    music_path,
    carimbo_path,
    solo_timestamps,
    music_dur=None,
    carimbo_dur=None,
    sample_rate=44100
):
    """
    Gera projeto nativo Samplitude / Sequoia (.VIP):
    - Trilha 1: Música masterizada
    - Trilha 2+: Carimbos posicionados cirurgicamente nos solos detectados
    - Mapeamento físico completo de arquivos (LIST phys)
    """
    if not os.path.exists(template_path):
        raise FileNotFoundError(f"Template VIP não encontrado: {template_path}")
    if not os.path.exists(music_path):
        raise FileNotFoundError(f"Áudio da música não encontrado: {music_path}")
    if not os.path.exists(carimbo_path):
        raise FileNotFoundError(f"Carimbo não encontrado: {carimbo_path}")

    if music_dur is None:
        music_dur = get_audio_duration(music_path)
    if carimbo_dur is None:
        carimbo_dur = get_audio_duration(carimbo_path)

    if isinstance(solo_timestamps, (int, float)):
        solo_timestamps = [float(solo_timestamps)]

    with open(template_path, 'rb') as f:
        data = f.read()

    # Monta LIST phys chunk (0: musica, 1: carimbo)
    phys_body = build_phys_entry(music_path) + build_phys_entry(carimbo_path)
    phys_chunk = b'LIST' + struct.pack('<I', 4 + len(phys_body)) + b'phys' + phys_body
    if len(phys_chunk) % 2 != 0:
        phys_chunk += b'\x00'

    # Template do objeto Samplitude
    obj_template = bytearray(data[25386 : 25386 + 8 + 2500])

    def make_obj(file_idx, start_sec, length_sec, name):
        obj = bytearray(obj_template)
        pos = obj.find(b'objc')
        payload = pos + 8
        length_samples = int(length_sec * sample_rate)
        start_samples = int(start_sec * sample_rate)
        end_samples = start_samples + length_samples
        
        struct.pack_into('<I', obj, payload + 0, file_idx)
        struct.pack_into('<I', obj, payload + 12, length_samples)
        struct.pack_into('<I', obj, payload + 16, start_samples)
        struct.pack_into('<I', obj, payload + 20, 0)
        struct.pack_into('<I', obj, payload + 24, end_samples)
        struct.pack_into('<I', obj, payload + 28, 0)
        struct.pack_into('<I', obj, payload + 32, length_samples)
        
        name_bytes = name.encode('latin1', errors='replace')[:255] + b'\x00'
        obj[payload + 164 : payload + 164 + len(name_bytes)] = name_bytes
        return bytes(obj)

    music_obj = make_obj(0, 0.0, music_dur, os.path.basename(music_path))
    carimbo_objs = []
    for st in solo_timestamps:
        carimbo_objs.append(make_obj(1, st, carimbo_dur, os.path.basename(carimbo_path)))

    all_objs = music_obj + b"".join(carimbo_objs)
    proj_chunk = b'LIST' + struct.pack('<I', 4 + len(all_objs)) + b'proj' + all_objs
    if len(proj_chunk) % 2 != 0:
        proj_chunk += b'\x00'

    # Preserva cabeçalho de tracks e configurações
    track_end = 25386
    new_vip = data[:12] + phys_chunk + data[844:track_end] + proj_chunk

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, 'wb') as f:
        f.write(new_vip)

    return os.path.abspath(output_path)
