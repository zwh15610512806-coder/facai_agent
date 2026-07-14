import unittest
from datetime import date, datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from creator_models import BdMember, Creator, CreatorCollaboration, CreatorFollowup, CreatorPortrait
from database import Base, get_db
from models import Product, SellingPoint
from routers import creators as creators_router
from routers import products as products_router


class ListQueryBudgetTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        app = FastAPI()

        def override_db():
            yield self.db

        app.dependency_overrides[get_db] = override_db
        app.include_router(creators_router.router, prefix="/api/creators")
        app.include_router(products_router.router, prefix="/api/products")
        self.client = TestClient(app)

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def _query_count(self, request) -> tuple[int, object]:
        statements = []

        def record(_connection, _cursor, statement, _parameters, _context, _many):
            statements.append(statement)

        event.listen(self.engine, "before_cursor_execute", record)
        try:
            response = request()
        finally:
            event.remove(self.engine, "before_cursor_execute", record)
        return len(statements), response

    def test_creator_page_stays_within_five_queries_for_thirty_rows(self):
        owner = BdMember(name="负责人")
        self.db.add(owner)
        self.db.flush()
        for index in range(30):
            creator = Creator(
                nickname=f"达人{index}",
                douyin_handle=f"creator-{index}",
                douyin_handle_normalized=f"creator-{index}",
                owner_id=owner.id,
                stage="lead",
            )
            self.db.add(creator)
            self.db.flush()
            self.db.add(CreatorPortrait(
                creator_id=creator.id,
                follower_count=10_000 + index,
                primary_categories=["烘焙"],
            ))
            self.db.add(CreatorCollaboration(
                creator_id=creator.id,
                source_type="manual",
                internal_code=f"C-{index}",
                collaboration_type="short_video",
                collaboration_date=date.today(),
                status="completed",
                actual_paid_cents=10_000,
                amount_status="confirmed",
            ))
            self.db.add(CreatorFollowup(
                creator_id=creator.id,
                followed_up_at=datetime.now(),
                method="wechat",
                content="已沟通",
            ))
        self.db.commit()
        self.db.expire_all()

        count, response = self._query_count(
            lambda: self.client.get("/api/creators", params={"per_page": 30})
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(response.json()["items"]), 30)
        self.assertLessEqual(count, 5, f"creator list executed {count} SQL statements")

    def test_product_lists_stay_within_fixed_query_budget(self):
        for index in range(70):
            product = Product(
                name=f"产品{index}", category="烘焙", price=10 + index, status="active"
            )
            self.db.add(product)
            self.db.flush()
            self.db.add(SellingPoint(
                product_id=product.id,
                point_type="卖点",
                content=f"卖点{index}",
                priority=1,
            ))
        self.db.commit()
        self.db.expire_all()

        legacy_count, legacy = self._query_count(lambda: self.client.get("/api/products/"))
        page_count, page = self._query_count(
            lambda: self.client.get("/api/products/page", params={"page": 1, "per_page": 50})
        )

        self.assertEqual(legacy.status_code, 200, legacy.text)
        self.assertEqual(len(legacy.json()), 70)
        self.assertLessEqual(legacy_count, 3, f"legacy product list executed {legacy_count} SQL statements")
        self.assertEqual(page.status_code, 200, page.text)
        self.assertEqual(len(page.json()["items"]), 50)
        self.assertEqual(page.json()["total"], 70)
        self.assertLessEqual(page_count, 4, f"paged product list executed {page_count} SQL statements")


if __name__ == "__main__":
    unittest.main()
