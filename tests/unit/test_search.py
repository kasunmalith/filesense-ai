import struct

from filesense_ai.db.repositories import Repository
from filesense_ai.indexing.service import IndexingService
from filesense_ai.search.hybrid import hybrid_search
from filesense_ai.search.semantic import index_text_embeddings, semantic_search


class FakeEmbeddingBackend:
    model_id = "test/fake-v1"

    def load(self):
        return None

    def embed_documents(self, texts):
        return [self.vector(text) for text in texts]

    def embed_queries(self, texts):
        return [self.vector(text) for text in texts]

    @staticmethod
    def vector(text):
        lower = text.lower()
        if any(word in lower for word in ("hotel", "lodging", "accommodation", "inn")):
            return [1.0, 0.0]
        if any(word in lower for word in ("invoice", "payment", "billing")):
            return [0.0, 1.0]
        return [0.5, 0.5]


def test_semantic_index_and_hybrid_ranking(database, tmp_path):
    root = tmp_path / "docs"
    root.mkdir()
    (root / "stay.txt").write_text("lodging reservation for the inn", encoding="utf-8")
    (root / "bill.txt").write_text("invoice payment for office supplies", encoding="utf-8")
    root_id = Repository(database.connection).add_root(root)
    IndexingService(database.connection).index_root(root_id)
    backend = FakeEmbeddingBackend()
    assert index_text_embeddings(database.connection, backend) == 2
    hits = semantic_search(database.connection, "hotel accommodation", backend)
    assert hits[0].filename == "stay.txt"
    assert hits[0].reasons == ("similar meaning",)
    hybrid = hybrid_search(database.connection, "hotel accommodation", backend)
    assert hybrid[0].filename == "stay.txt"
    assert "matching words" in hybrid[0].reasons or "similar meaning" in hybrid[0].reasons


def test_dimension_mismatch_is_ignored_and_model_switch_rebuilds(database, tmp_path):
    root = tmp_path / "docs"
    root.mkdir()
    (root / "one.txt").write_text("hotel accommodation", encoding="utf-8")
    root_id = Repository(database.connection).add_root(root)
    IndexingService(database.connection).index_root(root_id)
    backend = FakeEmbeddingBackend()
    index_text_embeddings(database.connection, backend)
    with database.connection:
        database.connection.execute(
            "UPDATE chunks SET embedding_blob=?,embedding_model='other/model'",
            (struct.pack("ff", 1.0, 0.0),),
        )
    assert index_text_embeddings(database.connection, backend) == 1
    assert semantic_search(database.connection, "hotel", backend)


def test_empty_and_stopword_queries_are_safe(database):
    assert semantic_search(database.connection, "   ", FakeEmbeddingBackend()) == []
    assert hybrid_search(database.connection, '!!!*" OR') == []
