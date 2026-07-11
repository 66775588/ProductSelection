# tests/server/test_runner.py
import os
os.environ["FORCE_MOCK"] = "true"  # 保证不触网

from dianshang.server import jobs, runner


def test_run_job_completes_nine_nodes():
    job_id = "test-1"
    jobs.job_store.set(job_id, jobs.JobStatus(job_id=job_id, status="queued"))
    runner.run_job(job_id, "保温杯", "pdd", overrides={"crawl": {"force_mock": True}})
    st = jobs.job_store.get(job_id)
    assert st.status == "done"
    # 9 个节点全部完成
    assert len(st.completed_nodes) == 9
    assert st.completed_nodes[0] == "task_decompose"
    assert st.completed_nodes[-1] == "memory_save"
    # 摘要字段
    assert "recommendation" in st.result
    assert "total_score" in st.result
    assert "scores" in st.result
    assert "report_paths" in st.result


def test_run_job_records_errors_field():
    job_id = "test-2"
    jobs.job_store.set(job_id, jobs.JobStatus(job_id=job_id, status="queued"))
    runner.run_job(job_id, "保温杯", "pdd", overrides={"crawl": {"force_mock": True}})
    st = jobs.job_store.get(job_id)
    assert isinstance(st.errors, list)
    assert isinstance(st.warnings, list)
