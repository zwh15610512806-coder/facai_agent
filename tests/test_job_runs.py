import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from models import JobRun


class PersistentJobRunTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.engine = create_engine(f"sqlite:///{(Path(self.temp_dir.name) / 'jobs.db').as_posix()}")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.db = self.Session()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        self.temp_dir.cleanup()

    def test_job_progress_and_success_are_persisted(self):
        from services.job_runs import finish_job, start_job, update_job

        job_id = start_job("search_rebuild", total=100, message="扫描中", db=self.db)
        update_job(job_id, current=40, total=100, message="已扫描 40", details={"files": 40}, db=self.db)
        finish_job(job_id, status="succeeded", message="完成", db=self.db)

        job = self.db.get(JobRun, job_id)
        self.assertEqual(job.status, "succeeded")
        self.assertEqual(job.progress_current, 40)
        self.assertEqual(job.progress_total, 100)
        self.assertEqual(job.details["files"], 40)
        self.assertIsNotNone(job.finished_at)

    def test_restart_marks_leftover_running_jobs_interrupted(self):
        from services.job_runs import recover_interrupted_jobs, start_job

        job_id = start_job("workbook_import", total=10, db=self.db)
        recovered = recover_interrupted_jobs(db=self.db)

        self.assertEqual(recovered, 1)
        job = self.db.get(JobRun, job_id)
        self.assertEqual(job.status, "interrupted")
        self.assertIn("重启", job.message)
        self.assertIsNotNone(job.finished_at)

    def test_new_progress_revives_an_active_job_marked_interrupted(self):
        from services.job_runs import recover_interrupted_jobs, start_job, update_job

        job_id = start_job("search_rebuild", total=100, db=self.db)
        recover_interrupted_jobs(db=self.db)

        update_job(job_id, current=50, message="worker still active", db=self.db)

        job = self.db.get(JobRun, job_id)
        self.assertEqual(job.status, "running")
        self.assertIsNone(job.finished_at)
        self.assertIsNone(job.error_summary)

    def test_helpers_create_job_runs_table_when_missing(self):
        from services.job_runs import latest_job, start_job

        JobRun.__table__.drop(self.engine)

        job_id = start_job("search_rebuild", message="扫描中", db=self.db)
        latest = latest_job("search_rebuild", db=self.db)

        self.assertEqual(latest["id"], job_id)
        self.assertEqual(latest["message"], "扫描中")
        self.assertIsNone(latest["progress"])


if __name__ == "__main__":
    unittest.main()
