"""代码图谱存储：内存 + JSON 持久化"""

from __future__ import annotations

import json
from pathlib import Path

from loguru import logger

from delphi.core.config import settings
from delphi.graph.extractor import CodeGraph


class GraphStore:
    """管理多个项目的代码图谱"""

    def __init__(self) -> None:
        self._graphs: dict[str, CodeGraph] = {}
        self._graph_dir = Path(settings.data_dir) / "graphs"
        self._graph_dir.mkdir(parents=True, exist_ok=True)
        logger.debug("图谱存储初始化, 存储目录={}", self._graph_dir)

    def _path(self, project: str) -> Path:
        return self._graph_dir / f"{project}.json"

    def save(self, project: str, graph: CodeGraph) -> None:
        """保存图谱到内存和 JSON 文件"""
        self._graphs[project] = graph
        path = self._path(project)
        path.write_text(json.dumps(graph.to_dict(), ensure_ascii=False, indent=2))
        logger.info(
            "图谱已保存: project={}, 符号数={}, 关系数={}, 路径={}",
            project,
            len(graph.symbols),
            len(graph.relations),
            path,
        )

    def load(self, project: str) -> CodeGraph | None:
        """从 JSON 文件加载图谱"""
        path = self._path(project)
        if not path.exists():
            logger.debug("图谱文件不存在, project={}, 路径={}", project, path)
            return None
        try:
            data = json.loads(path.read_text())
            graph = CodeGraph.from_dict(data)
            self._graphs[project] = graph
            logger.info(
                "图谱已加载: project={}, 符号数={}, 关系数={}", project, len(graph.symbols), len(graph.relations)
            )
            return graph
        except Exception:
            logger.warning("图谱加载失败: project={}", project, exc_info=True)
            return None

    def get(self, project: str) -> CodeGraph | None:
        """获取项目图谱（优先内存，其次文件）"""
        if project in self._graphs:
            logger.debug("从内存获取图谱: project={}", project)
            return self._graphs[project]
        logger.debug("内存中无图谱, 尝试从文件加载: project={}", project)
        return self.load(project)

    def delete(self, project: str) -> None:
        """删除项目图谱"""
        self._graphs.pop(project, None)
        path = self._path(project)
        if path.exists():
            path.unlink()
            logger.info("图谱已删除: project={}", project)
        else:
            logger.debug("图谱文件不存在, 跳过删除: project={}", project)

    def list_projects(self) -> list[str]:
        """列出所有已保存的图谱项目"""
        projects = set(self._graphs.keys())
        for p in self._graph_dir.glob("*.json"):
            projects.add(p.stem)
        logger.debug("已保存的图谱项目列表, 共 {} 个: {}", len(projects), sorted(projects))
        return sorted(projects)
