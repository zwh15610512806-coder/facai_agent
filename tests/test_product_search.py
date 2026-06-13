import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from models import Product
from routers.products import list_products


class ProductSearchTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=engine)
        self.Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def test_keyword_search_only_returns_product_names_containing_keyword(self):
        db = self.Session()
        try:
            db.add_all([
                Product(
                    name="白色翻糖膏",
                    category="烘焙装饰",
                    price=10,
                    brand="法采",
                    description="白色翻糖产品",
                    status="active",
                ),
                Product(
                    name="浅柔色素",
                    category="烘焙调色",
                    price=20,
                    brand="法采",
                    description="可用于翻糖调色",
                    status="active",
                ),
                Product(
                    name="色粉盘",
                    category="烘焙调色",
                    price=30,
                    brand="翻糖品牌",
                    description="调色工具",
                    status="active",
                ),
            ])
            db.commit()

            results = list_products(category=None, search="翻糖", status="active", db=db)

            self.assertEqual([product.name for product in results], ["白色翻糖膏"])
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
