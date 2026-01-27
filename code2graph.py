import os
import json
import time
import logging
import traceback
from pathlib import Path
from typing import List, Dict, Optional
import libadalang as lal
from constants import ADA_CODE_DIR, ADA_EXTENSIONS, OUTPUT_DIR
from constants import ADA_EXTENSIONS
import logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)

log = logging.getLogger(__name__)
os.makedirs(OUTPUT_DIR, exist_ok=True)
FAILED_REPORT_PATH = Path(OUTPUT_DIR) / "failed_parse_report.json"
NODE_CACHE_PATH = Path(OUTPUT_DIR) / "ada_nodes.json"


class AdaNode:
    def __init__(
        self,
        name: str,
        node_type: str,
        file_path: str,
        line_number: int,
        parent: Optional[str] = None,
        body: Optional[str] = None,
    ):
        self.name = name
        self.type = node_type
        self.file_path = file_path
        self.line_number = line_number
        self.parent = parent
        self.body = body or ""

        self.id = f"ada::{file_path}::{node_type}::{name}::{line_number}"
        self.text = f"{node_type} {name} in {parent or file_path}"

    @staticmethod
    def from_dict(d: Dict) -> "AdaNode":
        return AdaNode(
            name=d["name"],
            node_type=d["type"],
            file_path=d["file_path"],
            line_number=d["line_number"],
            parent=d.get("parent"),
            body=d.get("body", ""),
        )

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "parent": self.parent,
            "text": self.text,
            "body": self.body,
        }


def find_ada_files(root: Path) -> List[Path]:
    files: List[Path] = []
    for r, _, fs in os.walk(root):
        for f in fs:
            if any(f.endswith(ext) for ext in ADA_EXTENSIONS):
                files.append(Path(r) / f)
    log.debug(f"Found {len(files)} Ada files")
    return files


def safe_subp_name(spec: lal.SubpSpec) -> Optional[str]:
    name_node = getattr(spec, "f_subp_name", None)
    if not name_node:
        return None
    return name_node.text.strip()


def extract_source(node, content: str) -> str:
    try:
        sloc = node.sloc_range
        lines = content.splitlines()
        start = max(sloc.start.line - 1, 0)
        end = min(sloc.end.line, len(lines))
        return "\n".join(lines[start:end]).strip()
    except Exception:
        return ""


def extract_with_libadalang(
    content: str,
    file_path: str,
    package_name: str,
) -> List[AdaNode]:

    ctx = lal.AnalysisContext()
    unit = ctx.get_from_buffer(file_path, content)
    if unit.diagnostics:
        for d in unit.diagnostics:
            log.warning(
                f"[LIBADALANG] {file_path}:{d.sloc_range.start.line} "
                f"{d.message}"
            )
    nodes: List[AdaNode] = []
    for pkg in unit.root.findall(lal.PackageDecl):
        for part in (pkg.f_public_part, pkg.f_private_part):
            if not part:
                continue
            for decl in part.f_decls:
                if isinstance(decl, (lal.TypeDecl, lal.SubtypeDecl)) and decl.f_name:
                    body = extract_source(decl, content)
                    nodes.append(
                        AdaNode(
                            name=decl.f_name.text,
                            node_type="TYPE",
                            file_path=file_path,
                            line_number=decl.sloc_range.start.line,
                            parent=package_name,
                            body=body,
                        )
                    )

    for spec in unit.root.findall(lal.SubpSpec):
        name = safe_subp_name(spec)
        if not name:
            continue
        kind = "FUNCTION" if spec.f_subp_returns else "PROCEDURE"
        body = extract_source(spec, content)
        nodes.append(
            AdaNode(
                name=name,
                node_type=kind,
                file_path=file_path,
                line_number=spec.sloc_range.start.line,
                parent=package_name,
                body=body,
            )
        )
    log.debug(f"{file_path}: extracted {len(nodes)} nodes")
    return nodes

def parse_all_files(force_rebuild=False) -> List[AdaNode]:
    log.debug("STARTED Ada code parsing")
    if NODE_CACHE_PATH.exists() and not force_rebuild:
        log.debug(f"Loading AdaNodes from cache: {NODE_CACHE_PATH}")
        with open(NODE_CACHE_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)

        nodes = [AdaNode.from_dict(d) for d in raw]
        log.debug(f"Loaded {len(nodes)} Ada nodes from cache")
        return nodes
    ada_files = find_ada_files(ADA_CODE_DIR)
    failed_files: Dict[str, Dict] = {}
    all_nodes: List[AdaNode] = []

    start = time.time()

    for idx, path in enumerate(ada_files, 1):
        file_path = str(path)
        package_name = path.stem

        log.debug(f"[{idx}/{len(ada_files)}] Processing {file_path}")

        try:
            content = path.read_text(encoding="utf-8", errors="ignore")

            nodes = extract_with_libadalang(
                content=content,
                file_path=file_path,
                package_name=package_name,
            )

            all_nodes.extend(nodes)

        except Exception as e:
            log.error(f"FAILED: {file_path}")
            log.error(str(e))
            log.error(traceback.format_exc())

            failed_files[file_path] = {
                "error": str(e),
            }

    with open(NODE_CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump([n.to_dict() for n in all_nodes], f, indent=2)

    with open(FAILED_REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(failed_files, f, indent=2)

    log.debug(f"COMPLETED in {time.time() - start:.2f}s")
    log.debug(f"Total nodes extracted: {len(all_nodes)}")
    log.debug(f"Failed files: {len(failed_files)}")

    return all_nodes

if __name__ == "__main__":
    parse_all_files(force_rebuild=True)
