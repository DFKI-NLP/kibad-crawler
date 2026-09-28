"""Fetch paper and author data from the Semantic Scholar Academic Graph (S2AG).

Some things to note:

- If you are using an API key, it must be set in the header x-api-key
    (case-sensitive).
- We have two different IDs for a single paper:
    - paperId - string - The primary way to identify papers when using our
        website or this API
    - corpusId - int64 - A second way to identify papers. Our datasets use
        corpusId when pointing to papers.

https://api.semanticscholar.org/api-docs/graph
"""

from retry import retry

from kibad_crawler.config import MAX_NUM_BATCH_PAPERS, S2_API_KEY
from kibad_crawler.utils import api_call_post

URL_BASE = "https://api.semanticscholar.org/graph/v1"


@retry(tries=3, delay=2)
def batch(
    ids: list[str],
    fields: str = "paperId,corpusId,url,title,abstract,venue,publicationVenue,year,citationCount,isOpenAccess,openAccessPdf,publicationDate,journal,fieldsOfStudy,s2FieldsOfStudy,authors,tldr,publicationTypes,textAvailability",
):
    """Get details for multiple papers at once
    - Fields is a single-value string parameter, not a multi-value one.
    - It is a query parameter, not to be submitted in the POST request's body.

    Limitations:
    - Can only process 500 paper ids at a time.
    - Can only return up to 10 MB of data at a time.
    - Can only return up to 9999 citations at a time.
    - For a list of supported IDs reference the "Details about a paper" endpoint.

    Args:
        ids (list[str]): _description_
        fields (str, optional): A comma-separated list of the fields to be
            returned. See the contents of Response Schema below for a list of
            all available fields that can be returned. The paperId field is
            always returned. If the fields parameter is omitted, only the
            paperId and title will be returned. Defaults to
            "paperId,corpusId,url,title,abstract,venue,publicationVenue,year,citationCount,isOpenAccess,openAccessPdf,publicationDate,journal,fieldsOfStudy,s2FieldsOfStudy,authors,tldr,publicationTypes,textAvailability".

    Returns:
        _type_: _description_
    """
    assert len(ids) <= MAX_NUM_BATCH_PAPERS, "More than 500 paper IDs"

    route = "/paper/batch"
    url = URL_BASE + route
    params = {"fields": fields}
    payload = {"ids": ids}
    response = api_call_post(url=url, params=params, payload=payload, api_key=S2_API_KEY)
    return response.json()
