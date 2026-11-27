import os
import sys
import json
import argparse
import time
from datetime import datetime

from config import (
    DEFAULT_CARIMBO_CONFIANCA,
    DEFAULT_CARIMBO_CURTO,
    DEFAULT_VIP_TEMPLATE,
    DEFAULT_LIMITER_CEILING,
    DEFAULT_DUCKING_DB,
    DEFAULT_BITRATE,
    FFMPEG_PATH
)
from downloader import download_audio_track, sanitize_name
from audio_master import analyze_surgical_cuts, render_mastered_audio, get_audio_info
from solo_detector import SmartSoloDetector
from vip_engine import create_samplitude_vip
from quality_gate import QualityGateAuditor
from gdrive_uploader import GoogleDriveUploader

class WpAudioPipeline:
    def __init__(
        self,
        jingle_type='confianca',
        custom_jingle_path=None,
        vip_template=DEFAULT_VIP_TEMPLATE,
        ducking_db=DEFAULT_DUCKING_DB,
        output_dir='./saida_processada'
    ):
        if custom_jingle_path and os.path.exists(custom_jingle_path):
            self.carimbo_path = os.path.abspath(custom_jingle_path)
        elif jingle_type == 'curto':
            self.carimbo_path = DEFAULT_CARIMBO_CURTO
        else:
            self.carimbo_path = DEFAULT_CARIMBO_CONFIANCA

        self.vip_template = vip_template
        self.ducking_db = ducking_db
        self.output_dir = os.path.abspath(output_dir)
        self.cache_dir = os.path.join(self.output_dir, '.cache')
        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(self.cache_dir, exist_ok=True)

        self.detector = SmartSoloDetector()
        self.auditor = QualityGateAuditor()
        self.uploader = GoogleDriveUploader()

    def process_batch(self, songs_input, spots=None, count=1):
        if not spots:
            if count == 1:
                spots = ['solo_meio']
            elif count == 2:
                spots = ['intro', 'solo_meio']
            elif count == 3:
                spots = ['intro', 'solo_meio', 'outro']
            else:
                spots = ['solo_meio']

        carimbo_info = get_audio_info(self.carimbo_path)
        carimbo_dur = carimbo_info['duration']

        print("=" * 65)
        print("🎵 ESTEIRA INTELIGENTE DO CARIMBADOR & BAIXADOR WP")
        print(f"📌 Carimbo: {os.path.basename(self.carimbo_path)} ({carimbo_dur:.2f}s)")
        print(f"🎯 Spots Solicitados: {', '.join(spots)} ({count}x)")
        print(f"📁 Pasta de Saída: {self.output_dir}")
        print("=" * 65)

        results = []
        approved_files = []

        total = len(songs_input)
        for idx, song_item in enumerate(songs_input):
            query = song_item if isinstance(song_item, str) else song_item.get('url') or f"{song_item.get('artist', '')} - {song_item.get('title', '')}"
            print(f"\n[{idx+1}/{total}] 🚀 Iniciando: {query}")

            track_res = {
                'query': query,
                'status': 'failed',
                'qa_score': 0,
                'files': {}
            }

            try:
                # 1. Download em alta definição (320 kbps MP3)
                print("  ⬇️ Baixando faixa e metadados...")
                dl_info = download_audio_track(query, self.cache_dir)
                raw_mp3 = dl_info['file_path']
                artist = dl_info['artist']
                title = dl_info['title']
                print(f"  ✅ Faixa identificada: {artist} - {title}")

                # 2. Análise de Cortes Cirúrgicos (Início e Fim)
                print("  ✂️ Analisando cortes cirúrgicos de silêncio e vinhetas...")
                trim_start, trim_end, orig_dur, has_promo = analyze_surgical_cuts(raw_mp3)
                print(f"  ✂️ Janela musical útil: {trim_start:.2f}s até {trim_end:.2f}s (Duração: {orig_dur:.2f}s)")

                # 3. Detecção Espectral de Solos Instrumentais
                print(f"  🔍 Mapeando solos acústicos sem colisão vocal para {spots}...")
                detected_spots = self.detector.detect_spots(
                    raw_mp3,
                    jingle_duration=carimbo_dur,
                    trim_start=trim_start,
                    trim_end=trim_end,
                    spots=spots
                )

                solo_times = [s['time'] for s in detected_spots]
                times_formatted = ", ".join([f"{s['spot_type']}: {s['time']:.2f}s" for s in detected_spots])
                print(f"  🎯 Solos localizados: {times_formatted}")

                # 4. Masterização e Aplicação Cirúrgica dos Carimbos
                clean_base = f"{artist} - {title} (CARIMBADA)"
                out_mp3 = os.path.join(self.output_dir, f"{clean_base}.mp3")
                out_vip = os.path.join(self.output_dir, f"{clean_base}.vip")

                print("  🎛️ Masterizando áudio (-14 LUFS, Limiter Ceiling 0.98, Fadeout 3s)...")
                master_res = render_mastered_audio(
                    music_path=raw_mp3,
                    carimbo_path=self.carimbo_path,
                    output_mp3_path=out_mp3,
                    solo_timestamps=solo_times,
                    trim_start=trim_start,
                    trim_end=trim_end,
                    ducking_db=self.ducking_db,
                    limiter_ceiling=DEFAULT_LIMITER_CEILING
                )

                # 5. Geração do Projeto Samplitude / Sequoia (.VIP)
                print("  💾 Gerando projeto Samplitude (.VIP)...")
                create_samplitude_vip(
                    template_path=self.vip_template,
                    output_path=out_vip,
                    music_path=out_mp3,
                    carimbo_path=self.carimbo_path,
                    solo_timestamps=master_res['relative_solos'],
                    music_dur=master_res['duration'],
                    carimbo_dur=carimbo_dur
                )

                # 6. Auditoria de Qualidade 100% (Quality Gate)
                print("  🛡️ Executando Auditoria de Qualidade 100% (Quality Gate)...")
                qa_report = self.auditor.audit_track(out_mp3, out_vip, self.carimbo_path, master_res['relative_solos'])

                track_res['status'] = 'approved' if qa_report['passed'] else 'qa_warning'
                track_res['qa_score'] = qa_report['score']
                track_res['qa_details'] = qa_report
                track_res['files'] = {
                    'mp3': out_mp3,
                    'vip': out_vip,
                    'duration': master_res['duration']
                }

                if qa_report['passed']:
                    print(f"  🏆 Quality Gate: 100% APROVADO! Score: {qa_report['score']}")
                    approved_files.extend([out_mp3, out_vip])
                else:
                    print(f"  ⚠️ Quality Gate: Advertência (Score: {qa_report['score']}) -> {qa_report['details']}")
                    # Se aprovado nos critérios críticos, ainda inclui no lote
                    if qa_report['score'] >= 80:
                        approved_files.extend([out_mp3, out_vip])

            except Exception as err:
                print(f"  ❌ Erro ao processar '{query}': {err}")
                track_res['error'] = str(err)

            results.append(track_res)

        # 7. Empacotamento e Entrega para o Google Drive
        print("\n" + "=" * 65)
        print("📦 Empacotando e despachando lote aprovado...")
        batch_name = f"WP Músicas - Lote {datetime.now().strftime('%d-%m-%Y %Hh%M')}"
        upload_res = self.uploader.upload_batch(approved_files, batch_name=batch_name, output_zip_dir=self.output_dir)

        summary = {
            'timestamp': datetime.now().isoformat(),
            'total_requested': total,
            'total_approved': len([r for r in results if r['status'] == 'approved']),
            'batch_name': batch_name,
            'drive_link': upload_res.get('drive_folder_url'),
            'zip_package': upload_res.get('zip_package_path'),
            'results': results
        }

        print(f"🎉 Processamento concluído! Aprovados: {summary['total_approved']}/{total}")
        if summary['drive_link']:
            print(f"🔗 Google Drive: {summary['drive_link']}")
        elif summary['zip_package']:
            print(f"📦 Pacote ZIP gerado: {summary['zip_package']}")
        print("=" * 65)

        return summary

def main():
    parser = argparse.ArgumentParser(description="Esteira do Carimbador & Baixador Inteligente WP")
    parser.add_argument('--songs', required=True, help="Lista de músicas em formato JSON ou arquivo .json")
    parser.add_argument('--count', type=int, default=1, help="Quantidade de carimbos (1, 2 ou 3)")
    parser.add_argument('--spots', help="Spots separados por virgula (ex: intro,solo_meio,outro)")
    parser.add_argument('--jingle', default='confianca', choices=['confianca', 'curto'], help="Tipo de carimbo")
    parser.add_argument('--ducking', type=float, default=0.0, help="Atenuação musical durante o carimbo em dB")
    parser.add_argument('--output-dir', default='./saida_processada', help="Diretório de saída")
    args = parser.parse_args()

    if os.path.exists(args.songs):
        with open(args.songs, 'r', encoding='utf-8') as f:
            songs_data = json.load(f)
    else:
        try:
            songs_data = json.loads(args.songs)
        except:
            songs_data = [s.strip() for s in args.songs.split('\n') if s.strip()]

    spots_list = [s.strip() for s in args.spots.split(',')] if args.spots else None

    pipeline = WpAudioPipeline(
        jingle_type=args.jingle,
        ducking_db=args.ducking,
        output_dir=args.output_dir
    )

    summary = pipeline.process_batch(songs_data, spots=spots_list, count=args.count)
    print("\n[RESULTADO_FINAL_JSON]")
    print(json.dumps(summary, indent=2, ensure_ascii=False))

if __name__ == '__main__':
    main()
