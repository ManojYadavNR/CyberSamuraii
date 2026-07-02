import numpy as np

from schemas.fusion import Entity
from services.fusion_engine import _merge_metadata, deduplicate_entities
from services.json_utils import is_empty_value


def test_is_empty_value_numpy_array():
    assert is_empty_value(np.array([]))
    assert not is_empty_value(np.array([1.0, 2.0]))


def test_merge_metadata_numpy_embedding_does_not_crash():
    existing = {"embedding_vector": np.array([1.0, 2.0], dtype=np.float32)}
    incoming = {"platform": "github.com", "embedding_vector": np.array([], dtype=np.float32)}
    merged = _merge_metadata(existing, incoming, "reverse_image")
    assert merged["platform"] == "github.com"
    assert merged["embedding_vector"] == [1.0, 2.0]


def test_deduplicate_entities_with_numpy_metadata():
    a = Entity(
        type="image",
        value="https://example.org/a.jpg",
        sources=["seed"],
        metadata={"embedding_vector": np.zeros(512, dtype=np.float32).tolist()},
    )
    b = Entity(
        type="image",
        value="https://example.org/a.jpg",
        sources=["hop"],
        metadata={"embedding_vector": np.array([], dtype=np.float32), "match_type": "similar"},
    )
    out = deduplicate_entities([a, b])
    assert len(out) == 1
    assert out[0].metadata.get("match_type") == "similar"
