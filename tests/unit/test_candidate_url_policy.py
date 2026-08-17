from scraper.search.url_policy import URLRejectionReason, candidate_url_policy


def test_terminal_url_policy_rejects_listing_and_auth_urls():
    assert candidate_url_policy.rejection_reason(
        "https://arxiv.org/search/cs?searchtype=author&query=Zhang,+W"
    ) == URLRejectionReason.SEARCH_LISTING_URL
    assert candidate_url_policy.rejection_reason(
        "https://europepmc.org/accounts/login"
    ) == URLRejectionReason.AUTHENTICATION_URL


def test_terminal_url_policy_allows_article_url():
    assert candidate_url_policy.is_terminal_source_allowed("https://arxiv.org/abs/2309.15217v2")


def test_terminal_url_policy_keeps_binary_documents_out_of_page_acquisition():
    assert candidate_url_policy.rejection_reason(
        "https://arxiv.org/pdf/2309.15217v2.pdf"
    ) == URLRejectionReason.BINARY_DOCUMENT_URL
