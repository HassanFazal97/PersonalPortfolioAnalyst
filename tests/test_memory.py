"""Semantic memory: chunkers, ingestion, the recall tool, and chat gating."""

import uuid
from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

from app.memory import ingest
from app.memory.embeddings import EmbeddingClient
from app.tools.recall import recall_memory
from app.tools.registry import ToolContext
from tests.fakes import FakeRepo


class FakeEmbedder(EmbeddingClient):
    """Deterministic embedder: no network, tiny fake vectors, fixed cost."""

    def __init__(self):
        super().__init__(api_key="fake-key", model="voyage-3.5-lite")
        self.calls: list[tuple[list[str], str]] = []

    async def embed(self, texts, *, input_type):
        self.calls.append((list(texts), input_type))
        self.cost_usd += 0.00001 * len(texts)
        return [[0.1] * 4 for _ in texts]


# ---- chunkers ---------------------------------------------------------------


def test_chunk_chat_short_is_single_chunk():
    chunks = ingest.chunk_chat("How's NVDA?", "It's up 2% today.")
    assert chunks == ["Q: How's NVDA?\nA: It's up 2% today."]


def test_chunk_chat_long_splits_at_paragraphs():
    answer = "\n\n".join(f"Paragraph {i} " + "x" * 400 for i in range(8))
    chunks = ingest.chunk_chat("Q?", answer, max_chars=1000)
    assert len(chunks) > 1
    assert all(len(c) <= 1000 for c in chunks)
    assert "".join(chunks).startswith("Q: Q?")


def test_chunk_chat_hard_splits_monster_paragraph():
    chunks = ingest.chunk_chat("Q?", "y" * 5000, max_chars=1000)
    assert all(len(c) <= 1000 for c in chunks)
    assert sum(len(c) for c in chunks) >= 5000


def test_mentioned_tickers_word_boundaries():
    text = "NVDA rallied while SHOP.TO slipped; tech overall was flat."
    assert ingest.mentioned_tickers(text, ["NVDA", "SHOP.TO", "TE"]) == ["NVDA", "SHOP.TO"]


# ---- ingestion --------------------------------------------------------------


async def test_embed_digest_inserts_chunk_with_tickers():
    repo = FakeRepo()
    uid = uuid.uuid4()
    client = FakeEmbedder()
    n = await ingest.embed_digest(
        repo, user_id=uid, digest_id=uuid.uuid4(),
        body="PORTFOLIO: +1% — NVDA led gains.", digest_date=date(2026, 7, 20),
        holdings_tickers=["NVDA", "SHOP.TO"], client=client,
    )
    assert n == 1
    chunk = repo.memory_chunks[0]
    assert chunk["source_type"] == "digest"
    assert chunk["tickers"] == ["NVDA"]
    assert chunk["content_date"] == date(2026, 7, 20)
    assert client.calls[0][1] == "document"


async def test_embed_chat_run_is_idempotent():
    repo = FakeRepo()
    uid = uuid.uuid4()
    run_id = uuid.uuid4()
    client = FakeEmbedder()
    kwargs = dict(
        user_id=uid, run_id=run_id, question="How's NVDA?",
        answer="Up 2%.", created_at=datetime.now(timezone.utc),
        holdings_tickers=["NVDA"],
    )
    assert await ingest.embed_chat_run(repo, client=client, **kwargs) == 1
    assert await ingest.embed_chat_run(repo, client=client, **kwargs) == 0  # dup


async def test_embed_news_items_dates_from_published_at():
    repo = FakeRepo()
    uid = uuid.uuid4()
    row = SimpleNamespace(
        id=uuid.uuid4(), ticker="NVDA", headline="NVDA beats estimates",
        summary="Strong quarter.", published_at=datetime(2026, 7, 15, tzinfo=timezone.utc),
        created_at=datetime.now(timezone.utc),
    )
    n = await ingest.embed_news_items(repo, user_id=uid, rows=[row], client=FakeEmbedder())
    assert n == 1
    assert repo.memory_chunks[0]["content_date"] == date(2026, 7, 15)
    assert repo.memory_chunks[0]["tickers"] == ["NVDA"]


async def test_ingest_disabled_without_key_is_noop():
    repo = FakeRepo()
    client = EmbeddingClient(api_key="", model="voyage-3.5-lite")
    n = await ingest.embed_digest(
        repo, user_id=uuid.uuid4(), digest_id=uuid.uuid4(), body="x",
        digest_date=date.today(), holdings_tickers=[], client=client,
    )
    assert n == 0
    assert not hasattr(repo, "memory_chunks")


# ---- recall tool ------------------------------------------------------------


def _ctx(repo, uid, budget=None):
    from app.config import get_settings

    ctx = ToolContext(settings=get_settings(), repo=repo, user_id=uid)
    ctx.budget = budget
    return ctx


async def test_recall_memory_returns_scoped_dated_items(monkeypatch):
    repo = FakeRepo()
    uid, other = uuid.uuid4(), uuid.uuid4()
    fake = FakeEmbedder()
    monkeypatch.setattr("app.tools.recall.EmbeddingClient", lambda: fake)
    await ingest.embed_digest(
        repo, user_id=uid, digest_id=uuid.uuid4(),
        body="NVDA slipped 3% on export-control news.",
        digest_date=date(2026, 6, 20), holdings_tickers=["NVDA"], client=fake,
    )
    await ingest.embed_digest(
        repo, user_id=other, digest_id=uuid.uuid4(),
        body="Other tenant's digest about NVDA.",
        digest_date=date(2026, 6, 21), holdings_tickers=["NVDA"], client=fake,
    )

    result = await recall_memory(
        {"query": "what did you say about NVDA?", "tickers": ["nvda"]},
        _ctx(repo, uid),
    )
    assert result["count"] == 1
    item = result["items"][0]
    assert item["date"] == "2026-06-20"
    assert item["source_type"] == "digest"
    assert "export-control" in item["content"]
    # Query embeds use the asymmetric "query" input type
    assert fake.calls[-1][1] == "query"


async def test_recall_memory_charges_budget(monkeypatch):
    from app.agent.budget import Budget

    repo = FakeRepo()
    fake = FakeEmbedder()
    monkeypatch.setattr("app.tools.recall.EmbeddingClient", lambda: fake)
    budget = Budget(max_iterations=5, max_cost_usd=0.1, model="claude-sonnet-4-6")
    await recall_memory({"query": "anything"}, _ctx(repo, uuid.uuid4(), budget))
    assert budget.cost_usd > 0


async def test_recall_memory_rejects_bad_dates():
    with pytest.raises(ValueError, match="date_from"):
        await recall_memory(
            {"query": "x", "date_from": "last month"},
            _ctx(FakeRepo(), uuid.uuid4()),
        )


# ---- chat gating ------------------------------------------------------------


def test_prepare_chat_offers_recall_only_with_key(monkeypatch):
    import asyncio

    import app.main as main
    from app.config import get_settings

    repo = FakeRepo()
    uid = uuid.uuid4()
    repo.seed_user(uid, plan="free")

    async def run(with_key: bool):
        monkeypatch.setenv("VOYAGE_API_KEY", "vk" if with_key else "")
        get_settings.cache_clear()
        _plan, _budget, _ctx2, tools, system_prompt, _hist = await main._prepare_chat(
            repo, uid, get_settings()
        )
        names = [t.get("name") for t in tools]
        return names, system_prompt

    names, prompt = asyncio.run(run(True))
    assert "recall_memory" in names
    assert "recall_memory" in prompt
    names, prompt = asyncio.run(run(False))
    assert "recall_memory" not in names
    assert "recall_memory" not in prompt
    get_settings.cache_clear()
