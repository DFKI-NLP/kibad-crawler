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

from kibad_crawler.config import INTERIM_DATA_DIR, RAW_DATA_DIR

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
                # print(r["paperId"])
                paper_filter.append(r["paperId"])
                # print(f"{i}, {text}")
    end = pendulum.now()
    logger.info(
        f"{len(paper_filter):,} out of {total_papers:,} papers selected in {(end - start).in_words()}"
    )
    return paper_filter


def save_selected_papers(paper_ids: list, query_name: str, release_id: str):
    # papers
    files_path = Path(RAW_DATA_DIR / "semantic_scholar" / "release" / release_id / "papers")
    json_files = files_path.glob("**/*.json")

    # Create the output directory
    output_dir = Path(
        INTERIM_DATA_DIR / "semantic_scholar" / "release" / release_id / "papers" / "query_search"
    )
    output_dir.mkdir(exist_ok=True, parents=True)

    # Filter papers by paper id
    data = []
    for json_file in json_files:
        df = pd.read_json(json_file)
        data.append(df[df["paperId"].isin(paper_ids)])

    # Save selected papers by query name
    df_papers = pd.concat(data).reset_index(drop=True)
    df_papers.to_json(output_dir / f"{query_name}.json", index=False, orient="records")

    logger.info(f'{len(paper_ids):,} papers saved to "{output_dir / f"{query_name}.json"}"')
