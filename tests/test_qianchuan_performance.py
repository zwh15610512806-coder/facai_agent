import unittest
import zipfile
from io import BytesIO

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base
from models import ViralScript
from routers import templates as templates_router
from services.qianchuan_importer import parse_qianchuan_workbook


def _inline_xlsx(headers, rows):
    def cell_name(col_index, row_index):
        letters = ""
        col = col_index + 1
        while col:
            col, remainder = divmod(col - 1, 26)
            letters = chr(65 + remainder) + letters
        return f"{letters}{row_index}"

    def row_xml(row_index, values):
        cells = []
        for col_index, value in enumerate(values):
            text = str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            cells.append(
                f'<c r="{cell_name(col_index, row_index)}" t="inlineStr"><is><t>{text}</t></is></c>'
            )
        return f'<row r="{row_index}">{"".join(cells)}</row>'

    sheet_rows = [row_xml(1, headers)]
    sheet_rows.extend(row_xml(index, row) for index, row in enumerate(rows, start=2))
    sheet_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<dimension ref="A1"/>'
        f'<sheetData>{"".join(sheet_rows)}</sheetData>'
        "</worksheet>"
    )
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("xl/worksheets/sheet1.xml", sheet_xml)
    return buffer.getvalue()


class QianchuanWorkbookParserTests(unittest.TestCase):
    def test_parser_reads_inline_string_rows_when_dimension_is_a1(self):
        workbook = _inline_xlsx(
            [
                "素材名称",
                "素材ID",
                "素材评估",
                "净成交金额",
                "净成交订单数",
                "用户实际支付金额",
                "整体展示次数",
                "整体点击率",
                "整体点击次数",
                "整体转化率",
                "整体消耗",
                "3秒播放率",
                "10秒播放率",
                "平均观看时长",
                "视频完播率",
            ],
            [[
                "价格-26.3.17-刀叉-法采-星遥2.mp4",
                "7618149103516336169",
                "优质",
                "2,500.50",
                "22",
                "2,480.00",
                "12,345",
                "2.05%",
                "253",
                "13.16%",
                "800.25",
                "27.02%",
                "18.20%",
                "6.53",
                "8.10%",
            ]],
        )

        parsed = parse_qianchuan_workbook(workbook, "qianchuan.xlsx")

        self.assertEqual(parsed.row_count, 1)
        self.assertEqual(parsed.amount_field, "净成交金额")
        row = parsed.rows[0]
        self.assertEqual(row.material_id, "7618149103516336169")
        self.assertEqual(row.material_name, "价格-26.3.17-刀叉-法采-星遥2.mp4")
        self.assertEqual(row.transaction_amount, 2500.50)
        self.assertEqual(row.order_count, 22)
        self.assertEqual(row.spend, 800.25)
        self.assertEqual(row.impressions, 12345)
        self.assertEqual(row.ctr, 0.0205)
        self.assertEqual(row.play_10s_rate, 0.182)


class QianchuanPerformanceApiTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        app = FastAPI()

        def override_db():
            try:
                yield self.db
            finally:
                pass

        app.dependency_overrides[templates_router.get_db] = override_db
        app.include_router(templates_router.router, prefix="/api/templates")
        self.client = TestClient(app)

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def test_import_bind_and_auto_high_conversion_from_transaction_amount(self):
        script = ViralScript(
            category="烘焙配件",
            video_type="机制类",
            title="刀叉 / 脚本 / 3.17价格 / 文案",
            script_content="这是一条刀叉脚本文案，长度足够测试千川绑定和高成交标记。",
            is_high_conversion=0,
        )
        self.db.add(script)
        self.db.commit()

        workbook = _inline_xlsx(
            [
                "素材名称",
                "素材ID",
                "净成交金额",
                "净成交订单数",
                "用户实际支付金额",
                "整体展示次数",
                "整体点击率",
                "整体点击次数",
                "整体转化率",
                "整体消耗",
                "3秒播放率",
                "10秒播放率",
                "平均观看时长",
                "视频完播率",
            ],
            [[
                "价格-26.3.17-刀叉-法采-星遥2.mp4",
                "7618149103516336169",
                "2,500.50",
                "22",
                "2,480.00",
                "12,345",
                "2.05%",
                "253",
                "13.16%",
                "800.25",
                "27.02%",
                "18.20%",
                "6.53",
                "8.10%",
            ]],
        )

        upload = self.client.post(
            "/api/templates/qianchuan/import",
            files={"file": ("qianchuan.xlsx", workbook, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        self.assertEqual(upload.status_code, 200)
        self.assertEqual(upload.json()["data"]["imported"], 1)

        performance = self.client.get(f"/api/templates/viral/{script.id}/performance")
        self.assertEqual(performance.status_code, 200)
        self.assertEqual(performance.json()["data"]["summary"]["material_count"], 0)
        self.assertEqual(performance.json()["data"]["candidates"][0]["material_id"], "7618149103516336169")

        bound = self.client.post(
            f"/api/templates/viral/{script.id}/performance/bind",
            json={"material_id": "7618149103516336169"},
        )
        self.assertEqual(bound.status_code, 200)
        self.assertTrue(bound.json()["data"]["is_high_conversion"])
        binding_id = bound.json()["data"]["binding"]["id"]

        self.db.refresh(script)
        self.assertEqual(script.is_high_conversion, 1)

        performance = self.client.get(f"/api/templates/viral/{script.id}/performance").json()["data"]
        self.assertEqual(performance["summary"]["material_count"], 1)
        self.assertEqual(performance["summary"]["transaction_amount"], 2500.50)
        self.assertEqual(performance["summary"]["amount_field"], "净成交金额")
        self.assertEqual(performance["bindings"][0]["material_id"], "7618149103516336169")

        deleted = self.client.delete(f"/api/templates/viral/{script.id}/performance/bind/{binding_id}")
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(deleted.json()["data"]["summary"]["material_count"], 0)

    def test_auto_binds_high_score_materials_and_keeps_low_score_candidates(self):
        script = ViralScript(
            category="烘焙调味",
            video_type="品质类",
            title="调味茶酱 / 脚本 / 品质 / 6.24需求 / 文案",
            script_content="调味茶酱复购口播，强调调味茶酱颜色稳定、出餐方便和用户体验。",
            is_high_conversion=0,
        )
        self.db.add(script)
        self.db.commit()

        workbook = _inline_xlsx(
            [
                "素材名称",
                "素材ID",
                "净成交金额",
                "净成交订单数",
                "用户实际支付金额",
                "整体展示次数",
                "整体点击率",
                "整体点击次数",
                "整体转化率",
                "整体消耗",
            ],
            [
                [
                    "需求（褐色-26.5.8-调味茶酱-法采烘焙旗舰店-姜妈5.mp4",
                    "high-match-001",
                    "2,580.00",
                    "18",
                    "2,530.00",
                    "20,000",
                    "3.00%",
                    "600",
                    "12.00%",
                    "900.00",
                ],
                [
                    "机制-26.4.22-调味-法采-星遥1.mp4",
                    "low-match-001",
                    "680.00",
                    "4",
                    "650.00",
                    "8,000",
                    "1.50%",
                    "120",
                    "3.33%",
                    "260.00",
                ],
            ],
        )

        upload = self.client.post(
            "/api/templates/qianchuan/import",
            files={"file": ("qianchuan-auto.xlsx", workbook, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        self.assertEqual(upload.status_code, 200)
        self.assertEqual(upload.json()["data"]["imported"], 2)
        self.assertEqual(upload.json()["data"]["auto_bound"], 1)

        performance = self.client.get(f"/api/templates/viral/{script.id}/performance")
        self.assertEqual(performance.status_code, 200)
        data = performance.json()["data"]
        self.assertEqual(data["summary"]["material_count"], 1)
        self.assertEqual(data["summary"]["transaction_amount"], 2580.00)
        self.assertEqual([item["material_id"] for item in data["bindings"]], ["high-match-001"])
        self.assertIn("low-match-001", [item["material_id"] for item in data["candidates"]])
        self.assertTrue(data["is_high_conversion"])

        self.db.refresh(script)
        self.assertEqual(script.is_high_conversion, 1)

        repeated = self.client.get(f"/api/templates/viral/{script.id}/performance").json()["data"]
        self.assertEqual([item["material_id"] for item in repeated["bindings"]], ["high-match-001"])

    def test_duplicate_workbook_upload_is_skipped_by_file_hash(self):
        workbook = _inline_xlsx(
            ["素材名称", "素材ID", "用户实际支付金额", "整体消耗"],
            [["机制-26.4.22-调味果酱-法采-星遥1.mp4", "7631466388419297299", "1,900.00", "300.00"]],
        )

        first = self.client.post(
            "/api/templates/qianchuan/import",
            files={"file": ("qianchuan.xlsx", workbook, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        second = self.client.post(
            "/api/templates/qianchuan/import",
            files={"file": ("qianchuan.xlsx", workbook, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.json()["data"]["imported"], 1)
        self.assertEqual(second.json()["data"]["imported"], 0)
        self.assertTrue(second.json()["data"]["duplicate_file"])


if __name__ == "__main__":
    unittest.main()
