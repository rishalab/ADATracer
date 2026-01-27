import re
from collections import defaultdict
from typing import List, Tuple, Dict
from pathlib import Path
from tqdm import tqdm
from code2graph import AdaNode
from req2nodes import RequirementNode
from github_integration import GitHubIssue, GitCommit
from graph_database import Neo4jConnector
import logging
logging.basicConfig(level=logging.INFO)
logging.getLogger("neo4j").setLevel(logging.WARNING)

def normalize_path_basename(path: str) -> str:
    return Path(path.replace("\\", "/")).name.lower()

def derive_traceability(
    ada_nodes: List[AdaNode],
    requirements: List[RequirementNode],
    issues: List[GitHubIssue],
    commits: List[GitCommit],
) -> List[Tuple[str, str, str, Dict]]:

    relationships: List[Tuple[str, str, str, Dict]] = []
    ada_by_basename: Dict[str, List[AdaNode]] = defaultdict(list)
    for node in ada_nodes:
        key = normalize_path_basename(node.file_path)
        ada_by_basename[key].append(node)
    print("[INFO] Deriving CHANGES (Commit → AdaNode)")
    for commit in tqdm(commits, desc="Commit → AdaNode"):
        for changed_file in commit.changed_files:
            key = normalize_path_basename(changed_file)
            for ada in ada_by_basename.get(key, []):
                relationships.append((
                    commit.id,
                    ada.id,
                    "CHANGES",
                    {},
                ))
    print("[INFO] Deriving IMPACTS (Issue → AdaNode)")
    for issue in tqdm(issues, desc="Issue → AdaNode"):
        text = f"{issue.title} {issue.body}".lower()
        for basename, nodes in ada_by_basename.items():
            if basename in text:
                for ada in nodes:
                    relationships.append((
                        issue.id,
                        ada.id,
                        "IMPACTS",
                        {},
                    ))
    print("[INFO] Deriving ADDRESSES (Commit → Issue)")
    issue_by_number = {str(i.issue_id): i for i in issues}
    for commit in tqdm(commits, desc="Commit → Issue"):
        for iid in re.findall(r"#(\d+)", commit.message):
            issue = issue_by_number.get(iid)
            if issue:
                relationships.append((
                    commit.id,
                    issue.id,
                    "ADDRESSES",
                    {},
                ))

    return relationships

def materialize_traceability(
    ada_nodes: List[AdaNode],
    requirements: List[RequirementNode],
    issues: List[GitHubIssue],
    commits: List[GitCommit],
):
    relationships = derive_traceability(
        ada_nodes=ada_nodes,
        requirements=requirements,
        issues=issues,
        commits=commits,
    )

    print(f"[INFO] Persisting {len(relationships)} relationships")

    connector = Neo4jConnector()
    try:
        connector.insert_relationships(relationships)
    finally:
        connector.close()

    print("[OK] Traceability derivation complete")


if __name__ == "__main__":
    print(
        "This module is intended to be called from an orchestrator.\n"
        "It does not load data by itself."
    )

