# ============================================================
# proxyserverconfig.py
# 代理服务器 + VertexAI 凭证 + 默认生成参数 + QPS 控制
# ============================================================

# ===== 本地代理服务器配置 =====
PROXY_HOST = "127.0.0.1"
PROXY_PORT = 7897
PROXY_URL = f"http://{PROXY_HOST}:{PROXY_PORT}"

# ===== VertexAI 配置 =====
VERTEX_PROJECT_ID = "gen-lang-client-0682241933"
VERTEX_LOCATION = "us-central1"
VERTEX_KEY_PATH = "key/gen-lang-client-0682241933-c837790f65f2.json"
VERTEX_MODEL = "gemini-2.5-flash"

# ===== 默认生成参数（每次 AI 调用前用户可覆盖） =====
DEFAULT_TEMPERATURE = 0.7
DEFAULT_TOP_P = 0.9
DEFAULT_TOP_K = 40
DEFAULT_MAX_TOKENS = 16384

# ===== QPS 控制 =====
MAX_CONCURRENT_CALLS = 3    # 盲视变异并行调用最大并发数
MIN_CALL_INTERVAL = 1       # 最短调用间隔（秒）
MAX_CALL_INTERVAL = 5       # 最长调用间隔（秒）
