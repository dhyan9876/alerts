import json
import os
import time
import webbrowser
from kiteconnect import KiteConnect


def load_dotenv():
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if not os.path.exists(env_path):
        return

    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


load_dotenv()

API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
TOKEN_FILE = os.getenv("TOKEN_FILE", "kite_session.json")

if not API_KEY or not API_SECRET:
    raise RuntimeError(
        "API_KEY and API_SECRET must be set in .env or environment variables."
    )

kite = KiteConnect(api_key=API_KEY)


def save_access_token(access_token):
    data = {
        "access_token": access_token,
        "api_key": API_KEY,
        "saved_at": time.time(),
    }
    with open(TOKEN_FILE, "w", encoding="utf-8") as token_file:
        json.dump(data, token_file)


def load_saved_access_token():
    if not os.path.exists(TOKEN_FILE):
        return None
    try:
        with open(TOKEN_FILE, "r", encoding="utf-8") as token_file:
            data = json.load(token_file)
    except Exception:
        return None

    if data.get("api_key") != API_KEY:
        return None

    return data.get("access_token")


def token_is_valid(token):
    try:
        kite.set_access_token(token)
        kite.margins()
        return True
    except Exception:
        return False


def authenticate():
    saved_token = load_saved_access_token()
    if saved_token and token_is_valid(saved_token):
        print("Using saved Zerodha session token.\n")
        return saved_token

    login_url = kite.login_url()
    print("\n" + "=" * 60)
    print("👉 STEP 1: LAUNCHING AUTHENTICATION")
    print("=" * 60)
    print("Open Zerodha login page and authorize access:")
    print(f"{login_url}\n")
    webbrowser.open(login_url)

    print("=" * 60)
    print("👉 STEP 2: CAPTURE THE REQUEST TOKEN")
    print("=" * 60)
    print("After login, copy the request_token value from the redirect URL.")
    print("For example, copy the value from '?request_token=XXXXX'")
    print("-" * 60)

    request_token = input("Paste that 'request_token' value here and press Enter: ").strip()
    session_data = kite.generate_session(request_token, api_secret=API_SECRET)
    access_token = session_data["access_token"]
    kite.set_access_token(access_token)
    save_access_token(access_token)
    return access_token


_kite_instance = None


def get_kite_instance():
    global _kite_instance
    if _kite_instance is not None:
        return _kite_instance

    access_token = authenticate()
    kite.set_access_token(access_token)
    _kite_instance = kite
    return _kite_instance


def init_kite():
    return get_kite_instance()


if __name__ == "__main__":
    authenticate()
