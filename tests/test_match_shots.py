import asyncio
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from models import GeneratedScript, Product
from routers import scripts as scripts_router
from schemas import ScriptShotMatchRequest
from services.script_generator import ScriptGenerator


class FakeShotMatchGenerator:
    def __init__(self):
        self.called_with = None

    def get_model_name(self):
        return "fake-model"

    async def match_shots_to_copy(self, script_content, product):
        self.called_with = (script_content, product)
        return "（主播半身口播，手拿产品开场）" + script_content


class MatchShotsApiTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        product = Product(name="袋装刀叉", category="烘焙配件", price=55.17, brand="法采")
        self.db.add(product)
        self.db.commit()
        self.db.refresh(product)
        self.product = product
        self.original_generator = scripts_router.generator

    def tearDown(self):
        scripts_router.generator = self.original_generator
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def test_match_shots_request_requires_existing_copy(self):
        with self.assertRaises(ValueError):
            ScriptShotMatchRequest(product_id=self.product.id, script_content="  ")

    def test_match_shots_endpoint_updates_current_history_record(self):
        record = GeneratedScript(
            product_id=self.product.id,
            script_content="姐妹们，这套餐具很划算。",
            video_type="高成交模板库",
            ai_model="fake-model",
        )
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)

        fake = FakeShotMatchGenerator()
        scripts_router.generator = fake
        request = ScriptShotMatchRequest(
            product_id=self.product.id,
            script_id=record.id,
            script_content="姐妹们，这套餐具很划算。",
        )

        response = asyncio.run(scripts_router.match_script_shots(request, db=self.db))

        self.assertEqual(response.product_name, "袋装刀叉")
        self.assertIn("（主播半身口播", response.script_content)
        self.assertIn("姐妹们，这套餐具很划算。", response.script_content)
        self.assertEqual(
            self.db.query(GeneratedScript).filter(GeneratedScript.id == record.id).first().script_content,
            response.script_content,
        )
        self.assertEqual(fake.called_with[0], "姐妹们，这套餐具很划算。")
        self.assertEqual(fake.called_with[1]["name"], "袋装刀叉")


class MatchShotsGeneratorTests(unittest.TestCase):
    def test_match_shots_to_copy_preserves_every_sentence(self):
        generator = ScriptGenerator()
        script = "姐妹们，这套餐具很划算。现在下单还能省不少！左下角直接拍。"

        result = asyncio.run(generator.match_shots_to_copy(
            script,
            {"name": "袋装刀叉", "category": "烘焙配件", "price": 55.17, "brand": "法采"},
        ))

        self.assertIn("（", result)
        self.assertIn("）姐妹们，这套餐具很划算。", result)
        self.assertIn("）现在下单还能省不少！", result)
        self.assertIn("）左下角直接拍。", result)
        self.assertNotIn("【", result)
        self.assertNotIn("】", result)


if __name__ == "__main__":
    unittest.main()
