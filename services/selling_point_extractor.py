"""从产品资料文件中提取卖点，替换原有卖点话术"""
import json
import logging
import os

from services.ai_service import ai_service
from services.bounded_executor import run_blocking

logger = logging.getLogger(__name__)


def read_file_content(file_path: str) -> str:
    """读取各类文件内容为纯文本"""
    ext = os.path.splitext(file_path)[1].lower()

    if ext == ".txt":
        with open(file_path, encoding="utf-8") as file:
            return file.read()

    if ext == ".pdf":
        try:
            from pdfminer.high_level import extract_text
            return extract_text(file_path)
        except ImportError:
            try:
                import PyPDF2
                text = ""
                with open(file_path, "rb") as file:
                    reader = PyPDF2.PdfReader(file)
                    for page in reader.pages:
                        text += page.extract_text() or ""
                return text
            except ImportError:
                return "[PDF文件需安装 pdfminer.six 或 PyPDF2 来读取]"

    if ext in (".docx", ".doc"):
        try:
            from docx import Document
            doc = Document(file_path)
            return "\n".join([p.text for p in doc.paragraphs])
        except ImportError:
            return "[Word文件需安装 python-docx 来读取]"

    if ext in (".xlsx", ".xls"):
        try:
            import pandas as pd
            df = pd.read_excel(file_path)
            # 把所有单元格拼接
            texts = []
            for col in df.columns:
                for val in df[col].dropna():
                    texts.append(str(val))
            return "\n".join(texts)
        except ImportError:
            return "[Excel文件需安装 openpyxl/pandas 来读取]"

    if ext in (".png", ".jpg", ".jpeg"):
        return "[图片文件暂不支持文字提取]"

    # 默认当文本读
    try:
        with open(file_path, encoding="utf-8") as file:
            return file.read()
    except (OSError, UnicodeError):
        return f"[无法读取文件: {file_path}]"


async def extract_selling_points(
    file_path: str,
    product_name: str,
    product_category: str,
) -> list[dict]:
    """从文件中提取卖点，返回卖点列表"""
    content = await run_blocking(read_file_content, file_path)

    if not content or content.startswith("["):
        logger.warning("无法读取文件内容: %s", file_path)
        return []

    # 截断过长内容
    if len(content) > 8000:
        content = content[:8000] + "\n...(内容过长已截断)"

    prompt = f"""请从以下产品资料中提取关键卖点话术。

产品名称：{product_name}
产品品类：{product_category}

资料内容：
{content}

请提取 3-5 条卖点，每条卖点需要：
- point_type：卖点类型（功效/性价比/场景/痛点/对比）
- content：具体的卖点话术，用于短视频口播，要口语化、有感召力
- priority：1-5，最重要的排1

只输出 JSON 数组格式，不要任何其他文字：
[
  {{"point_type": "功效", "content": "具体话术...", "priority": 1}},
  ...
]"""

    if ai_service.is_available:
        try:
            messages = [
                {"role": "system", "content": "你是一个烘焙产品卖点提炼专家。只输出JSON数组，不要其他文字。"},
                {"role": "user", "content": prompt},
            ]
            result = await ai_service.chat(
                messages,
                temperature=0.3,
                interface_key="selling_point_extract",
            )

            # 提取 JSON
            start = result.find("[")
            end = result.rfind("]") + 1
            if start >= 0 and end > start:
                return json.loads(result[start:end])
        except Exception:
            logger.exception("AI提取卖点失败")

    # 离线回退：简单拆分
    lines = [
        line.strip()
        for line in content.split("\n")
        if line.strip() and len(line.strip()) > 10
    ]
    points = []
    for i, line in enumerate(lines[:5]):
        points.append({
            "point_type": "功效" if i == 0 else ("性价比" if i == 1 else "场景"),
            "content": line[:80],
            "priority": i + 1,
        })
    return points
