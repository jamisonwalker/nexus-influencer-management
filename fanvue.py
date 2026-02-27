import secrets
import hashlib
import base64
import urllib.parse
import requests
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class FanvueOAuth:
    """
    Fanvue OAuth 2.0 with PKCE integration
    """
    
    # Fanvue API endpoints
    AUTH_URL = "https://auth.fanvue.com/oauth2/auth"
    TOKEN_URL = "https://auth.fanvue.com/oauth2/token"
    API_BASE_URL = "https://api.fanvue.com"
    
    def __init__(self, client_id=None, client_secret=None, redirect_uri=None):
        """
        Initialize the Fanvue OAuth client
        
        Args:
            client_id (str): Fanvue OAuth client ID
            client_secret (str): Fanvue OAuth client secret
            redirect_uri (str): Redirect URI for your application
        """
        self.client_id = client_id or os.getenv("FANVUE_CLIENT_ID")
        self.client_secret = client_secret or os.getenv("FANVUE_CLIENT_SECRET")
        self.redirect_uri = redirect_uri or os.getenv("FANVUE_REDIRECT_URI")
        
        # Don't raise an error if credentials are missing - handle it when methods are called
        # This allows the module to be imported even if environment variables aren't loaded yet
        self.initialized = all([self.client_id, self.redirect_uri])
    
    def generate_pkce_parameters(self):
        """
        Generate PKCE parameters (code verifier and code challenge)
        
        Returns:
            dict: Contains code_verifier and code_challenge
        """
        # Generate code verifier
        code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode('utf-8').rstrip('=')
        
        # Generate code challenge from code verifier
        code_challenge = base64.urlsafe_b64encode(
            hashlib.sha256(code_verifier.encode('utf-8')).digest()
        ).decode('utf-8').rstrip('=')
        
        return {
            "code_verifier": code_verifier,
            "code_challenge": code_challenge
        }
    
    def get_authorization_url(self, code_challenge, state=None, scope=None):
        """
        Get the Fanvue authorization URL
        
        Args:
            code_challenge (str): PKCE code challenge
            state (str): Optional state parameter for CSRF protection
            scope (str): Optional scope parameter (default: openid offline_access offline read:self)
            
        Returns:
            str: Authorization URL
        """
        if not self.initialized:
            raise ValueError("Client ID and redirect URI are required")
        
        params = {
            'client_id': self.client_id,
            'redirect_uri': self.redirect_uri,
            'response_type': 'code',
            'scope': scope or 'openid offline_access offline read:self',
            'state': state or secrets.token_hex(32),
            'code_challenge': code_challenge,
            'code_challenge_method': 'S256'
        }
        
        return f"{self.AUTH_URL}?{urllib.parse.urlencode(params)}"
    
    def exchange_code_for_tokens(self, code, code_verifier):
        """
        Exchange authorization code for access token and refresh token
        
        Args:
            code (str): Authorization code from Fanvue
            code_verifier (str): PKCE code verifier used during authorization
            
        Returns:
            dict: Contains access_token, refresh_token, expires_in, etc.
        """
        if not self.initialized:
            raise ValueError("Client ID and redirect URI are required")
            
        data = {
            'grant_type': 'authorization_code',
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'code': code,
            'redirect_uri': self.redirect_uri,
            'code_verifier': code_verifier,
        }
        
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        
        response = requests.post(self.TOKEN_URL, data=data, headers=headers)
        response.raise_for_status()
        
        return response.json()
    
    def refresh_access_token(self, refresh_token):
        """
        Refresh access token using refresh token
        
        Args:
            refresh_token (str): Refresh token from previous token exchange
            
        Returns:
            dict: Contains new access_token, refresh_token, expires_in, etc.
        """
        if not self.initialized:
            raise ValueError("Client ID and redirect URI are required")
            
        data = {
            'grant_type': 'refresh_token',
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'refresh_token': refresh_token,
        }
        
        response = requests.post(self.TOKEN_URL, data=data)
        response.raise_for_status()
        
        return response.json()
    
    def get_user_profile(self, access_token):
        """
        Get authenticated user's profile information
        
        Args:
            access_token (str): Access token from token exchange
            
        Returns:
            dict: User profile data
        """
        headers = {
            'Authorization': f'Bearer {access_token}',
            'X-Fanvue-API-Version': '2025-06-26'
        }
        response = requests.get(f"{self.API_BASE_URL}/users/me", headers=headers)
        response.raise_for_status()
        
        return response.json()
    
    def get_chats(self, access_token):
        """
        Get list of chats for authenticated user
        
        Args:
            access_token (str): Access token from token exchange
            
        Returns:
            dict: List of chats
        """
        headers = {
            'Authorization': f'Bearer {access_token}',
            'X-Fanvue-API-Version': '2025-06-26'
        }
        response = requests.get(f"{self.API_BASE_URL}/chats", headers=headers)
        response.raise_for_status()
        
        return response.json()
    
    def get_messages(self, access_token, user_uuid, page=1, size=15, mark_as_read=True):
        """
        Get messages from a chat
        
        Args:
            access_token (str): Access token from token exchange
            user_uuid (str): UUID of the user to get messages with
            page (int): Page number (default: 1)
            size (int): Number of messages per page (default: 15, max: 50)
            mark_as_read (bool): Whether to mark messages as read (default: True)
            
        Returns:
            dict: Paginated list of messages
        """
        headers = {
            'Authorization': f'Bearer {access_token}',
            'X-Fanvue-API-Version': '2025-06-26'
        }
        params = {
            'page': page,
            'size': min(size, 50),
            'markAsRead': str(mark_as_read).lower()
        }
        response = requests.get(
            f"{self.API_BASE_URL}/chats/{user_uuid}/messages",
            headers=headers,
            params=params
        )
        response.raise_for_status()
        
        return response.json()
    
    def send_message(self, access_token, user_uuid, text, media_uuids=None, price=None, template_uuid=None):
        """
        Send a message to a user in an existing chat conversation
        
        Args:
            access_token (str): Access token from token exchange
            user_uuid (str): UUID of the user to send message to
            text (str): Text message content
            media_uuids (list): Optional list of media UUIDs to attach
            price (float): Optional price for pay-to-view content
            template_uuid (str): Optional template UUID to use
            
        Returns:
            dict: Response from Fanvue API
        """
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json',
            'X-Fanvue-API-Version': '2025-06-26'
        }
        data = {
            'text': text
        }
        if media_uuids:
            data['mediaUuids'] = media_uuids
        if price is not None:
            data['price'] = price
        if template_uuid:
            data['templateUuid'] = template_uuid
            
        response = requests.post(
            f"{self.API_BASE_URL}/chats/{user_uuid}/message",
            headers=headers,
            json=data
        )
        response.raise_for_status()
        
        return response.json()
    
    def make_authenticated_request(self, endpoint, access_token, method='GET', data=None, params=None):
        """
        Make an authenticated API request to Fanvue
        
        Args:
            endpoint (str): API endpoint (e.g., /users/me)
            access_token (str): Access token from token exchange
            method (str): HTTP method (GET, POST, PUT, DELETE, etc.)
            data (dict): Optional request body data
            params (dict): Optional query parameters
            
        Returns:
            dict: Response data from Fanvue API
        """
        url = f"{self.API_BASE_URL}{endpoint}"
        headers = {
            'Authorization': f'Bearer {access_token}',
            'X-Fanvue-API-Version': '2025-06-26'
        }
        
        response = requests.request(
            method,
            url,
            headers=headers,
            json=data,
            params=params
        )
        
        response.raise_for_status()
        return response.json()

# Example usage
if __name__ == "__main__":
    try:
        # Initialize OAuth client
        oauth = FanvueOAuth()
        
        # Generate PKCE parameters
        pkce = oauth.generate_pkce_parameters()
        print("Generated PKCE parameters:")
        print(f"Code Verifier: {pkce['code_verifier']}")
        print(f"Code Challenge: {pkce['code_challenge']}")
        
        # Get authorization URL
        auth_url = oauth.get_authorization_url(pkce['code_challenge'])
        print("\nAuthorization URL:")
        print(auth_url)
        
        # In a real application, you would redirect the user to auth_url
        # and handle the callback with the authorization code
        
    except Exception as e:
        print(f"Error: {e}")
