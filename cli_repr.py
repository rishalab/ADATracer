import shlex
from collections import defaultdict
from typing import Dict, List, Tuple
from code2graph import parse_all_files, AdaNode
from req2nodes import RequirementNode
from embeddings import generate_embeddings, link_by_similarity
from graph_database import Neo4jConnector
import logging
import os
logging.basicConfig(level=logging.INFO)
logging.getLogger("neo4j").setLevel(logging.WARNING)
os.environ["TRANSFORMERS_VERBOSITY"] = "error"
os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("requests").setLevel(logging.WARNING)
logging.getLogger("huggingface_hub").setLevel(logging.WARNING)
logging.getLogger("sentence_transformers").setLevel(logging.WARNING)
TOP_K = 10


def build_file_text_index(ada_nodes: List[AdaNode]) -> Dict[str, str]:
    file_text: Dict[str, str] = defaultdict(str)
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


class REPLState:
    def __init__(self):
        self.requirement: RequirementNode | None = None
        self.results: List[Tuple[str, float, float, float]] = []


def print_help():
    print("""
Commands:
  help                          Show this help
  exit | quit                   Exit REPL

Requirement analysis:
  req "<text>"                  Analyze requirement text
  reqfile <path>                Analyze requirement from file

Result exploration:
  list                          List last results
  show <n>                      Show AdaNode details for rank n
  node <node_id>                Show AdaNode details by id

Git traceability (Neo4j):
  commits <node_id>             Show commits touching node
  issues <node_id>              Show issues impacting node
""")



def repl():
    print("ADATracer Interactive CLI (Hybrid Scoring, File-Level Keywords)")
    print("Type 'help' for commands\n")
    ada_nodes: List[AdaNode] = parse_all_files()
    ada_by_id = {a.id: a for a in ada_nodes}
    print(f"[INFO] Loaded {len(ada_nodes)} Ada nodes")
    file_text_index = build_file_text_index(ada_nodes)
    embeddings, _ = generate_embeddings(ada_nodes)
    state = REPLState()
    connector: Neo4jConnector | None = None

    while True:
        try:
            raw = input("adatrcer> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not raw:
            continue

        args = shlex.split(raw)
        cmd = args[0]

        if cmd in ("exit", "quit"):
            break

        if cmd == "help":
            print_help()
            continue
      
        if cmd == "req":
            text = " ".join(args[1:])
            req = RequirementNode("REPL", text, "interactive")
            req_emb, _ = generate_embeddings([req])
            embeddings.update(req_emb)
            links, _ = link_by_similarity(
                sources=[req],
                targets=ada_nodes,
                embeddings=embeddings,
                threshold=0.0,
                max_links=50,
            )
            scored = []
            for ada_id, vector_score in links.get(req.id, []):
                ada = ada_by_id[ada_id]
                file_text = file_text_index.get(ada.file_path, "")
                kw = keyword_score(text, file_text)
                combined = 0.7 * vector_score + 0.3 * kw
                scored.append((ada_id, combined, vector_score, kw))
            scored.sort(key=lambda x: x[1], reverse=True)
            scored = scored[:TOP_K]
            state.requirement = req
            state.results = scored

            print("\nRank | Combined | Vector | Keyword | AdaNode ID")
            print("-" * 80)
            for i, (nid, c, v, k) in enumerate(scored, 1):
                print(f"{i:>4} | {c:>8.3f} | {v:>6.3f} | {k:>7.3f} | {nid}")
            continue

        if cmd == "reqfile":
            path = args[1]
            with open(path, encoding="utf-8") as f:
                text = f.read().strip()
            raw = f'req "{text}"'
            args = shlex.split(raw)
            cmd = "req"
            continue

        if cmd == "list":
            if not state.results:
                print("No results")
                continue
            for i, (nid, c, v, k) in enumerate(state.results, 1):
                print(f"{i:>2}. {nid} (combined={c:.3f})")
            continue

        if cmd == "show":
            idx = int(args[1]) - 1
            nid, c, v, k = state.results[idx]
            node = ada_by_id[nid]

            print("\nAdaNode")
            print("-" * 40)
            print(f"ID            : {node.id}")
            print(f"Type          : {node.type}")
            print(f"Name          : {node.name}")
            print(f"File          : {node.file_path}")
            print(f"Line          : {node.line_number}")
            print(f"Combined Score: {c:.3f}")
            print(f"Vector Score  : {v:.3f}")
            print(f"Keyword Score : {k:.3f}")
            continue

        if cmd == "node":
            nid = args[1]
            node = ada_by_id.get(nid)
            if not node:
                print("Node not found")
                continue
            print(node)
            continue

        if cmd in ("commits", "issues"):
            if connector is None:
                connector = Neo4jConnector()

            nid = args[1]

            if cmd == "commits":
                q = """
                MATCH (c:Commit)-[:CHANGES]->(a:AdaNode {id:$id})
                RETURN c.commit_hash AS hash, c.message AS msg
                """
            else:
                q = """
                MATCH (i:Issue)-[:IMPACTS]->(a:AdaNode {id:$id})
                RETURN i.issue_id AS id, i.title AS title
                """

            with connector.driver.session() as session:
                rows = session.run(q, id=nid).data()

            if not rows:
                print("No results")
                continue

            print()
            for r in rows:
                print(" - ", " | ".join(str(v) for v in r.values()))
            continue

        print("Unknown command. Type 'help'.")

    if connector:
        connector.close()

    print("Bye.")


if __name__ == "__main__":
    repl()

