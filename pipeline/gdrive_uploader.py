import os
import sys
import json
import zipfile
from datetime import datetime

class GoogleDriveUploader:
    """
    Conector de Entrega para Google Drive.
    Suporta upload via Service Account JSON (recomendado para nuvem / GitHub Actions)
    e empacotamento zip de segurança para entrega direta via Telegram.
    """
    def __init__(self, credentials_path=None):
        self.credentials_path = credentials_path or os.environ.get('GOOGLE_DRIVE_CREDENTIALS')

    def upload_batch(self, files_list, batch_name=None, output_zip_dir=None):
        if not batch_name:
            batch_name = f"WP Músicas - Lote {datetime.now().strftime('%d-%m-%Y %Hh%M')}"

        result = {
            'batch_name': batch_name,
            'total_files': len(files_list),
            'drive_folder_url': None,
            'zip_package_path': None,
            'status': 'pending'
        }

        # 1. Sempre cria um pacote ZIP seguro com todos os MP3s e VIPs
        if output_zip_dir:
            os.makedirs(output_zip_dir, exist_ok=True)
            zip_filename = f"{batch_name.replace(':', '-').replace(' ', '_')}.zip"
            zip_path = os.path.join(output_zip_dir, zip_filename)
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for file_path in files_list:
                    if os.path.exists(file_path):
                        zipf.write(file_path, arcname=os.path.basename(file_path))
            result['zip_package_path'] = os.path.abspath(zip_path)

        # 2. Upload para o Google Drive se houver credenciais configuradas
        if self.credentials_path and os.path.exists(self.credentials_path):
            try:
                from google.oauth2 import service_account
                from googleapiclient.discovery import build
                from googleapiclient.http import MediaFileUpload

                SCOPES = ['https://www.googleapis.com/auth/drive']
                creds = service_account.Credentials.from_service_account_file(self.credentials_path, scopes=SCOPES)
                service = build('drive', 'v3', credentials=creds)

                # Cria pasta do lote no Drive
                folder_metadata = {
                    'name': batch_name,
                    'mimeType': 'application/vnd.google-apps.folder'
                }
                folder = service.files().create(body=folder_metadata, fields='id, webViewLink').execute()
                folder_id = folder.get('id')

                # Compartilha com 'anyone with the link' para acesso imediato
                permission = {
                    'type': 'anyone',
                    'role': 'reader'
                }
                service.permissions().create(fileId=folder_id, body=permission).execute()

                # Upload dos arquivos do lote
                for file_path in files_list:
                    if not os.path.exists(file_path):
                        continue
                    file_metadata = {
                        'name': os.path.basename(file_path),
                        'parents': [folder_id]
                    }
                    media = MediaFileUpload(file_path, resumable=True)
                    service.files().create(body=file_metadata, media_body=media, fields='id').execute()

                folder_link = f"https://drive.google.com/drive/folders/{folder_id}"
                result['drive_folder_url'] = folder_link
                result['status'] = 'uploaded_to_drive'
                return result
            except Exception as e:
                result['error'] = f"Falha no upload do Google Drive: {str(e)}"
                result['status'] = 'drive_failed_zip_fallback'
                return result

        result['status'] = 'ready_for_drive_config'
        return result
