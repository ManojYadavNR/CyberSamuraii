import numpy as np

from services.json_utils import embedding_nonempty, normalize_embedding


def test_embedding_nonempty_rejects_empty_numpy_array():
    assert not embedding_nonempty(np.array([]))
    assert not embedding_nonempty(None)
    assert not embedding_nonempty([])


def test_embedding_nonempty_accepts_valid_embedding():
    emb = np.random.randn(512).astype(np.float32)
    assert embedding_nonempty(emb)
    assert embedding_nonempty(emb.tolist())


def test_sequence_nonempty_rejects_empty_numpy_array():
    from services.json_utils import is_empty_value, sequence_nonempty

    assert not sequence_nonempty(np.array([]))
    assert sequence_nonempty(np.array([1.0]))
    assert is_empty_value(np.array([]))
    assert not is_empty_value(np.array([1.0]))


def test_normalize_embedding_returns_list():
    emb = np.array([1.0, 2.0, 3.0], dtype=np.float32)
    out = normalize_embedding(emb)
    assert out == [1.0, 2.0, 3.0]
