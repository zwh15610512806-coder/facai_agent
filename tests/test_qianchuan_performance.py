import unittest
import zipfile
from io import BytesIO

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base
from models import (
    QianchuanImportBatch,
    QianchuanMaterialPerformance,
    QianchuanScriptBinding,
    ViralScript,
)
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

    def _add_qianchuan_material(
        self,
        material_id,
        material_name,
        transaction_amount=0,
        order_count=0,
    ):
        batch = self.db.query(QianchuanImportBatch).first()
        if not batch:
            batch = QianchuanImportBatch(
                filename="seed.xlsx",
                file_sha256=f"seed-{material_id}",
                row_count=0,
                imported_count=0,
                skipped_count=0,
                amount_field="净成交金额",
            )
            self.db.add(batch)
            self.db.flush()
        material = QianchuanMaterialPerformance(
            batch_id=batch.id,
            material_id=material_id,
            material_name=material_name,
            amount_field="净成交金额",
            transaction_amount=transaction_amount,
            order_count=order_count,
        )
        self.db.add(material)
        self.db.commit()
        return material

    def test_summary_includes_average_order_value_and_zero_order_fallback(self):
        material = self._add_qianchuan_material(
            "avg-001",
            "需求-26.5.8-调味茶酱-法采-姜妈5.mp4",
            transaction_amount=2580,
            order_count=18,
        )

        summary = templates_router._summarize_qianchuan_materials([material])

        self.assertEqual(summary["average_order_value"], 143.33)

        zero_order_material = self._add_qianchuan_material(
            "avg-002",
            "需求-26.5.9-调味茶酱-法采-姜妈6.mp4",
            transaction_amount=1200,
            order_count=0,
        )

        zero_order_summary = templates_router._summarize_qianchuan_materials([zero_order_material])

        self.assertEqual(zero_order_summary["average_order_value"], 0)

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

    def test_auto_match_dry_run_returns_alias_matches_without_creating_bindings(self):
        script = ViralScript(
            category="烘焙调味",
            video_type="需求类",
            title="茶酱 / 脚本 / 26.5.8需求 / 文案",
            script_content="茶酱用于调味茶饮和面包夹心，强调出餐稳定。",
            is_high_conversion=0,
        )
        self.db.add(script)
        self.db.commit()
        self._add_qianchuan_material(
            "tea-jam-001",
            "需求-26.5.8-调味果酱-法采-姜妈5.mp4",
            transaction_amount=2300,
            order_count=16,
        )

        response = self.client.post(
            "/api/templates/qianchuan/bindings/auto-match",
            json={"mode": "dry_run"},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["mode"], "dry_run")
        self.assertEqual(data["created"], 0)
        self.assertEqual(data["planned"], 1)
        self.assertEqual(data["matches"][0]["script_id"], script.id)
        self.assertEqual(data["matches"][0]["material_id"], "tea-jam-001")
        self.assertIn("茶酱", data["matches"][0]["matched_aliases"])
        self.assertEqual(self.db.query(QianchuanScriptBinding).count(), 0)

    def test_auto_match_apply_is_idempotent_preserves_bindings_and_rejects_category_only(self):
        existing_script = ViralScript(
            category="烘焙调味",
            video_type="机制类",
            title="已绑定脚本",
            script_content="已有人工绑定，不应该被全量匹配重建或覆盖。",
        )
        alias_script = ViralScript(
            category="烘焙调色",
            video_type="需求类",
            title="果蔬粉 / 脚本 / 26.6.1需求 / 文案",
            script_content="果蔬粉做蛋糕调色，讲果蔬色素上色自然。",
        )
        generic_script = ViralScript(
            category="烘焙配件",
            video_type="需求类",
            title="烘焙配件 / 脚本 / 26.6.2需求 / 文案",
            script_content="只提到烘焙配件大类，没有明确产品名。",
        )
        self.db.add_all([existing_script, alias_script, generic_script])
        self.db.commit()
        self._add_qianchuan_material("manual-001", "机制-26.5.1-茶酱-法采.mp4", 800, 3)
        self._add_qianchuan_material("color-001", "需求-26.6.1-果蔬色素-法采.mp4", 2600, 18)
        self._add_qianchuan_material("generic-001", "需求-26.6.2-烘焙配件-法采.mp4", 3000, 21)
        self.db.add(QianchuanScriptBinding(
            script_id=existing_script.id,
            material_id="manual-001",
            material_name="机制-26.5.1-茶酱-法采.mp4",
        ))
        self.db.commit()

        first = self.client.post(
            "/api/templates/qianchuan/bindings/auto-match",
            json={"mode": "apply"},
        )
        second = self.client.post(
            "/api/templates/qianchuan/bindings/auto-match",
            json={"mode": "apply"},
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()["data"]["created"], 1)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json()["data"]["created"], 0)
        bindings = self.db.query(QianchuanScriptBinding).order_by(
            QianchuanScriptBinding.material_id
        ).all()
        self.assertEqual([item.material_id for item in bindings], ["color-001", "manual-001"])
        status = self.client.get("/api/templates/qianchuan/bindings/auto-match/status")
        self.assertEqual(status.status_code, 200)
        self.assertEqual(status.json()["data"]["last_result"]["mode"], "apply")

    def test_auto_match_keeps_ambiguous_alias_materials_as_candidates(self):
        script = ViralScript(
            category="烘焙造型",
            video_type="机制类",
            title="翻糖膏 / 脚本 / 26.5.3机制 / 文案",
            script_content="翻糖膏用于蛋糕造型，强调延展性和稳定性。",
        )
        self.db.add(script)
        self.db.commit()
        self._add_qianchuan_material("fondant-001", "机制-26.5.3-翻糖-法采-星遥1.mp4", 2100, 12)
        self._add_qianchuan_material("fondant-002", "机制-26.5.3-翻糖膏-法采-星遥2.mp4", 2050, 11)

        response = self.client.post(
            "/api/templates/qianchuan/bindings/auto-match",
            json={"mode": "apply"},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["created"], 0)
        self.assertEqual(data["ambiguous"][0]["script_id"], script.id)
        self.assertEqual(
            {item["material_id"] for item in data["ambiguous"][0]["candidates"]},
            {"fondant-001", "fondant-002"},
        )
        self.assertEqual(self.db.query(QianchuanScriptBinding).count(), 0)

    def test_auto_match_does_not_bind_one_material_to_multiple_scripts(self):
        first_script = ViralScript(
            category="烘焙装饰",
            video_type="机制类",
            title="翻糖膏 / 脚本 / 26.5.3机制 / A",
            script_content="翻糖膏用于蛋糕造型，强调延展性。",
        )
        second_script = ViralScript(
            category="烘焙装饰",
            video_type="机制类",
            title="翻糖膏 / 脚本 / 26.5.3机制 / B",
            script_content="翻糖膏用于蛋糕造型，强调稳定性。",
        )
        self.db.add_all([first_script, second_script])
        self.db.commit()
        self._add_qianchuan_material("fondant-shared", "机制-26.5.3-翻糖膏-法采-星遥1.mp4", 2200, 14)

        response = self.client.post(
            "/api/templates/qianchuan/bindings/auto-match",
            json={"mode": "apply"},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["created"], 0)
        self.assertEqual(
            [item for item in data["ambiguous"] if item.get("material_id") == "fondant-shared"][0]["material_id"],
            "fondant-shared",
        )
        self.assertEqual(self.db.query(QianchuanScriptBinding).count(), 0)


if __name__ == "__main__":
    unittest.main()
