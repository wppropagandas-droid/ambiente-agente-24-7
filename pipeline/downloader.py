import os
import re
import yt_dlp
from config import FFMPEG_PATH

def sanitize_name(text):
    if not text:
        return "DESCONHECIDO"
    # Remove emojis, caracteres inválidos em sistemas de arquivos
    cleaned = re.sub(r'[\\/*?:"<>|]', "", text)
    # Remove marcas promocionais comuns em títulos de YouTube
    noise_patterns = [
        r'\(CLIPE\s+OFICIAL\)', r'\[CLIPE\s+OFICIAL\]',
        r'\(V[IÍ]DEO\s+OFICIAL\)', r'\[V[IÍ]DEO\s+OFICIAL\]',
        r'\(AUDIO\s+OFICIAL\)', r'\[AUDIO\s+OFICIAL\]',
        r'\(ÁUDIO\s+OFICIAL\)', r'\[ÁUDIO\s+OFICIAL\]',
        r'\(LYRIC\s+VIDEO\)', r'\[LYRIC\s+VIDEO\]',
        r'\(AO\s+VIVO\)', r'\[AO\s+VIVO\]',
        r'\(OFICIAL\)', r'\[OFICIAL\]',
        r'HD', r'4K', r'1080P'
    ]
    for np in noise_patterns:
        cleaned = re.sub(np, '', cleaned, flags=re.IGNORECASE)
    return " ".join(cleaned.split()).upper().strip()

def download_audio_track(query_or_url, download_dir):
    os.makedirs(download_dir, exist_ok=True)

    is_url = query_or_url.startswith('http://') or query_or_url.startswith('https://')
    search_target = query_or_url if is_url else f"ytsearch1:{query_or_url} audio oficial"

    outtmpl = os.path.join(download_dir, '%(id)s.%(ext)s')

    ffmpeg_dir = os.path.dirname(FFMPEG_PATH) if os.path.isabs(FFMPEG_PATH) else None

    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': outtmpl,
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '320',
        }],
    }

    if ffmpeg_dir:
        ydl_opts['ffmpeg_location'] = ffmpeg_dir

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(search_target, download=True)
        if 'entries' in info and info['entries']:
            entry = info['entries'][0]
        else:
            entry = info

        video_id = entry.get('id')
        raw_title = entry.get('title', 'FAIXA')
        raw_artist = entry.get('artist') or entry.get('creator') or entry.get('uploader', 'ARTISTA')

        mp3_path = os.path.join(download_dir, f"{video_id}.mp3")
        if not os.path.exists(mp3_path):
            candidates = [f for f in os.listdir(download_dir) if f.startswith(video_id) and f.endswith('.mp3')]
            if candidates:
                mp3_path = os.path.join(download_dir, candidates[0])

        # Se for pesquisa por nome, parseia 'Artista - Titulo'
        if ' - ' in raw_title:
            parts = raw_title.split(' - ', 1)
            parsed_artist = sanitize_name(parts[0])
            parsed_title = sanitize_name(parts[1])
        else:
            parsed_artist = sanitize_name(raw_artist)
            parsed_title = sanitize_name(raw_title)

        return {
            'file_path': os.path.abspath(mp3_path),
            'artist': parsed_artist,
            'title': parsed_title,
            'raw_title': raw_title,
            'duration': entry.get('duration', 0)
        }
