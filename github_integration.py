import json
import logging
import os
import requests
from typing import Dict, List, Tuple
from tqdm import tqdm
from constants import (
    GITHUB_API_TOKEN,
    GITHUB_REPO_OWNER,
    GITHUB_REPO_NAME,
    OUTPUT_DIR,
)
from constants import GITHUB_API_TOKEN
import logging

ISSUES_FILE = os.path.join(OUTPUT_DIR, "issues.json")
COMMITS_FILE = os.path.join(OUTPUT_DIR, "commits.json")
os.makedirs(OUTPUT_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)
logging.getLogger("neo4j").setLevel(logging.WARNING)

class GitHubIssue:
    def __init__(
        self,
        issue_id: int,
        title: str,
        body: str,
        created_at: str,
        updated_at: str,
        state: str,
    ):
        self.issue_id = int(issue_id)
        self.title = title
        self.body = body or ""
        self.created_at = created_at
        self.updated_at = updated_at
        self.state = state

        self.id = f"issue::{self.issue_id}"
        self.text = f"{self.title} {self.body}".strip()

    def to_dict(self) -> Dict:
        return {
            "issue_id": self.issue_id,
            "title": self.title,
            "body": self.body,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "state": self.state,
        }

    @staticmethod
    def from_dict(d: Dict) -> "GitHubIssue":
        issue_id = d.get("issue_id") or d.get("number")
        if issue_id is None:
            raise ValueError(f"Missing issue_id/number in cache: {d.keys()}")

        return GitHubIssue(
            issue_id=issue_id,
            title=d.get("title", ""),
            body=d.get("body", ""),
            created_at=d.get("created_at", ""),
            updated_at=d.get("updated_at", ""),
            state=d.get("state", ""),
        )

    def __repr__(self):
        return f"Issue #{self.issue_id}: {self.title}"


class GitCommit:
    def __init__(
        self,
        commit_hash: str,
        author: str,
        date: str,
        message: str,
        changed_files: List[str],
    ):
        self.commit_hash = commit_hash
        self.author = author
        self.date = date
        self.message = message
        self.changed_files = changed_files

        self.id = f"commit::{self.commit_hash}"
        self.text = self.message

    def to_dict(self) -> Dict:
        return {
            "commit_hash": self.commit_hash,
            "author": self.author,
            "date": self.date,
            "message": self.message,
            "changed_files": self.changed_files,
        }

    @staticmethod
    def from_dict(d: Dict) -> "GitCommit":
        commit_hash = d.get("commit_hash") or d.get("sha")
        if commit_hash is None:
            raise ValueError(f"Missing commit hash in cache: {d.keys()}")
        return GitCommit(
            commit_hash=commit_hash,
            author=d.get("author", ""),
            date=d.get("date", ""),
            message=d.get("message", ""),
            changed_files=d.get("changed_files", []),
        )

    def __repr__(self):
        return f"Commit {self.commit_hash[:8]}: {self.message}"


def _github_headers() -> Dict[str, str]:
    if not GITHUB_API_TOKEN:
        raise RuntimeError("GITHUB_API_TOKEN not set")
    return {
        "Authorization": f"token {GITHUB_API_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
    }


def _save_json(path: str, data: List[Dict]):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _load_json(path: str) -> List[Dict]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def fetch_github_issues() -> Tuple[List[GitHubIssue], Dict]:
    issues: List[GitHubIssue] = []
    failed: Dict = {}
    headers = _github_headers()
    page = 1
    with tqdm(desc="Fetching issues (pages)", unit="page") as pbar:
        while True:
            url = f"https://api.github.com/repos/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}/issues"
            params = {"state": "all", "per_page": 100, "page": page}
            try:
                r = requests.get(url, headers=headers, params=params)
                r.raise_for_status()
                data = r.json()
                if not data:
                    break
                for item in data:
                    if "pull_request" in item:
                        continue
                    issues.append(
                        GitHubIssue(
                            issue_id=item["number"],
                            title=item["title"],
                            body=item.get("body", ""),
                            created_at=item["created_at"],
                            updated_at=item["updated_at"],
                            state=item["state"],
                        )
                    )
                page += 1
                pbar.update(1)
            except Exception as e:
                failed[f"issues_page_{page}"] = str(e)
                break
    return issues, failed


def fetch_github_commits() -> Tuple[List[GitCommit], Dict]:
    commits: List[GitCommit] = []
    failed: Dict = {}
    headers = _github_headers()
    page = 1
    with tqdm(desc="Fetching commits (pages)", unit="page") as page_bar:
        while True:
            url = f"https://api.github.com/repos/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}/commits"
            params = {"per_page": 100, "page": page}
            try:
                r = requests.get(url, headers=headers, params=params)
                r.raise_for_status()
                data = r.json()
                if not data:
                    break
                with tqdm(
                    data,
                    desc=f"Commit details (page {page})",
                    unit="commit",
                    leave=False,
                ) as commit_bar:
                    for item in commit_bar:
                        sha = item["sha"]
                        try:
                            detail_url = f"{url}/{sha}"
                            dr = requests.get(detail_url, headers=headers)
                            dr.raise_for_status()
                            detail = dr.json()
                            changed_files = [
                                f["filename"]
                                for f in detail.get("files", [])
                            ]
                            commits.append(
                                GitCommit(
                                    commit_hash=sha,
                                    author=detail["commit"]["author"]["name"],
                                    date=detail["commit"]["author"]["date"],
                                    message=detail["commit"]["message"],
                                    changed_files=changed_files,
                                )
                            )
                        except Exception as e:
                            failed[sha] = str(e)
                page += 1
                page_bar.update(1)
            except Exception as e:
                faild[f"commit_page_{page}"] = str(e)
                break
    return commits, failed

def extract_github_data(
    force_refresh: bool = False,
) -> Tuple[List[GitHubIssue], List[GitCommit], Dict]:

    if (
        not force_refresh
        and os.path.exists(ISSUES_FILE)
        and os.path.exists(COMMITS_FILE)
    ):
        log.info("Loading GitHub data from cache")
        issues = [
            GitHubIssue.from_dict(d)
            for d in _load_json(ISSUES_FILE)
        ]
        commits = [
            GitCommit.from_dict(d)
            for d in _load_json(COMMITS_FILE)
        ]
        return issues, commits, {}

    log.info("Fetching GitHub data from API")
    issues, issue_failures = fetch_github_issues()
    commits, commit_failures = fetch_github_commits()
    failed = {}
    failed.update(issue_failures)
    failed.update(commit_failures)
    _save_json(ISSUES_FILE, [i.to_dict() for i in issues])
    _save_json(COMMITS_FILE, [c.to_dict() for c in commits])
    log.info(
        f"Saved {len(issues)} issues and {len(commits)} commits to cache"
    )
    return issues, commits, failed

if __name__ == "__main__":
    issues, commits, failed = extract_github_data(force_refresh=False)

    log.info(f"Issues: {len(issues)}")
    log.info(f"Commits: {len(commits)}")
    log.info(f"Failures: {len(failed)}")

