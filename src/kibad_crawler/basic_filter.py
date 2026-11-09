"""Filter Semantic Scholar paper metadata using configured search queries.

Search titles and abstracts directly in JSON files or through a SQLite index
managed by sifts, and save matching paper records as JSON for each query.
"""

from pathlib import Path
from typing import Any

from loguru import logger
import pandas as pd
import pendulum
from pyparsing import (
    CaselessLiteral,
    Word,
    alphanums,
    infix_notation,
    opAssoc,
    quotedString,
    removeQuotes,
)
import sifts  # type: ignore
from sifts.core import CollectionBase  # type: ignore
from tqdm import tqdm

from kibad_crawler.config import INTERIM_DATA_DIR, RAW_DATA_DIR
from kibad_crawler.search_queries import ALL_SEARCH_QUERIES, Query

and_ = CaselessLiteral("and")
or_ = CaselessLiteral("or")
not_ = CaselessLiteral("not")
search_term = Word(alphanums) | quotedString.set_parse_action(removeQuotes)
search_expression = infix_notation(
    search_term,
    [
        (not_, 1, opAssoc.RIGHT),
        (and_, 2, opAssoc.LEFT),
        (or_, 2, opAssoc.LEFT),
    ],
)


def get_processing_or_steps(query_plain_text: str) -> list[Any]:
    """Returns the OR keywords in a list of lists.

    Args:
        query_plain_text (str): Plain text query using AND and OR operators.

    Returns:
        (list[list | str]): A list of lists with OR keywords in each list
            separated by 'and' keywords.
    """
    query_parsed = search_expression.parse_string(query_plain_text)[0]

    processing_steps: Any = []
    for group in query_parsed:
        if not isinstance(group, str):
            processing_steps.append([x for x in group if x != "or"])
        else:
            processing_steps.append(group)

    processing_or_steps = [x for x in processing_steps if isinstance(x, list)]
    return processing_or_steps


def get_papers_from_search(query: str, files_path: Path) -> list:
    """Evaluate all the papers in a directory against a single query search."""
    # parse OR operators in the query
    processing_or_steps = get_processing_or_steps(query_plain_text=query)

    # Get all the JSON files with metadata
    json_files = files_path.glob("**/*.json")

    logger.info(f"Processing files in '{files_path}'")

    total_papers = 0
    paper_filter = []
    start = pendulum.now()
    # for each paper on each metadata file apply query search
    for json_file in json_files:
        df = pd.read_json(json_file)
        df = df[["paperId", "title", "abstract"]]
        total_papers += df.shape[0]

        for i, r in df.iterrows():
            text = f"{r['title'].strip()} {r['abstract'].strip() if r['abstract'] else ""}"

            check_result = []
            for step in processing_or_steps:
                # TODO implement '*' and '?' wildcards for the search
                check_result.append(
                    any(word.replace("*", "").lower() in text.lower() for word in step)
                )

            result = all(check_result)
            if result:
                paper_filter.append(r["paperId"])
    end = pendulum.now()
    logger.info(
        f"{len(paper_filter):,} out of {total_papers:,} papers selected in {(end - start).in_words()}"
    )
    return paper_filter


def save_selected_papers(paper_ids: list, query: Query, files_path: Path, output_dir: Path):
    """Save to disk a list of papers in JSON format.

    Args:
        paper_ids (list): IDs of the papers to be saved.
        query (Query): Query to include its name to include in the JSON file.
        files_path (Path): Directory to find JSON files with paper metadata.
    """
    # papers
    json_files = files_path.glob("**/*.json")

    # Filter papers by paper id
    data = []
    for json_file in json_files:
        df = pd.read_json(json_file)
        data.append(df[df["paperId"].isin(paper_ids)])

    # Save selected papers by query name
    df_papers = pd.concat(data).reset_index(drop=True)
    df_papers.to_json(
        output_dir / f"{query.id} - {query.name}.json", index=False, orient="records"
    )

    output_file_path = output_dir / f"{query.id} - {query.name}.json"
    logger.info(f'{len(paper_ids):,} "{query.name}" papers saved to "{output_file_path}"')


def _check_papers_exist(release_id: str) -> bool:
    """Check whether the directory exists or not. Returns False if does not
    exists and True if it does.

    Args:
        release_id (str): Release id.

    Returns:
        bool: True if directory exists.
    """
    files_path = Path(RAW_DATA_DIR / "semantic_scholar" / "release" / release_id / "papers")
    if not files_path.exists():
        logger.info(f"'{release_id}' no papers found in {files_path}")
        logger.warning(
            "Please download paper metadata first using `uv run kibad-crawler download-paper-metadata`"
        )
        return False
    return True


# sifts


def load_documents_to_database_from_path(files_path: str | Path) -> CollectionBase | None:
    """Load documents (title + abstract) to an sqlite database.

    Args:
        release_id (str): Release to identify the location of the papers.

    Returns:
        (CollectionBase): Database with papers loaded.
    """
    files_path = Path(files_path)
    if not files_path.exists():
        logger.warning(f"Directory {files_path} does not exists.")
    json_files = list(files_path.glob("**/*.json"))
    logger.info(f"Processing files in '{files_path}'")

    database_path = files_path / "database"
    database_path.mkdir(parents=True, exist_ok=True)
    if (database_path / "papers.db").exists():
        (database_path / "papers.db").unlink()

    collection = sifts.Collection(
        db_url=f"sqlite:///{database_path / 'papers.db'}",
        name="papers",
    )

    start = pendulum.now()
    total_papers = 0
    for json_file in tqdm(json_files, total=len(json_files)):
        df = pd.read_json(json_file)
        df = df[["paperId", "title", "abstract"]]
        total_papers += df.shape[0]

        for _, r in df.iterrows():
            text = f"{r['title'].strip()} {r['abstract'].strip() if r['abstract'] else ""}"

            collection.add(
                contents=[text],
                ids=[r["paperId"]],
            )
    end = pendulum.now()
    duration = end - start
    logger.info(
        f"{total_papers:,} papers loaded to database '{database_path / "papers.db"}' in {duration.in_words()}"
    )
    return collection


def load_documents_to_database(release_id: str) -> CollectionBase | None:
    """Load documents (title + abstract) to an sqlite database.

    Args:
        release_id (str): Release to identify the location of the papers.

    Returns:
        (CollectionBase): Database with papers loaded.
    """
    files_path = Path(RAW_DATA_DIR / "semantic_scholar" / "release" / f"{release_id}" / "papers")
    if not _check_papers_exist(release_id=release_id):
        return None

    json_files = list(files_path.glob("**/*.json"))
    logger.info(f"Processing files in '{files_path}'")

    database_path = (
        INTERIM_DATA_DIR / "semantic_scholar" / "release" / f"{release_id}" / "papers" / "database"
    )
    database_path.mkdir(parents=True, exist_ok=True)
    if (database_path / "papers.db").exists():
        (database_path / "papers.db").unlink()

    collection = sifts.Collection(
        db_url=f"sqlite:///{database_path / 'papers.db'}",
        name="papers",
    )

    start = pendulum.now()
    total_papers = 0
    for json_file in tqdm(json_files, total=len(json_files)):
        df = pd.read_json(json_file)
        df = df[["paperId", "title", "abstract"]]
        total_papers += df.shape[0]

        for _, r in df.iterrows():
            text = f"{r['title'].strip()} {r['abstract'].strip() if r['abstract'] else ""}"

            collection.add(
                contents=[text],
                ids=[r["paperId"]],
            )
    end = pendulum.now()
    duration = end - start
    logger.info(
        f"{total_papers:,} papers loaded to database '{release_id}.db' in {duration.in_words()}"
    )
    return collection


def get_papers_from_search_with_sifts(
    query: Query, collection: CollectionBase, top_n: int | None = None
):
    """Returns a list with papers that pass the filter.

    The results are sorted by `rank` which is similar to the bm25_function.
    https://www.sqlite.org/fts5.html#the_bm25_function
    "The better the match, the numerically smaller the [rank] value returned."

    Args:
        query (Query): Query with keywords and logic operators to search in papers.
        collection (CollectionBase): Database.
        top_n (int | None, optional): How many papers to return. Defaults to None.

    Returns:
        (list): Paper ids of the papers that pass the filter.
    """
    results = collection.query(query.query)
    df = pd.DataFrame(results["results"]).sort_values(by=["rank"]).reset_index(drop=True)
    paper_ids = df["id"].to_list()[: top_n or df.shape[0]]
    logger.info(
        f'{len(paper_ids):,} papers out of {results["total"]:,} results from {collection.count():,} papers in the database for {query.name}'
    )
    return paper_ids


def execute_all_search_queries_sift(release_id: str, release_diff: str | None = None):
    """Run the string searches using a SQLite database with sifts.

    Args:
        release_id (str): Release version from Semantic Scholar with format
            'YYYY-MM-DD'.
    """
    if release_diff:
        files_path = Path(
            RAW_DATA_DIR
            / "semantic_scholar"
            / "release"
            / release_id
            / "diffs"
            / f"{release_diff}_to_{release_id}"
            / "papers"
        )
        output_dir = Path(
            INTERIM_DATA_DIR
            / "semantic_scholar"
            / "release"
            / release_id
            / "diffs"
            / f"{release_diff}_to_{release_id}"
            / "papers"
            / "sifts"
        )
    else:
        files_path = Path(
            RAW_DATA_DIR / "semantic_scholar" / "release" / f"{release_id}" / "papers"
        )
        output_dir = Path(
            INTERIM_DATA_DIR / "semantic_scholar" / "release" / release_id / "papers" / "sifts"
        )

    collection = load_documents_to_database_from_path(files_path=files_path)

    # Create the output directory
    output_dir.mkdir(exist_ok=True, parents=True)
    for query in ALL_SEARCH_QUERIES:
        papers = get_papers_from_search_with_sifts(query=query, collection=collection)  # type: ignore
        save_selected_papers(
            paper_ids=papers, query=query, files_path=files_path, output_dir=output_dir
        )
    #     elif files_path:
    #     output_dir = Path(files_path) / "sifts"
    #     output_dir.mkdir(exist_ok=True, parents=True)
    #     for query in ALL_SEARCH_QUERIES:
    #         papers = get_papers_from_search_with_sifts(query=query, collection=collection)
    #         save_selected_papers(
    #             paper_ids=papers, query=query, release_id=release_id, output_dir=output_dir
    #         )
    # else:
    #     collection = None
    if collection is None:
        logger.warning("No release nor path passed.")
        return

    # Create the output directory
    # output_dir = Path(
    #     INTERIM_DATA_DIR / "semantic_scholar" / "release" / release_id / "papers" / "sifts"
    # )
    # output_dir.mkdir(exist_ok=True, parents=True)
    # for query in ALL_SEARCH_QUERIES:
    #     papers = get_papers_from_search_with_sifts(query=query, collection=collection)
    #     save_selected_papers(
    #         paper_ids=papers, query=query, release_id=release_id, output_dir=output_dir
    #     )
    logger.info(
        f"String searches finished. Use 'uv run kibad-crawler download-open-access-files {output_dir}' to download open-access PDF files"
    )
