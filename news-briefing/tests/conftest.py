"""pytest 配置 — 将 src/ 加入 Python 路径。"""

import sys
from pathlib import Path

# 将 src 目录加入 Python 搜索路径
src_path = Path(__file__).parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))
