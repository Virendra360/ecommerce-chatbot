from pathlib import Path
import pickle

from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from langchain_google_community import GmailToolkit


SCOPES = ["https://www.googleapis.com/auth/gmail.send"]

_service = None


def get_gmail_service():
    root = Path(__file__).resolve().parents[2]

    credentials_path = root / "credentials.json"
    token_path = root / "token.pickle"

    creds = None

    if token_path.exists():
        with open(token_path, "rb") as token:
            creds = pickle.load(token)

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())

    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(
            credentials_path,
            SCOPES
        )
        creds = flow.run_local_server(port=0)

        with open(token_path, "wb") as token:
            pickle.dump(creds, token)

    return build(
        "gmail",
        "v1",
        credentials=creds
    )


def initialize_gmail() -> bool:
    global _service

    if _service is not None:
        return True

    try:
        _service = get_gmail_service()
        return True
    except Exception as e:
        print(f"Gmail initialization failed: {e}")
        return False


def get_gmail_tools():
    if not initialize_gmail():
        return []

    toolkit = GmailToolkit(
        api_resource=_service
    )

    return toolkit.get_tools()


def is_gmail_available():
    return _service is not None