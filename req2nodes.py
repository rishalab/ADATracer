import os
import time
import logging
from pathlib import Path
from typing import Dict, List, Tuple
from constants import REQUIREMENTS_DIR
import logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

class RequirementNode:
    def __init__(self, req_id: str, text: str, file_path: str):
        self.id = f"requirement-{req_id}"
        self.req_id = req_id
        self.text = text
        self.file_path = file_path

    def __repr__(self):
        return f"Requirement {self.req_id}: {self.text[:60]}"


def _to_repo_relative(path: Path) -> str:
    return path.as_posix()


def _extract_requirement_id(file_path: Path) -> str:
    name = file_path.stem
    if not name.startswith("req"):
        raise ValueError(f"Invalid requirement filename: {file_path.name}")
    suffix = name[3:]
    if not suffix.isdigit():
        raise ValueError(f"Invalid requirement ID format: {file_path.name}")
    return suffix


def _read_requirement_file(file_path: Path) -> str:
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read().strip()
    if not content:
        raise ValueError("Empty requirement file")
    return content


def parse_requirements() -> Tuple[List[RequirementNode], Dict[str, Dict]]:
    start_time = time.time()
    logging.debug("STARTED requirement parsing")
    requirements: List[RequirementNode] = []
    failed_files: Dict[str, Dict] = {}
    if not REQUIREMENTS_DIR.exists():
        logging.error(f"Requirements directory does not exist: {REQUIREMENTS_DIR}")
        return requirements, failed_files
    files = sorted(
        Path(root) / file
        for root, _, filenames in os.walk(REQUIREMENTS_DIR)
        for file in filenames
        if file.startswith("req") and file.endswith(".txt")
    )
    logging.debug(f"Found {len(files)} requirement files")
    for idx, file_path in enumerate(files):
        rel_path = _to_repo_relative(file_path)
        try:
            req_id = _extract_requirement_id(file_path)
            text = _read_requirement_file(file_path)
            node = RequirementNode(
                req_id=req_id,
                text=text,
                file_path=rel_path,
            )
            requirements.append(node)
        except Exception as e:
            failed_files[rel_path] = {
                "error": str(e),
            }
            logging.debug(f"Failed to parse {rel_path}: {e}")
        if idx % 50 == 0 or idx == len(files) - 1:
            logging.debug(
                f"Processed {idx + 1}/{len(files)} requirement files"
            )
    duration = time.time() - start_time
    logging.debug(
        f"COMPLETED requirement parsing: "
        f"{len(requirements)} ok, {len(failed_files)} failed in {duration:.2f}s"
    )
    requirements.sort(key=lambda r: int(r.req_id))
    return requirements, failed_files


def get_requirement_by_id(
    nodes: List[RequirementNode], req_id: str
) -> RequirementNode | None:
    for node in nodes:
        if node.req_id == req_id:
            return node
    return None


if __name__ == "__main__":
    reqs, failed = parse_requirements()
    logging.debug(f"Total requirements: {len(reqs)}")
    logging.debug(f"Failed files: {len(failed)}")
    if reqs:
        avg_len = sum(len(r.text) for r in reqs) / len(reqs)
        logging.debug(f"Average requirement length: {avg_len:.1f}")
    if failed:
        logging.debug("Failed requirement files:")
        for path, info in failed.items():
            logging.debug(f"  {path}: {info['error']}")