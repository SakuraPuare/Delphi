from dataclasses import dataclass, field


@dataclass
class ChunkMetadata:
    file_path: str = ""
    repo_url: str = ""
    language: str = ""
    start_line: int = 0
    end_line: int = 0
    node_type: str = ""  # "function", "class", "method", "fallback"
    file_hash: str = ""  # SHA256 of file content, for incremental updates


@dataclass
class Chunk:
    text: str
    metadata: ChunkMetadata = field(default_factory=ChunkMetadata)
