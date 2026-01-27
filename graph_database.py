import logging
from typing import Dict, List, Tuple
from neo4j import GraphDatabase
from constants import (
    NEO4J_URI,
    NEO4J_USER,
    NEO4J_PASSWORD,
)
import logging
from code2graph import AdaNode
from req2nodes import RequirementNode
from github_integration import GitHubIssue, GitCommit
import logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)
logging.getLogger("neo4j").setLevel(logging.WARNING)

class Neo4jConnector:
    def __init__(self):
        self.driver = GraphDatabase.driver(
            NEO4J_URI,
            auth=(NEO4J_USER, NEO4J_PASSWORD),
        )

    def close(self):
        self.driver.close()

    def _run(self, query: str, rows: List[Dict]):
        if not rows:
            return

        with self.driver.session() as session:
            session.execute_write(
                lambda tx: tx.run(query, rows=rows)
            )

    def create_constraints(self):
        queries = [
            "CREATE CONSTRAINT IF NOT EXISTS FOR (n:AdaNode) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Requirement) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Issue) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Commit) REQUIRE n.id IS UNIQUE",
        ]

        with self.driver.session() as session:
            session.execute_write(
                lambda tx: [tx.run(q) for q in queries]
            )

    def insert_ada_nodes(self, nodes: List[AdaNode]):
        query = """
        UNWIND $rows AS row
        MERGE (n:AdaNode {id: row.id})
        SET n.name = row.name,
            n.type = row.type,
            n.file_path = row.file_path,
            n.line_number = row.line_number,
            n.summary = row.summary
        """
        rows = [
            {
                "id": n.id,
                "name": n.name,
                "type": n.type,
                "file_path": n.file_path,
                "line_number": n.line_number,
                "summary": getattr(n, "summary", ""),
            }
            for n in nodes
        ]
        self._run(query, rows)

    def insert_requirements(self, nodes: List[RequirementNode]):
        query = """
        UNWIND $rows AS row
        MERGE (n:Requirement {id: row.id})
        SET n.req_id = row.req_id,
            n.text = row.text,
            n.file_path = row.file_path
        """
        rows = [n.__dict__ for n in nodes]
        self._run(query, rows)

    def insert_issues(self, nodes: List[GitHubIssue]):
        query = """
        UNWIND $rows AS row
        MERGE (n:Issue {id: row.id})
        SET n.issue_id = row.issue_id,
            n.title = row.title,
            n.body = row.body,
            n.created_at = row.created_at,
            n.updated_at = row.updated_at,
            n.state = row.state
        """
        rows = [
            {
                "id": n.id,
                "issue_id": n.issue_id,
                "title": n.title,
                "body": n.body,
                "created_at": n.created_at,
                "updated_at": n.updated_at,
                "state": n.state,
            }
            for n in nodes
        ]
        self._run(query, rows)

    def insert_commits(self, nodes: List[GitCommit]):
        query = """
        UNWIND $rows AS row
        MERGE (n:Commit {id: row.id})
        SET n.commit_hash = row.commit_hash,
            n.author = row.author,
            n.date = row.date,
            n.message = row.message,
            n.changed_files = row.changed_files
        """
        rows = [
            {
                "id": n.id,
                "commit_hash": n.commit_hash,
                "author": n.author,
                "date": n.date,
                "message": n.message,
                "changed_files": n.changed_files,
            }
            for n in nodes
        ]
        self._run(query, rows)

    def insert_relationships(
        self,
        relationships,
        batch_size: int = 1000,
    ):
        query_template = """
        UNWIND $rows AS row
        MATCH (a {id: row.src})
        MATCH (b {id: row.dst})
        MERGE (a)-[r:%s]->(b)
        SET r += row.props
        """

        grouped = {}
        for src, dst, rel, props in relationships:
            grouped.setdefault(rel, []).append(
                {"src": src, "dst": dst, "props": props or {}}
            )

        with self.driver.session() as session:
            for rel, rows in grouped.items():
                query = query_template % rel
                for i in range(0, len(rows), batch_size):
                    batch = rows[i:i + batch_size]
                    session.run(query, rows=batch)

    def get_node(self, node_id: str) -> Dict | None:
        query = "MATCH (n {id: $id}) RETURN n"
        with self.driver.session() as session:
            record = session.run(query, id=node_id).single()
            return record["n"] if record else None