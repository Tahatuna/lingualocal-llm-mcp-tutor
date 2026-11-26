"""Settings, all from the environment so another project can run the service with its own values."""
import os

HOST = "127.0.0.1"  # never reachable from the network
PORT = int(os.environ.get("LS_PORT") or 8770)
DATA_DIR = os.environ.get("LS_DATA_DIR") or os.path.expanduser("~/Library/Application Support/Language Services")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS_DIR = os.path.join(ROOT, "models")

# Pages allowed to call the API from a browser (CORS). Comma separated.
ALLOWED_ORIGINS = {o.strip() for o in (os.environ.get("LS_ALLOWED_ORIGINS")
                                       or "http://localhost:8767,http://127.0.0.1:8767").split(",") if o.strip()}

OLLAMA_URL = (os.environ.get("LS_OLLAMA_URL") or "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL = os.environ.get("LS_OLLAMA_MODEL") or "gemma3:12b"
OLLAMA_KEEP_ALIVE = os.environ.get("LS_OLLAMA_KEEP_ALIVE") or "30m"

# Natural English voices (Kokoro); Turkish uses the macOS system voice.
VOICE_US = os.environ.get("LS_VOICE_US") or "af_heart"
VOICE_UK = os.environ.get("LS_VOICE_UK") or "bf_emma"
VOICE_TR = os.environ.get("LS_VOICE_TR") or "Yelda"

USER_AGENT = "language-services/1.0 (local learning app)"
