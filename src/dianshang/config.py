"""全局配置：评分权重、利润阈值、爬取参数、GLM 配置。

从环境变量读取（.env），所有数值集中在此，便于调参与校准。
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field

# 项目根目录：src/dianshang/config.py 的上两级
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(PROJECT_ROOT / ".env")


def _get_bool(key: str, default: bool) -> bool:
    val = os.getenv(key)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


class ScoringWeights(BaseModel):
    """五维评分权重（总和应为 1.0），对应设计文档评估维度。"""

    market_potential: float = Field(default=0.30, description="市场潜力 30%")
    competition: float = Field(default=0.20, description="竞争程度 20%")
    profit: float = Field(default=0.25, description="盈利空间 25%")
    pain_points: float = Field(default=0.15, description="用户痛点 15%")
    risk: float = Field(default=0.10, description="风险等级 10%")


class ScoreThresholds(BaseModel):
    """综合得分 → 推荐等级阈值。"""

    strong_recommend: int = 80  # 强烈推荐
    try_it: int = 65  # 可尝试
    cautious: int = 50  # 谨慎进入
    # < cautious 即「不推荐」


class ProfitConfig(BaseModel):
    """全链路成本测算参数（占售价百分比，除非另注）。"""

    profit_threshold: float = Field(default=30.0, description="毛利率红线（%）")
    platform_commission_rate: float = Field(default=0.06, description="平台佣金率")
    logistics_rate: float = Field(default=0.10, description="物流费占售价")
    promotion_rate: float = Field(default=0.15, description="推广费占售价")
    refund_loss_rate: float = Field(default=0.05, description="退款损耗率")
    tax_rate: float = Field(default=0.03, description="税费率")
    packaging_cost: float = Field(default=2.0, description="包材固定成本（元）")


class LLMConfig(BaseModel):
    api_key: str = Field(default="", description="智谱 API Key")
    model: str = Field(default="glm-4.6")
    temperature: float = Field(default=0.2, description="低温度保证结论稳定")
    timeout: float = Field(default=60.0)
    max_retries: int = Field(default=3)


class CrawlConfig(BaseModel):
    timeout: int = Field(default=30)
    concurrency: int = Field(default=3)
    headless: bool = Field(default=True)
    force_mock: bool = Field(default=False, description="强制走 Mock，跳过真实爬取")


class Paths(BaseModel):
    data_dir: Path = Field(default_factory=lambda: PROJECT_ROOT / "data")
    reports_dir: Path = Field(default_factory=lambda: PROJECT_ROOT / "data" / "reports")
    cache_dir: Path = Field(default_factory=lambda: PROJECT_ROOT / "data" / "cache")
    memory_db: Path = Field(default_factory=lambda: PROJECT_ROOT / "data" / "memory.db")


class Settings(BaseModel):
    scoring_weights: ScoringWeights = Field(default_factory=ScoringWeights)
    score_thresholds: ScoreThresholds = Field(default_factory=ScoreThresholds)
    profit: ProfitConfig = Field(default_factory=ProfitConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    crawl: CrawlConfig = Field(default_factory=CrawlConfig)
    paths: Paths = Field(default_factory=Paths)


def load_settings() -> Settings:
    """从环境变量加载配置。"""
    settings = Settings()
    # 利润阈值
    settings.profit.profit_threshold = float(
        os.getenv("PROFIT_THRESHOLD", settings.profit.profit_threshold)
    )
    # 得分阈值
    settings.score_thresholds.strong_recommend = int(
        os.getenv("SCORE_STRONG_RECOMMEND", settings.score_thresholds.strong_recommend)
    )
    settings.score_thresholds.try_it = int(
        os.getenv("SCORE_TRY", settings.score_thresholds.try_it)
    )
    settings.score_thresholds.cautious = int(
        os.getenv("SCORE_CAUTIOUS", settings.score_thresholds.cautious)
    )
    # LLM
    settings.llm.api_key = os.getenv("ZHIPUAI_API_KEY", "")
    settings.llm.model = os.getenv("GLM_MODEL", settings.llm.model)
    # 爬取
    settings.crawl.timeout = int(os.getenv("CRAWL_TIMEOUT", settings.crawl.timeout))
    settings.crawl.concurrency = int(
        os.getenv("CRAWL_CONCURRENCY", settings.crawl.concurrency)
    )
    settings.crawl.headless = _get_bool("CRAWL_HEADLESS", settings.crawl.headless)
    settings.crawl.force_mock = _get_bool("FORCE_MOCK", settings.crawl.force_mock)
    # 路径
    if val := os.getenv("DATA_DIR"):
        settings.paths.data_dir = Path(val)
    if val := os.getenv("REPORTS_DIR"):
        settings.paths.reports_dir = Path(val)
    if val := os.getenv("MEMORY_DB"):
        settings.paths.memory_db = Path(val)

    # 确保运行时目录存在
    settings.paths.reports_dir.mkdir(parents=True, exist_ok=True)
    settings.paths.cache_dir.mkdir(parents=True, exist_ok=True)
    settings.paths.data_dir.mkdir(parents=True, exist_ok=True)
    return settings


# 全局单例
settings = load_settings()
