from dataclasses import dataclass, field

from loguru import logger


@dataclass
class ChunkMetadata:
    file_path: str = ""
    repo_url: str = ""
    language: str = ""
    start_line: int = 0
    end_line: int = 0
    node_type: str = ""  # "function", "class", "method", "fallback"
    symbol_name: str = ""  # 函数/类/方法名称
    parent_symbol: str = ""  # 父级符号名称（如方法所属的类）
    file_hash: str = ""  # SHA256 of file content, for incremental updates


@dataclass
class Chunk:
    text: str
    metadata: ChunkMetadata = field(default_factory=ChunkMetadata)
