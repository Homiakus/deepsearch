from scraper.extraction.document_type import DocumentType, document_type_classifier


def test_document_classifier_rejects_access_denied():
    result = document_type_classifier.classify(
        "https://example.com/article",
        "<html><body><h1>Access Denied</h1><p>Reference #123</p></body></html>",
    )
    assert result.document_type == DocumentType.BLOCK_PAGE
    assert not result.accepted
    assert result.reason_code == "BLOCK_OR_ACCESS_DENIED"


def test_document_classifier_rejects_listing_page():
    result = document_type_classifier.classify(
        "https://arxiv.org/search/cs?searchtype=author&query=Zhang,+W",
        "<html><body>Many results <a href='/abs/1'>Paper</a></body></html>",
        title="Search results",
    )
    assert result.document_type == DocumentType.SEARCH_LISTING
    assert not result.accepted


def test_document_classifier_accepts_substantive_document():
    result = document_type_classifier.classify(
        "https://arxiv.org/abs/2309.15217v2",
        "<html><head><title>Ragas</title></head><body>"
        + ("Substantive evidence. " * 20)
        + "</body></html>",
        title="Ragas: Automated Evaluation of Retrieval Augmented Generation",
    )
    assert result.document_type == DocumentType.DOCUMENT
    assert result.accepted


def test_document_classifier_does_not_treat_article_navigation_as_login():
    result = document_type_classifier.classify(
        "https://arxiv.org/abs/2309.15217v2",
        "<html><body><nav>Log in | Sign in</nav><h1>Ragas</h1>"
        + ("Substantive evidence. " * 100)
        + "</body></html>",
        title="Ragas: Automated Evaluation of Retrieval Augmented Generation",
    )
    assert result.document_type == DocumentType.DOCUMENT
    assert result.accepted
