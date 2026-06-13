"""将法采脚本库导入 ViralScript 表"""
import sys
import json
sys.path.insert(0, '.')

from database import SessionLocal, init_db
from models import ViralScript

# 视频类型映射：Excel类型 -> 模型video_type
TYPE_MAP = {
    '需求': '痛点激发',
    '痛点': '痛点激发',
    '机制': '限时优惠',
    '爆款翻拍': '黄金3秒种草',
    '对比': '测评对比',
    '创意': '剧情带货',
}


def import_facai_scripts(json_path: str):
    init_db()
    db = SessionLocal()
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        added = 0
        skipped = 0

        for sheet, info in data['详细数据'].items():
            for script in info['脚本列表']:
                bh = (
                    script.get('编号（1-7-1即为1月7日的第一条素材）y', '') or
                    script.get('编号（1-7-1即为1月7日的第一条素材）', '') or
                    script.get('编号', '') or ''
                )
                raw_type = script.get('类型', '') or ''
                video_type = TYPE_MAP.get(raw_type, '痛点激发')

                script_col = (
                    script.get('视频脚本（红括号为画面，绿括号为剪辑要求）', '') or
                    script.get('视频脚本（括号内为画面，括号后面的文字为视频内容）', '') or
                    script.get('视频脚本', '') or ''
                )

                if not script_col or not bh:
                    skipped += 1
                    continue

                # 判断是否已拍
                is_yipai = '已拍' in bh

                # 拍摄地点
                ps = script.get('拍摄地点', '') or script.get('拍摄场地', '') or ''
                zy = script.get('注意事项', '') or ''
                al = script.get('案例视频', '') or ''

                vs = ViralScript(
                    category=f"法采-{sheet}",
                    video_type=video_type,
                    title=f"{bh} [{raw_type}] {sheet}",
                    script_content=script_col,
                    performance_data={
                        'source': '法采脚本库',
                        'product': sheet,
                        '编号': bh,
                        '拍摄地点': ps,
                        '注意事项': zy,
                        '案例视频': al,
                        '已拍': is_yipai,
                    },
                    tags=f"法采,{sheet},{raw_type}",
                    is_high_conversion=1 if is_yipai else 0,
                )
                db.add(vs)
                added += 1

        db.commit()
        print(f"导入完成：新增 {added} 条脚本，跳过 {skipped} 条（无脚本内容）")
    except Exception as e:
        db.rollback()
        print(f"导入失败: {e}")
        raise
    finally:
        db.close()


if __name__ == '__main__':
    import os
    # 优先从 Downloads 找
    paths = [
        'C:/Users/Probably/Downloads/法采脚本库_结构化.json',
        './法采脚本库_结构化.json',
    ]
    json_path = None
    for p in paths:
        if os.path.exists(p):
            json_path = p
            break
    if not json_path:
        print(f"找不到法采脚本库JSON文件，尝试了: {paths}")
        sys.exit(1)
    import_facai_scripts(json_path)
