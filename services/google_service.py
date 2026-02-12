import os
import json
import logging
from typing import List, Dict, Optional
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload
import io

# Scopes required for the application
SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/youtube.readonly',
    'https://www.googleapis.com/auth/drive.metadata.readonly',
    'https://www.googleapis.com/auth/drive.file',
    'https://www.googleapis.com/auth/userinfo.email',
    'https://www.googleapis.com/auth/userinfo.profile',
    'openid'
]

TOKEN_DIR = 'data/google_tokens'
ACCOUNTS_FILE = 'data/google_accounts.json'

class GoogleService:
    def __init__(self):
        self.accounts: List[Dict[str, str]] = []
        self.current_account_id: Optional[str] = None
        
        # Ensure directories exist
        os.makedirs(TOKEN_DIR, exist_ok=True)
        
        # Load persisted accounts
        self.load_accounts()
        
        if self.accounts:
            self.current_account_id = self.accounts[0]['id']

    def load_accounts(self):
        if os.path.exists(ACCOUNTS_FILE):
            try:
                with open(ACCOUNTS_FILE, 'r') as f:
                    self.accounts = json.load(f)
            except Exception as e:
                logging.error(f"Failed to load accounts: {e}")
                self.accounts = []

    def save_accounts(self):
        with open(ACCOUNTS_FILE, 'w') as f:
            json.dump(self.accounts, f, indent=4)

    def get_accounts(self) -> List[Dict[str, str]]:
        return self.accounts

    def get_current_account(self) -> Optional[Dict[str, str]]:
        if not self.current_account_id:
            return None
        for acc in self.accounts:
            if acc["id"] == self.current_account_id:
                return acc
        return None

    def set_current_account(self, account_id: str):
        if any(acc["id"] == account_id for acc in self.accounts):
            self.current_account_id = account_id

    def add_account(self):
        """
        Initiates the OAuth flow to add a new account.
        Returns the new account dict or None if failed.
        """
        creds = None
        # Always start a new flow for add_account
        try:
            flow = InstalledAppFlow.from_client_secrets_file(
                'client_secret.json', SCOPES)
            creds = flow.run_local_server(port=0)
        except Exception as e:
            logging.error(f"OAuth flow failed: {e}")
            return None

        # Get user info to identify the account
        try:
            user_info_service = build('oauth2', 'v2', credentials=creds)
            user_info = user_info_service.userinfo().get().execute()
            
            email = user_info.get('email')
            name = user_info.get('name', email)
            picture = user_info.get('picture', 'person')
            user_id = user_info.get('id')
            
            # Save credentials
            token_path = os.path.join(TOKEN_DIR, f'token_{user_id}.json')
            with open(token_path, 'w') as token:
                token.write(creds.to_json())
            
            # Update accounts list
            new_account = {
                "id": user_id,
                "name": name,
                "email": email,
                "avatar": picture # This will be a URL now, handled by UI
            }
            
            # Check if exists, update if so
            existing = False
            for i, acc in enumerate(self.accounts):
                if acc['id'] == user_id:
                    self.accounts[i] = new_account
                    existing = True
                    break
            
            if not existing:
                self.accounts.append(new_account)
            
            self.save_accounts()
            self.current_account_id = user_id
            return new_account
            
        except Exception as e:
            logging.error(f"Failed to fetch user info or save token: {e}")
            return None

    def _get_credentials(self, account_id: str) -> Optional[Credentials]:
        token_path = os.path.join(TOKEN_DIR, f'token_{account_id}.json')
        if os.path.exists(token_path):
            try:
                # Use a copy of SCOPES to avoid modification if that were possible
                creds = Credentials.from_authorized_user_file(token_path, SCOPES)
            except ValueError:
                # Can happen if scopes mismatch in some versions or file is corrupt
                logging.error("Failed to load credentials from file - mismatched scopes")
                return None
                
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                    # Save refreshed token
                    with open(token_path, 'w') as token:
                        token.write(creds.to_json())
                except Exception as e:
                     # Check for invalid_scope error
                     error_str = str(e)
                     if "invalid_scope" in error_str:
                         logging.error(f"Scope mismatch: {e}. Re-authentication required.")
                         # Could delete the token file here to force re-auth, but just returning None is safer for now.
                         # os.remove(token_path) 
                     else:
                         logging.error(f"Failed to refresh token: {e}")
                     return None
            return creds
        return None

    def is_account_valid(self, account_id: str = None) -> bool:
        if account_id is None:
            account_id = self.current_account_id
        if not account_id:
            return False
        return self._get_credentials(account_id) is not None

    def get_gmail_data(self) -> List[Dict]:
        if not self.current_account_id:
            return []
        
        creds = self._get_credentials(self.current_account_id)
        if not creds:
            return []

        try:
            service = build('gmail', 'v1', credentials=creds)
            results = service.users().messages().list(userId='me', maxResults=10).execute()
            messages = results.get('messages', [])

            email_data = []
            if messages:
                # Batch get details would be better, but loop for simplicity for now
                for msg in messages:
                    txt = service.users().messages().get(userId='me', id=msg['id'], format='minimal').execute()
                    snippet = txt.get('snippet', '')
                    headers = {} # Minimal format doesn't give headers always, use 'metadata' or 'full' for headers.
                    
                    # Re-fetch with metadata for headers
                    meta = service.users().messages().get(userId='me', id=msg['id'], format='metadata').execute()
                    headers_list = meta.get('payload', {}).get('headers', [])
                    headers = {h['name']: h['value'] for h in headers_list}
                    
                    labelIds = meta.get('labelIds', [])
                    is_read = 'UNREAD' not in labelIds

                    import email.utils
                    from datetime import datetime, date
                    
                    date_str = headers.get('Date', '')
                    formatted_time = ''
                    if date_str:
                        try:
                            dt = email.utils.parsedate_to_datetime(date_str)
                            # Convert to local if possible, or naive. parsedate_to_datetime returns aware usually.
                            
                            # Simple formatting logic
                            now = datetime.now(dt.tzinfo)
                            if dt.date() == now.date():
                                formatted_time = dt.strftime('%H:%M')
                            else:
                                formatted_time = dt.strftime('%b %d')
                        except:
                            formatted_time = date_str[:10] # Fallback

                    email_data.append({
                        "id": msg['id'],
                        "sender": headers.get('From', 'Unknown'),
                        "subject": headers.get('Subject', '(No Subject)'),
                        "preview": snippet,
                        "time": formatted_time,
                        "is_read": is_read
                    })
            return email_data
        except Exception as e:
            logging.error(f"Gmail API error: {e}")
            return []

    def get_email_details(self, message_id: str) -> Optional[Dict]:
        if not self.current_account_id:
            return None
        
        creds = self._get_credentials(self.current_account_id)
        if not creds:
            return None

        try:
            service = build('gmail', 'v1', credentials=creds)
            msg = service.users().messages().get(userId='me', id=message_id, format='full').execute()
            
            payload = msg.get('payload', {})
            headers_list = payload.get('headers', [])
            headers = {h['name']: h['value'] for h in headers_list}
            
            body = "No text content found."
            is_html = False
            
            def get_body(parts):
                html_body = None
                text_body = None
                
                for part in parts:
                    mime = part.get('mimeType')
                    data = part.get('body', {}).get('data', '')
                    
                    if mime == 'text/html' and data:
                         import base64
                         html_body = base64.urlsafe_b64decode(data).decode()
                    elif mime == 'text/plain' and data:
                         import base64
                         text_body = base64.urlsafe_b64decode(data).decode()
                    
                    if 'parts' in part:
                         # Recursive search
                         found_body, found_is_html = get_body(part['parts'])
                         if found_body:
                             if found_is_html: return found_body, True
                             # If we found text deep down, keep it but keep looking for html at this level or others
                             if text_body is None: text_body = found_body

                if html_body: return html_body, True
                if text_body: return text_body, False
                return None, False

            if 'parts' in payload:
                found_body, found_is_html = get_body(payload['parts'])
                if found_body:
                    body = found_body
                    is_html = found_is_html
            else:
                # Single part message
                data = payload.get('body', {}).get('data', '')
                if data:
                    import base64
                    body = base64.urlsafe_b64decode(data).decode()
                    if payload.get('mimeType') == 'text/html':
                        is_html = True

            return {
                "id": msg['id'],
                "sender": headers.get('From', 'Unknown'),
                "subject": headers.get('Subject', '(No Subject)'),
                "body": body,
                "is_html": is_html,
                "date": headers.get('Date', '')
            }
        except Exception as e:
            logging.error(f"Gmail detail error: {e}")
            return None

    def get_youtube_data(self) -> List[Dict]:
        if not self.current_account_id:
            return []

        creds = self._get_credentials(self.current_account_id)
        if not creds:
            return []

        try:
            service = build('youtube', 'v3', credentials=creds)
            # Get latest activities (uploads from subscriptions)
            # This requires complex logic. Simple "popular" or "my liked" is easier.
            # Let's try "activities" - list (home feed equivalent is hard via API, best is subscriptions)
            
            # Let's get 'most popular' videos for now as a placeholder for "new subjects" 
            # OR get 'subscriptions' and then get their latest video. 
            # Safest 'personal' data is 'activities'
            request = service.activities().list(part='snippet,contentDetails', mine=True, maxResults=8)
            response = request.execute()
            
            videos = []
            for item in response.get('items', []):
                snippet = item['snippet']
                # Limit to uploads
                if item['snippet']['type'] == 'upload':
                    videos.append({
                        "id": item['id'],
                        "channel": snippet['channelTitle'],
                        "title": snippet['title'],
                        "views": "New", # Views requires another call
                        "color": "bg-red-500", # Placeholder
                        "thumbnail": snippet['thumbnails']['default']['url']
                    })
            return videos
        except Exception as e:
            logging.error(f"YouTube API error: {e}")
            return []

    def get_drive_data(self) -> List[Dict]:
        if not self.current_account_id:
            return []

        creds = self._get_credentials(self.current_account_id)
        if not creds:
            return []

        try:
            service = build('drive', 'v3', credentials=creds)
            results = service.files().list(
                pageSize=12, fields="nextPageToken, files(id, name, mimeType, modifiedTime, iconLink)").execute()
            items = results.get('files', [])
            
            files = []
            for item in items:
                # Map mimeType to icon/color roughly
                icon = "insert_drive_file"
                color = "text-gray-400"
                if 'folder' in item['mimeType']:
                    icon = "folder"
                    color = "text-yellow-400"
                elif 'image' in item['mimeType']:
                    icon = "image"
                    color = "text-red-400"
                
                files.append({
                    "id": item['id'],
                    "name": item['name'],
                    "icon": icon,
                    "color": color,
                    "modified": item['modifiedTime'][:10] # Simple date
                })
            return files
        except Exception as e:
            logging.error(f"Drive API error: {e}")
            return []

    def _find_drive_file_id(self, name: str) -> Optional[str]:
        if not self.current_account_id: return None
        creds = self._get_credentials(self.current_account_id)
        if not creds: return None
        try:
            service = build('drive', 'v3', credentials=creds)
            query = f"name = '{name}' and trashed = false"
            results = service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
            files = results.get('files', [])
            if files:
                return files[0]['id']
            return None
        except Exception as e:
            logging.error(f"Drive find error: {e}")
            return None

    def read_drive_file(self, name: str) -> Optional[str]:
        file_id = self._find_drive_file_id(name)
        if not file_id: return None
        
        creds = self._get_credentials(self.current_account_id)
        if not creds: return None
        
        try:
            service = build('drive', 'v3', credentials=creds)
            request = service.files().get_media(fileId=file_id)
            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while done is False:
                status, done = downloader.next_chunk()
            return fh.getvalue().decode('utf-8')
        except Exception as e:
            logging.error(f"Drive read error: {e}")
            return None

    def save_drive_file(self, name: str, content: str) -> bool:
        if not self.current_account_id: return False
        creds = self._get_credentials(self.current_account_id)
        if not creds: return False
        
        try:
            service = build('drive', 'v3', credentials=creds)
            file_id = self._find_drive_file_id(name)
            
            fh = io.BytesIO(content.encode('utf-8'))
            media = MediaIoBaseUpload(fh, mimetype='application/json', resumable=True)
            
            if file_id:
                # Update
                try:
                    service.files().update(fileId=file_id, media_body=media).execute()
                except HttpError as e:
                     if e.resp.status == 404:
                         # File not found (maybe deleted externally but id cached? unlikely here as we search by name freshly)
                         # Search again or create?
                         # Just create new if update fails?
                         # For now log and return False
                         logging.error(f"Update failed: {e}")
                         return False
                     raise e
            else:
                # Create
                file_metadata = {'name': name}
                service.files().create(body=file_metadata, media_body=media, fields='id').execute()
            return True
        except Exception as e:
            logging.error(f"Drive save error: {e}")
            return False

google_service = GoogleService()
