"""
Pytest Configuration - 测试配置
"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 配置 pytest-asyncio
pytest_plugins = ['pytest_asyncio']

# HTTP route tests emulate the Java application service.  Production has no
# fallback token; the test process supplies an explicit, non-secret value.
from app.utils.config import config

config.INTERNAL_API_TOKEN = "test-internal-token"
config.EMBEDDING_ALLOW_FALLBACK = True
