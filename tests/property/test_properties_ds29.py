"""Property, Metamorphic, and Differential Tests for Core Algorithms (§DS-29).

Verifies invariants across entire input domains using Hypothesis:
- Normalization Idempotency & Metamorphic Query Invariance
- Metric Symmetry & Triangle Inequality in SimHash Space
- Permutation Invariance in Deterministic Media Ranking
- Hard Invariant Bounds on Document Chunking
- Differential Oracle Verification against Reference Models
"""

import hashlib
import random
from typing import Any

from hypothesis import example, given, settings
from hypothesis import strategies as st

from scraper.discovery.media_finder import score_and_rank_images
from scraper.domain.document import Document, DocumentProvenance
from scraper.normalization.canonicalizer import canonicalize_url
from scraper.normalization.content_hash import compute_content_hash
from scraper.normalization.near_duplicate import NearDuplicateDetector
from scraper.retrieval.chunking import StructureAwareChunker

# ---------------------------------------------------------------------------
# 1. Canonicalizer Invariants & Metamorphic Properties
# ---------------------------------------------------------------------------


# Safe URL generator
url_alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.~"
url_text = st.text(alphabet=url_alphabet, min_size=1, max_size=30)
url_schemes = st.sampled_from(["http", "https"])
url_domains = st.sampled_from(
    ["example.com", "arxiv.org", "wikipedia.org", "sub.domain.org"]
)
url_paths = st.lists(url_text, min_size=0, max_size=4).map(
    lambda p: "/" + "/".join(p) if p else ""
)


@st.composite
def valid_http_urls(draw):
    scheme = draw(url_schemes)
    domain = draw(url_domains)
    path = draw(url_paths)
    has_query = draw(st.booleans())
    if has_query:
        params = draw(
            st.dictionaries(keys=url_text, values=url_text, min_size=1, max_size=4)
        )
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        return f"{scheme}://{domain}{path}?{qs}"
    return f"{scheme}://{domain}{path}"


@given(url=valid_http_urls())
@settings(max_examples=100, deadline=None)
@example(url="https://arxiv.org/abs/2309.15217v2")
@example(url="https://example.com/a%2Fb/c")
def test_canonicalize_url_idempotency_property(url: str):
    """Property: Canonicalizing an already canonicalized URL is idempotent: f(f(x)) == f(x)."""
    first_pass = canonicalize_url(url)
    second_pass = canonicalize_url(first_pass)
    assert second_pass == first_pass


@given(
    domain=url_domains,
    path=url_paths,
    params=st.lists(
        st.tuples(url_text, url_text), min_size=2, max_size=6, unique_by=lambda x: x[0]
    ),
)
@settings(max_examples=100, deadline=None)
def test_canonicalize_query_ordering_metamorphic_property(
    domain: str, path: str, params: list[tuple]
):
    """Metamorphic: Permuting query parameters yields identical canonical URL."""
    shuffled_params = list(params)
    random.shuffle(shuffled_params)

    qs1 = "&".join(f"{k}={v}" for k, v in params)
    qs2 = "&".join(f"{k}={v}" for k, v in shuffled_params)

    u1 = f"https://{domain}{path}?{qs1}"
    u2 = f"https://{domain}{path}?{qs2}"

    assert canonicalize_url(u1) == canonicalize_url(u2)


# ---------------------------------------------------------------------------
# 2. SimHash & Hamming Distance Metric Properties
# ---------------------------------------------------------------------------


words_st = st.lists(
    st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=2, max_size=10),
    min_size=1,
    max_size=30,
).map(lambda ws: " ".join(ws))


@given(
    h1=st.integers(min_value=0, max_value=2**64 - 1),
    h2=st.integers(min_value=0, max_value=2**64 - 1),
)
@settings(max_examples=100, deadline=None)
def test_hamming_distance_metric_symmetry(h1: int, h2: int):
    """Property: Hamming distance is symmetric: d(x, y) == d(y, x)."""
    d_xy = NearDuplicateDetector.hamming_distance(h1, h2)
    d_yx = NearDuplicateDetector.hamming_distance(h2, h1)
    assert d_xy == d_yx
    assert d_xy >= 0


@given(h1=st.integers(min_value=0, max_value=2**64 - 1))
@settings(max_examples=100, deadline=None)
def test_hamming_distance_identity(h1: int):
    """Property: Hamming distance identity: d(x, x) == 0."""
    assert NearDuplicateDetector.hamming_distance(h1, h1) == 0


@given(
    h1=st.integers(min_value=0, max_value=2**64 - 1),
    h2=st.integers(min_value=0, max_value=2**64 - 1),
    h3=st.integers(min_value=0, max_value=2**64 - 1),
)
@settings(max_examples=100, deadline=None)
def test_hamming_distance_triangle_inequality(h1: int, h2: int, h3: int):
    """Property: Hamming distance satisfies triangle inequality: d(x, z) <= d(x, y) + d(y, z)."""
    d_xz = NearDuplicateDetector.hamming_distance(h1, h3)
    d_xy = NearDuplicateDetector.hamming_distance(h1, h2)
    d_yz = NearDuplicateDetector.hamming_distance(h2, h3)
    assert d_xz <= d_xy + d_yz


@given(text=words_st)
@settings(max_examples=50, deadline=None)
def test_near_duplicate_exact_idempotency(text: str):
    """Property: Registering the exact same document text always detects near-duplicate."""
    detector = NearDuplicateDetector(hamming_threshold=12)
    res1 = detector.register_document("doc_original", text)
    res2 = detector.register_document("doc_duplicate", text)

    assert res1.is_near_duplicate is False
    assert res2.is_near_duplicate is True
    assert res2.duplicate_of_id == "doc_original"


# ---------------------------------------------------------------------------
# 3. Deterministic Media Selection Properties
# ---------------------------------------------------------------------------


candidate_st = st.fixed_dictionaries(
    {
        "url": st.sampled_from(
            [f"https://example.com/images/img_{i}.jpg" for i in range(20)]
        ),
        "caption": st.sampled_from(
            [
                "Laser beam optics",
                "Neural network diagram",
                "Database index structure",
                "Quantum superposition",
            ]
        ),
        "alt": st.sampled_from(["diagram", "photo", "figure", "illustration"]),
        "source_domain": st.sampled_from(["example.com", "science.org"]),
        "width": st.integers(min_value=400, max_value=1600),
        "height": st.integers(min_value=300, max_value=1200),
    }
)


@given(
    candidates=st.lists(
        candidate_st, min_size=1, max_size=10, unique_by=lambda x: x["url"]
    ),
    query=st.sampled_from(["laser optics", "neural network", "database"]),
    min_c=st.integers(min_value=1, max_value=3),
    max_c=st.integers(min_value=3, max_value=8),
)
@settings(max_examples=60, deadline=None)
def test_media_ranking_permutation_invariance_and_score_bounds(
    candidates: list[dict[str, Any]], query: str, min_c: int, max_c: int
):
    """Property: Shuffling candidate inputs yields identical ranked output order due to deterministic tie-break."""
    if min_c > max_c:
        min_c, max_c = max_c, min_c

    ranked1 = score_and_rank_images(
        candidates, query=query, min_count=min_c, max_count=max_c
    )

    # Permuted candidate list
    shuffled_candidates = list(candidates)
    random.shuffle(shuffled_candidates)
    ranked2 = score_and_rank_images(
        shuffled_candidates, query=query, min_count=min_c, max_count=max_c
    )

    assert [x["url"] for x in ranked1] == [x["url"] for x in ranked2]

    # Invariants: score bounds and monotonic sorting
    for i in range(len(ranked1)):
        assert 0.0 <= ranked1[i]["relevance_score"] <= 1.0
        if i > 0:
            assert ranked1[i - 1]["relevance_score"] >= ranked1[i]["relevance_score"]


# ---------------------------------------------------------------------------
# 4. Structure-Aware Chunker Hard Invariant Bounds
# ---------------------------------------------------------------------------


@given(
    paragraph_words=st.lists(
        st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=8),
        min_size=1,
        max_size=300,
    ),
    target_words=st.integers(min_value=50, max_value=200),
)
@settings(max_examples=50, deadline=None)
@example(paragraph_words=["word"] * 250, target_words=100)
def test_chunker_hard_word_bound_property(
    paragraph_words: list[str], target_words: int
):
    """Property: Every emitted chunk strictly respects the configured target_words bound."""
    text = " ".join(paragraph_words)
    chunker = StructureAwareChunker(target_words=target_words)
    doc = Document(
        id="doc_prop",
        title="Property Document",
        source_url="https://example.com/prop",
        canonical_url="https://example.com/prop",
        clean_markdown=text,
        provenance=DocumentProvenance(content_hash="mock_hash"),
    )
    chunks = chunker.chunk_document(doc)
    assert len(chunks) >= 1
    for c in chunks:
        assert c.word_count <= target_words


# ---------------------------------------------------------------------------
# 5. Differential Testing against Pure Python Reference Oracle
# ---------------------------------------------------------------------------


def _reference_content_hash(text: str) -> str:
    """Pure reference SHA-256 oracle over NFKC and whitespace normalized text."""
    import re
    import unicodedata

    if not text:
        return hashlib.sha256(b"").hexdigest()
    nfkc = unicodedata.normalize("NFKC", text)
    sp_norm = re.sub(r"[ \t]+", " ", nfkc)
    nl_norm = re.sub(r"\n+", "\n", sp_norm).strip().lower()
    return hashlib.sha256(nl_norm.encode("utf-8")).hexdigest()


@given(text=st.text(min_size=0, max_size=200))
@settings(max_examples=100, deadline=None)
def test_differential_content_hash_against_reference(text: str):
    """Differential: Production compute_content_hash matches reference oracle behavior."""
    prod_hash = compute_content_hash(text)
    ref_hash = _reference_content_hash(text)
    assert prod_hash == ref_hash
