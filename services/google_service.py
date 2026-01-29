import os
import json
import logging
from typing import List, Dict, Optional
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Scopes required for the application
SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/youtube.readonly',
    'https://www.googleapis.com/auth/drive.metadata.readonly',
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
            creds = Credentials.from_authorized_user_file(token_path, SCOPES)
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                    # Save refreshed token
                    with open(token_path, 'w') as token:
                        token.write(creds.to_json())
                except Exception as e:
                     logging.error(f"Failed to refresh token: {e}")
                     return None
            return creds
        return None

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
                    
                    email_data.append({
                        "id": msg['id'],
                        "sender": headers.get('From', 'Unknown'),
                        "subject": headers.get('Subject', '(No Subject)'),
                        "preview": snippet,
                        "time": "" # Date parsing is complex, skipping for brevity or add if needed
                    })
            return email_data
        except Exception as e:
            logging.error(f"Gmail API error: {e}")
            return []

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

google_service = GoogleService()
