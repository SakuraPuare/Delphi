"""代码图谱存储：内存 + JSON 持久化"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from delphi.graph.extractor import CodeGraph

logger = logging.getLogger(__name__)

GRAPH_DIR = Path.home() / ".delphi" / "graphs"


class GraphStore:
    """管理多个项目的代码图谱"""

    def __init__(self) -> None:
        self._graphs: dict[str, CodeGraph] = {}
        GRAPH_DIR.mkdir(parents=True, exist_ok=True)

    def _path(self, project: str) -> Path:
        return GRAPH_DIR / f"{project}.json"

    def save(self, project: str, graph: CodeGraph) -> None:
        """保存图谱到内存和 JSON 文件"""
        self._graphs[project] = graph
        path = self._path(project)
        path.write_text(json.dumps(graph.to_dict(), ensure_ascii=False, indent=2))
        logger.info("Saved graph for '%s' (%d symbols, %d relations)",
                     project, len(graph.symbols), len(graph.relations))

    def load(self, project: str) -> CodeGraph | None:
        """从 JSON 文件加载图谱"""
        path = self._path(project)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text())
            graph = CodeGraph.from_dict(data)
            self._graphs[project] = graph
            return graph
        except Exception:
            logger.warning("Failed to load graph for '%s'", project, exc_info=True)
            return None

    def get(self, project: str) -> CodeGraph | None:
        """获取项目图谱（优先内存，其次文件）"""
        if project in self._graphs:
            return self._graphs[project]
        return self.load(project)

    def delete(self, project: str) -> None:
        """删除项目图谱"""
        self._graphs.pop(project, None)
        path = self._path(project)
        if path.exists():
            path.unlink()
            logger.info("Deleted graph for '%s'", project)

    def list_projects(self) -> list[str]:
        """列出所有已保存的图谱项目"""
        projects = set(self._graphs.keys())
        for p in GRAPH_DIR.glob("*.json"):
            projects.add(p.stem)
        return sorted(projects)
