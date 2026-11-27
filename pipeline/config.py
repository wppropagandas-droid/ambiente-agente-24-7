import os
import sys

def get_base_dir():
    if getattr(sys, 'frozen', False):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))

BASE_DIR = get_base_dir()
ASSETS_DIR = os.path.join(BASE_DIR, 'assets')

# Windows flag to prevent flashing CMD windows
CREATE_NO_WINDOW = 0x08000000 if sys.platform == 'win32' else 0

def find_ffmpeg():
    # 1. Environment / system PATH
    system_candidates = ['ffmpeg', 'ffmpeg.exe']
    # 2. Local workspace paths
    local_candidates = [
        os.path.join(BASE_DIR, 'ffmpeg.exe'),
        r'E:\WP SISTEMAS\BAIXADOR DE MÚSICAS WP\ffmpeg.exe',
        r'C:\Users\PRODUCAO\AppData\Local\Programs\Fusion Audio Master\resources\ffmpeg\ffmpeg.exe',
    ]
    for c in local_candidates:
        if os.path.exists(c):
            return os.path.abspath(c)
    return 'ffmpeg'

FFMPEG_PATH = find_ffmpeg()

# Asset defaults (checks workspace paths first, falls back to bundled assets)
def resolve_asset(primary_path, fallback_filename):
    if os.path.exists(primary_path):
        return os.path.abspath(primary_path)
    fallback = os.path.join(ASSETS_DIR, fallback_filename)
    if os.path.exists(fallback):
        return os.path.abspath(fallback)
    return primary_path

DEFAULT_CARIMBO_CONFIANCA = resolve_asset(
    r'E:\CARIMBOS\01 NTV Confiança 1 acapella.mp3',
    '01 NTV Confiança 1 acapella.mp3'
)

DEFAULT_CARIMBO_CURTO = resolve_asset(
    r'E:\CARIMBOS\PARA MÚSICA\CARIMBO CURTO 01.mp3',
    'CARIMBO CURTO 01.mp3'
)

DEFAULT_VIP_TEMPLATE = resolve_asset(
    r'E:\MODELOS\01.vip',
    '01.vip'
)

# Audio standards
DEFAULT_BITRATE = '320k'
DEFAULT_SAMPLE_RATE = 44100
DEFAULT_LIMITER_CEILING = 0.98   # -0.17 dBFS True Peak headroom
TARGET_LUFS = -14.0              # Broadcast & streaming standard
DEFAULT_FADEOUT_SEC = 3.0
DEFAULT_DUCKING_DB = 0.0         # 100% Uniform (no ducking) unless user requests
