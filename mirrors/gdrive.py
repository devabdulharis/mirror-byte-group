import os
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import pickle
from config import Config
from utils.helpers import format_size
from utils.mirror_progress import MirrorProgressTracker

SCOPES = ['https://www.googleapis.com/auth/drive.file']

class GoogleDriveMirror:
    def __init__(self):
        self.service = None
        self.creds = None
        self._authenticate()

    def _authenticate(self):
        """Authenticate dengan Google Drive"""
        token_path = 'token.pickle'

        if os.path.exists(token_path):
            with open(token_path, 'rb') as token:
                self.creds = pickle.load(token)

        if not self.creds or not self.creds.valid:
            if self.creds and self.creds.expired and self.creds.refresh_token:
                self.creds.refresh(Request())
            elif os.path.exists(Config.GDRIVE_CREDENTIALS_JSON):
                flow = InstalledAppFlow.from_client_secrets_file(
                    Config.GDRIVE_CREDENTIALS_JSON, SCOPES
                )
                self.creds = flow.run_local_server(port=0)
            else:
                return

            with open(token_path, 'wb') as token:
                pickle.dump(self.creds, token)

        self.service = build('drive', 'v3', credentials=self.creds)

    def is_available(self) -> bool:
        return self.service is not None

    async def upload(self, file_path: str, folder_id: str = None,
                      progress_tracker: MirrorProgressTracker = None) -> dict:
        """Upload file ke Google Drive"""
        import asyncio

        if not self.is_available():
            return {
                'success': False,
                'error': 'Google Drive tidak dikonfigurasi',
                'platform': 'gdrive'
            }

        filename = os.path.basename(file_path)
        folder = folder_id or Config.GDRIVE_FOLDER_ID
        file_size = os.path.getsize(file_path)

        file_metadata = {'name': filename}
        if folder:
            file_metadata['parents'] = [folder]

        media = MediaFileUpload(file_path, resumable=True, chunksize=10*1024*1024)

        def do_upload():
            request = self.service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id,name,webViewLink,size'
            )

            response = None
            while response is None:
                status, response = request.next_chunk()

            # Set public sharing
            self.service.permissions().create(
                fileId=response['id'],
                body={'type': 'anyone', 'role': 'reader'}
            ).execute()

            return response

        try:
            if progress_tracker:
                # Update progress via status object from MediaFileUpload
                # Wrap do_upload to track progress
                request = self.service.files().create(
                    body=file_metadata,
                    media_body=media,
                    fields='id,name,webViewLink,size'
                )
                uploaded = 0
                response = None
                while response is None:
                    status, response = request.next_chunk()
                    if status:
                        uploaded = int(status.progress() * file_size) if status.progress() else uploaded
                        await progress_tracker.update(uploaded, file_size, filename)
            else:
                result = await asyncio.to_thread(do_upload)
                return {
                    'success': True,
                    'platform': 'gdrive',
                    'file_id': result['id'],
                    'link': result.get('webViewLink', ''),
                    'name': result.get('name', filename)
                }

            if response:
                await progress_tracker.complete(filename)
                return {
                    'success': True,
                    'platform': 'gdrive',
                    'file_id': response['id'],
                    'link': response.get('webViewLink', ''),
                    'name': response.get('name', filename)
                }
            return {'success': False, 'error': 'Upload incomplete', 'platform': 'gdrive'}

        except Exception as e:
            if progress_tracker:
                await progress_tracker.error(str(e), filename)
            return {
                'success': False,
                'error': str(e),
                'platform': 'gdrive'
            }
