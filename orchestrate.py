import os
import json
import logging
from collections import defaultdict
from embeddings import generate_embeddings, link_by_similarity
from code2graph import parse_all_files, AdaNode
from req2nodes import parse_requirements, RequirementNode
from github_integration import extract_github_data
from graph_database import Neo4jConnector
from derive_traceability import materialize_traceability
from constants import OUTPUT_DIR
import logging
logging.basicConfig(level=logging.INFO)
logging.getLogger("neo4j").setLevel(logging.WARNING)
os.environ["TRANSFORMERS_VERBOSITY"] = "error"
os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("requests").setLevel(logging.WARNING)
logging.getLogger("huggingface_hub").setLevel(logging.WARNING)
logging.getLogger("sentence_transformers").setLevel(logging.WARNING)

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
    req_nodes, _ = parse_requirements()
    issues, commits, _ = extract_github_data(force_refresh=False)
    ada_by_id = {a.id: a for a in ada_nodes}
    file_text_index = build_file_text_index(ada_nodes)
    all_nodes = ada_nodes + req_nodes
    embeddings, _ = generate_embeddings(all_nodes)
    related_links, _ = link_by_similarity(
        sources=req_nodes,
        targets=ada_nodes,
        embeddings=embeddings,
        threshold=0.00,
        max_links=50,
    )
    relationships = []
    req_to_files = {}
    for req in req_nodes:
        matches = related_links.get(req.id, [])
        file_scores = defaultdict(float)
        for ada_id, vector_score in matches:
            ada = ada_by_id[ada_id]
            file_text = file_text_index.get(ada.file_path, "")
            kw = keyword_score(req.text, file_text)
            combined = 0.7 * vector_score + 0.3 * kw
            relationships.append((
                req.id,
                ada.id,
                "RELATED_TO",
                {
                    "vector_score": vector_score,
                    "keyword_score": kw,
                    "score": combined,
                },
            ))
            file_scores[ada.file_path] = max(
                file_scores[ada.file_path],
                combined,
            )
        ranked_files = sorted(
            file_scores.items(),
            key=lambda x: x[1],
            reverse=True,
        )[:10]
        req_to_files[req.req_id] = [
            {"file_path": f, "score": s}
            for f, s in ranked_files
        ]
    connector = Neo4jConnector()
    try:
        connector.create_constraints()
        connector.insert_ada_nodes(ada_nodes)
        connector.insert_requirements(req_nodes)
        connector.insert_issues(issues)
        connector.insert_commits(commits)
        connector.insert_relationships(relationships)
    finally:
        connector.close()
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out_path = os.path.join(
        OUTPUT_DIR, "req_to_file_top10_hybrid.json"
    )
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(req_to_files, f, indent=2)
    logging.info(f"[OK] Saved req→file mapping → {out_path}")
    materialize_traceability(
        ada_nodes=ada_nodes,
        requirements=req_nodes,
        issues=issues,
        commits=commits,
    )


if __name__ == "__main__":
    main()
