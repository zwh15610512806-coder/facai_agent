"""初始化数据库并导入种子数据"""
import sys, os
sys.stdout.reconfigure(encoding='utf-8')
from database import init_db

print("=" * 50)
print("  短视频脚本生成 Agent — 数据初始化")
print("=" * 50)

# 1. 创建数据库表
print("\n[1/3] 创建数据库表...")
init_db()
print("  ✅ 数据库表已创建")

# 2. 导入种子产品
print("\n[2/3] 导入种子产品数据...")
from data.seed_products import seed_products
seed_products()

# 3. 导入种子模板
print("\n[3/3] 导入脚本模板和爆款脚本...")
from data.seed_templates import seed_templates
seed_templates()

print("\n" + "=" * 50)
print("  🎉 初始化完成！运行以下命令启动：")
print("     python main.py")
print("  或：")
print("     uvicorn main:app --reload --host 0.0.0.0 --port 8000")
print("=" * 50)
