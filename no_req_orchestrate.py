import os
import json
import logging
from collections import defaultdict
from embeddings import generate_embeddings, link_by_similarity
from code2graph import parse_all_files, AdaNode
from github_integration import extract_github_data
from graph_database import Neo4jConnector
from derive_traceability import materialize_traceability
from constants import OUTPUT_DIR
import logging
logging.basicConfig(level=logging.INFO)
logging.getLogger("neo4j").setLevel(logging.WARNING)

def build_file_text_index(ada_nodes: list[AdaNode]) -> dict[str, str]:
   file_text: dict[str, str] = defaultdict(str)

    for n in ada_nodes:
        parts = [
            n.name,
            n.type,
            getattr(n, "body", ""),
            getattr(n, "text", ""),
        ]
        file_text[n.file_path] += " " + " ".join(p for p in parts if p)

    return {
        path: text.lower()
        for path, text in file_text.items()
    }


def keyword_score(req_text: str, file_text: str) -> float:
    req_words = set(req_text.lower().split())
    file_words = set(file_text.split())
    if not req_words:
        return 0.0
    return len(req_words & file_words) / len(req_words)

def main():
    ada_nodes = parse_all_files()
    issues, commits, _ = extract_github_data(force_refresh=False)
    ada_by_id = {a.id: a for a in ada_nodes}
    file_text_index = build_file_text_index(ada_nodes)
    connector = Neo4jConnector()
    try:
        connector.create_constraints()
        connector.insert_ada_nodes(ada_nodes)
        connector.insert_issues(issues)
        connector.insert_commits(commits)
    finally:
        connector.close()
    materialize_traceability(
        ada_nodes=ada_nodes,
        requirements=None,
        issues=issues,
        commits=commits,
    )
if __name__ == "__main__":
    main()