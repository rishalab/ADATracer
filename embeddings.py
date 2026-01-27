import os
import logging
os.environ["TRANSFORMERS_VERBOSITY"] = "error"
os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
for name in [
    "urllib3",
    "requests",
    "huggingface_hub",
    "huggingface_hub.file_download",
    "sentence_transformers",
    "transformers",
    "filelock",
]:
    logging.getLogger(name).setLevel(logging.WARNING)
    logging.getLogger(name).propagate = False
import time
import numpy as np
from typing import Dict, List, Tuple, Union
from tqdm import tqdm
from sentence_transformers import SentenceTransformer

from constants import MAX_TOKENS
from code2graph import AdaNode
from req2nodes import RequirementNode
from github_integration import GitHubIssue, GitCommit
logging.basicConfig(
    level=logging.INFO,   # <-- critical
    format="%(asctime)s [%(levelname)s] %(message)s",
)

Node = Union[AdaNode, RequirementNode, GitHubIssue, GitCommit]

_MODEL: SentenceTransformer | None = None
def _get_model() -> SentenceTransformer:
    global _MODEL
    if _MODEL is None:
        _MODEL = SentenceTransformer("all-MiniLM-L6-v2")
    return _MODEL
def _node_text(node: Node) -> str:
    MAX_BODY_CHARS = 2000
    if isinstance(node, AdaNode):
        parts = [node.type, node.name]

        body = getattr(node, "body", None)
        if body:
            parts.append(body)

        return ": ".join(str(p) for p in parts if p)
    if isinstance(node, RequirementNode):
        return f"Requirement {node.req_id}: {node.text}"
    if isinstance(node, GitHubIssue):
        body = node.body or ""
        return f"Issue {node.issue_id}: {node.title} {body}"
    if isinstance(node, GitCommit):
        return f"Commit {node.commit_hash[:8]}: {node.message}"
    raise TypeError(f"Unsupported node type: {type(node)}")

def generate_embeddings(
    nodes: List[Node],
) -> Tuple[Dict[str, np.ndarray], Dict[str, Dict]]:
    """
    Generate embeddings for a list of nodes.

    Returns:
      embeddings: node_id -> embedding vector
      failures  : node_id -> failure metadata
    """

    start = time.time()
    model = _get_model()

    embeddings: Dict[str, np.ndarray] = {}
    failures: Dict[str, Dict] = {}

    for node in tqdm(nodes, desc="Embedding nodes"):
        node_id = node.id
        text = _node_text(node)

        truncated = False
        if len(text) > MAX_TOKENS:
            text = text[:MAX_TOKENS]
            truncated = True

        try:
            vec = model.encode(
                text,
                convert_to_numpy=True,
                show_progress_bar=False,  # IMPORTANT
            )
            embeddings[node_id] = vec

            if truncated:
                failures[node_id] = {
                    "type": "truncated",
                    "original_length": len(_node_text(node)),
                }

        except Exception as e:
            failures[node_id] = {
                "type": "embedding_failed",
                "error": str(e),
            }
            logging.debug(f"Embedding failed for {node_id}: {e}")

    logging.debug(
        f"Generated embeddings for {len(embeddings)} nodes "
        f"with {len(failures)} issues in {time.time() - start:.2f}s"
    )

    return embeddings, failures

def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))

def link_by_similarity(
    sources: List[Node],
    targets: List[Node],
    embeddings: Dict[str, np.ndarray],
    threshold: float,
    max_links: int,
) -> Tuple[Dict[str, List[Tuple[str, float]]], Dict[str, Dict]]:

    links: Dict[str, List[Tuple[str, float]]] = {}
    stats = {
        "comparisons": 0,
        "links_created": 0,
        "skipped_missing_embedding": 0,
    }
    for src in sources:
        src_id = src.id
        src_vec = embeddings.get(src_id)
        if src_vec is None:
            stats["skipped_missing_embedding"] += 1
            continue
        scored: List[Tuple[str, float]] = []
        for tgt in targets:
            if tgt.id == src_id:
                continue
            tgt_vec = embeddings.get(tgt.id)
            if tgt_vec is None:
                stats["skipped_missing_embedding"] += 1
                continue
            stats["comparisons"] += 1
            sim = cosine_similarity(src_vec, tgt_vec)
            if sim >= threshold:
                scored.append((tgt.id, sim))
        scored.sort(key=lambda x: x[1], reverse=True)
        if max_links > 0:
            scored = scored[:max_links]
        links[src_id] = scored
        stats["links_created"] += len(scored)
    return links, stats
