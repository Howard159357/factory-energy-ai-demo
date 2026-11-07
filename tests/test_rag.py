import logging
import uuid
from pathlib import Path

import pytest

from factory_energy.rag.chunk import chunk_markdown, chunk_pdf
from factory_energy.rag.embed import (
    HashEmbedder,
    LocalOnnxEmbedder,
    make_embedder,
    pool,
    tokens,
)
from factory_energy.rag.ingest import discover, ingest
from factory_energy.rag.store import KnowledgeStore, persistent_client

CORPUS = {
    "kb/compressors.md": """# Compressed air system

## Night load baseline
The compressor night load between 02:00 and 05:00 is compared with the median of the last six
similar nights. A CUSUM alarm means a leak is likely: walk the network with an ultrasonic
detector.

## Lead and lag
AC-01 is the base machine, AC-03 is the VSD trim and AC-02 is the lag compressor.
""",
    "kb/reflow.md": """# Reflow oven manual

## Start-up
The oven switches on 35 to 60 minutes before its SMT line and preheats at 80 % of rating for
45 minutes.

## Weekend shutdown
Switch reflow ovens off at the end of the last shift. Standby over a weekend wastes energy.
""",
    "kb/tariff.md": """# Tariff guide

## Exceedance penalty
Demand above the 1,250 kW contract is billed at twice the contract price up to 10 % over and
three times beyond.

## Power factor
The monthly power factor adjusts the bill by 0.1 % per point from 80 %, up to 95 %.
""",
}


def write_corpus(root: Path, files: dict[str, str]) -> list[Path]:
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return discover(("kb",), root)


_CLIENT: list[object] = []


def new_store(embedder: HashEmbedder | None = None) -> KnowledgeStore:
    """A fresh collection in one on-disk client shared by this module (unique names isolate)."""
    if not _CLIENT:
        import tempfile

        _CLIENT.append(persistent_client(Path(tempfile.mkdtemp(prefix="rag-tests-"))))
    return KnowledgeStore(_CLIENT[0], embedder or HashEmbedder(), f"t-{uuid.uuid4().hex}")


@pytest.fixture
def store(tmp_path: Path) -> KnowledgeStore:
    knowledge = new_store()
    ingest(knowledge, write_corpus(tmp_path, CORPUS), tmp_path)
    return knowledge


def test_chunks_follow_headings_and_carry_the_heading_path() -> None:
    chunks = chunk_markdown(CORPUS["kb/reflow.md"], "kb/reflow.md")
    assert [c.heading for c in chunks] == [
        "Reflow oven manual > Start-up", "Reflow oven manual > Weekend shutdown"
    ]
    assert all(c.text.startswith(c.heading) for c in chunks)
    assert [c.chunk_id for c in chunks] == ["kb/reflow.md#0", "kb/reflow.md#1"]


def test_long_sections_are_windowed_with_overlap_and_code_is_not_a_heading() -> None:
    paragraphs = [f"Paragraph {i} " + "energy " * 40 for i in range(12)]
    text = "# Title\n\n```\n# not a heading\n```\n\n" + "\n\n".join(paragraphs)
    chunks = chunk_markdown(text, "doc.md", max_chars=600, overlap=100)
    assert len(chunks) > 3
    assert {c.heading for c in chunks} == {"Title"}
    assert all(len(c.text) <= 600 + len("Title\n\n") for c in chunks)
    for previous, current in zip(chunks, chunks[1:], strict=False):
        assert previous.text[-60:] in current.text  # the tail is repeated as overlap
    with pytest.raises(ValueError):
        chunk_markdown(text, "doc.md", max_chars=100, overlap=100)


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("when does the CUSUM night load alarm mean an air leak", "kb/compressors.md"),
        ("how long does the reflow oven preheat before the SMT line", "kb/reflow.md"),
        ("what is the penalty for demand above the contract", "kb/tariff.md"),
    ],
)
def test_the_right_document_ranks_first(
    store: KnowledgeStore, question: str, expected: str
) -> None:
    top = store.search(question, k=3)
    assert top[0].source == expected
    assert top[0].score > top[-1].score


def test_passages_carry_citable_metadata(store: KnowledgeStore) -> None:
    passage = store.search("which compressor is the VSD trim machine", k=1)[0]
    assert passage.source == "kb/compressors.md"
    assert passage.heading == "Compressed air system > Lead and lag"
    assert passage.citation == "kb/compressors.md#Compressed air system > Lead and lag"
    assert "AC-03" in passage.text and passage.page is None


def test_ingest_is_idempotent_and_tracks_changes(tmp_path: Path) -> None:
    knowledge = new_store()
    files = write_corpus(tmp_path, CORPUS)
    first = ingest(knowledge, files, tmp_path)
    assert sorted(first.added) == sorted(CORPUS) and knowledge.count() == 6
    again = ingest(knowledge, files, tmp_path)
    assert not again.changed and again.chunks == 0

    (tmp_path / "kb/tariff.md").write_text("# Tariff guide\n\n## Peak\nPeak is 16:00-22:00.\n",
                                           encoding="utf-8")
    (tmp_path / "kb/reflow.md").unlink()
    changed = ingest(knowledge, discover(("kb",), tmp_path), tmp_path)
    assert changed.updated == ["kb/tariff.md"] and changed.removed == ["kb/reflow.md"]
    assert knowledge.count() == 3
    assert knowledge.search("peak hours", k=1)[0].heading == "Tariff guide > Peak"


def test_bad_queries_fail_cleanly(store: KnowledgeStore) -> None:
    for bad in ("", "   ", "x" * 2001):
        with pytest.raises(ValueError):
            store.search(bad)
    for k in (0, 21):
        with pytest.raises(ValueError):
            store.search("leak", k=k)
    assert new_store().search("anything") == []


def test_a_store_refuses_a_different_embedder(store: KnowledgeStore) -> None:
    with pytest.raises(ValueError, match="rebuild"):
        KnowledgeStore(store.client, HashEmbedder(dimensions=64), store.collection_name)
    store.embedder = HashEmbedder(dimensions=64)
    store.reset()
    assert store.count() == 0


def _pdf(pages: list[str]) -> bytes:
    """A minimal valid PDF with one line of Helvetica text per page."""
    objects = ["<< /Type /Catalog /Pages 2 0 R >>", ""]
    kids = []
    for text in pages:
        content = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("latin-1")
        objects.append(f"<< /Length {len(content)} >>\nstream\n{content.decode()}\nendstream")
        objects.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                       f"/Contents {len(objects)} 0 R /Resources << /Font << /F1 "
                       f"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> >> >> >>")
        kids.append(f"{len(objects)} 0 R")
    objects[1] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(pages)} >>"
    out, offsets = b"%PDF-1.4\n", []
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n{body}\nendobj\n".encode("latin-1")
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += "".join(f"{offset:010d} 00000 n \n" for offset in offsets).encode()
    trailer = f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>"
    out += f"{trailer}\nstartxref\n{xref}\n%%EOF\n".encode()
    return out


def test_pdf_pages_are_retrievable_with_their_page_number(tmp_path: Path) -> None:
    path = tmp_path / "kb" / "sop.pdf"
    path.parent.mkdir()
    path.write_bytes(_pdf(["Check the capacitor bank fuses on MDB-3.",
                           "Reset the bank and confirm the power factor is above 0.95."]))
    chunks = chunk_pdf(path, "kb/sop.pdf")
    assert [(c.heading, c.page) for c in chunks] == [("page 1", 1), ("page 2", 2)]
    knowledge = new_store()
    ingest(knowledge, discover(("kb",), tmp_path), tmp_path)
    passage = knowledge.search("reset bank power factor", k=1)[0]
    assert (passage.page, passage.citation) == (2, "kb/sop.pdf#p.2")


def test_hash_tokens_keep_meter_ids_and_embedder_choice_is_validated() -> None:
    assert tokens("Check RF-02 and the oven") == ["check", "rf-02", "rf", "02", "oven"]
    vectors = HashEmbedder().embed(["air leak", "air leak", "oven"])
    assert vectors[0] == vectors[1] and vectors[0] != vectors[2]
    assert abs(sum(x * x for x in vectors[0]) - 1.0) < 1e-9
    with pytest.raises(ValueError):
        make_embedder("cloud")
    with pytest.raises(ValueError):
        make_embedder("openai_compatible")


def test_local_model_missing_falls_back_to_hash_with_a_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING, logger="factory_energy.rag.embed"):
        embedder = make_embedder("local", "multilingual-e5-small", model_dir=tmp_path)
    assert isinstance(embedder, HashEmbedder)
    assert "falling back to the hash embedder" in caplog.text and "rebuild" in caplog.text
    with pytest.raises(ValueError, match="unknown local model"):
        make_embedder("local", "gpt-embed", model_dir=tmp_path)  # a typo errors, no fallback


def test_pooling_mean_over_real_tokens_and_cls() -> None:
    states = [[[1.0, 0.0], [3.0, 0.0], [100.0, 100.0]]]  # the third token is padding
    mask = [[1, 1, 0]]
    assert pool(states, mask, "mean") == [[1.0, 0.0]]
    first = pool([[[0.0, 2.0], [5.0, 5.0]]], [[1, 1]], "cls")[0]
    assert first == pytest.approx([0.0, 1.0])


class _Encoding:
    def __init__(self, text: str) -> None:
        self.text, self.ids, self.attention_mask, self.type_ids = text, [1, 2], [1, 1], [0, 0]


class _Tokenizer:
    seen: list[str] = []

    @classmethod
    def from_file(cls, path: str) -> "_Tokenizer":
        return cls()

    def enable_truncation(self, length: int) -> None: ...

    def enable_padding(self) -> None: ...

    def encode_batch(self, texts: list[str]) -> list[_Encoding]:
        _Tokenizer.seen += texts
        return [_Encoding(t) for t in texts]


class _Input:
    def __init__(self, name: str) -> None:
        self.name = name


class _Session:
    fed: list[set[str]] = []

    def __init__(self, path: str, providers: list[str]) -> None:
        self.path = path

    def get_inputs(self) -> list[_Input]:
        return [_Input("input_ids"), _Input("attention_mask"), _Input("token_type_ids")]

    def run(self, outputs: None, feed: dict[str, object]) -> list[object]:
        _Session.fed.append(set(feed))
        return [[[[3.0, 4.0], [0.0, 0.0]]] * len(feed["input_ids"])]  # type: ignore[arg-type]


def test_local_model_uses_prefixes_and_its_pooling(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import onnxruntime
    import tokenizers

    folder = tmp_path / "multilingual-e5-small" / "onnx"
    folder.mkdir(parents=True)
    (folder / "model.onnx").write_bytes(b"")
    (folder.parent / "tokenizer.json").write_text("{}")
    monkeypatch.setattr(tokenizers, "Tokenizer", _Tokenizer)
    monkeypatch.setattr(onnxruntime, "InferenceSession", _Session)
    embedder = make_embedder("local", "multilingual-e5-small", model_dir=tmp_path)
    assert isinstance(embedder, LocalOnnxEmbedder)
    assert embedder.name == "local-multilingual-e5-small"
    vectors = embedder.embed(["air leak"])
    embedder.embed_queries(["where is the leak?"])
    assert _Tokenizer.seen[-2:] == ["passage: air leak", "query: where is the leak?"]
    assert _Session.fed[-1] == {"input_ids", "attention_mask", "token_type_ids"}
    assert vectors[0] == pytest.approx([0.6, 0.8])  # mean over the two real tokens, unit length
