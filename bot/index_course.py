"""Lập/cập nhật chỉ mục tài liệu. Chạy bằng index_course.bat. Chạy lại an toàn: chỉ làm file mới/đổi."""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent))
load_dotenv(Path(__file__).resolve().parent.parent / ".env")
import rag  # noqa: E402

rag.build_index(Path(os.environ["COURSE_DIR"]), log=lambda s: print(s, flush=True))
print("Xong.")
