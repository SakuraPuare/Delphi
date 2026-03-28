from __future__ import annotations

import time

import httpx
import typer
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeRemainingColumn
from rich.table import Table

app = typer.Typer(name="delphi", help="Delphi - 可离线部署的本地知识库系统")
console = Console()
err_console = Console(stderr=True)

# Global state
_state: dict = {"api_url": "http://localhost:8888", "verbose": False}


@app.callback()
def main(
    api_url: str = typer.Option("http://localhost:8888", help="API Server 地址"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="输出详细日志"),
) -> None:
    _state["api_url"] = api_url.rstrip("/")
    _state["verbose"] = verbose


def _client() -> httpx.Client:
    return httpx.Client(base_url=_state["api_url"], timeout=30)


def _handle_connection_error() -> None:
    err_console.print(f"[red]无法连接到 API Server ({_state['api_url']})[/red]")
    err_console.print("请确认服务已启动: delphi serve")
    raise SystemExit(2)


def _handle_http_error(resp: httpx.Response) -> None:
    try:
        detail = resp.json().get("detail", resp.text)
    except Exception:
        detail = resp.text
    err_console.print(f"[red]请求失败 ({resp.status_code}): {detail}[/red]")
    raise SystemExit(1)


# --- serve ---


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", help="监听地址"),
    port: int = typer.Option(8888, help="监听端口"),
    reload: bool = typer.Option(False, help="开发模式热重载"),
) -> None:
    """启动 API 服务"""
    import uvicorn

    uvicorn.run("delphi.api.app:app", host=host, port=port, reload=reload)


# --- status ---


@app.command()
def status() -> None:
    """查看系统状态"""
    try:
        with _client() as c:
            resp = c.get("/status")
    except httpx.ConnectError:
        _handle_connection_error()

    if resp.status_code != 200:
        _handle_http_error(resp)

    data = resp.json()
    console.print("\n[bold]服务状态[/bold]")
    for name, info in data.items():
        ok = info.get("ok", False)
        mark = "[green]✓[/green]" if ok else "[red]✗[/red]"
        extra_parts: list[str] = []
        if info.get("model"):
            extra_parts.append(f"模型: {info['model']}")
        if info.get("collections") is not None:
            extra_parts.append(f"集合数: {info['collections']}")
        if info.get("error") and not ok:
            extra_parts.append(f"错误: {info['error']}")
        extra = "  " + ", ".join(extra_parts) if extra_parts else ""
        console.print(f"  {name:<14} {mark}{extra}")
    console.print()


# --- import ---

import_app = typer.Typer(help="数据导入")
app.add_typer(import_app, name="import")


def _poll_task(client: httpx.Client, task_id: str) -> None:
    """Poll a task until completion, showing a progress bar."""
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        bar = progress.add_task("导入中...", total=None)
        while True:
            resp = client.get(f"/import/tasks/{task_id}")
            if resp.status_code != 200:
                _handle_http_error(resp)
            info = resp.json()
            total = info.get("total", 0)
            processed = info.get("processed", 0)
            status = info.get("status", "pending")

            if total > 0:
                progress.update(bar, total=total, completed=processed)

            if status == "done":
                progress.update(bar, total=total, completed=total)
                break
            if status == "failed":
                err_console.print(f"[red]导入失败: {info.get('error', '未知错误')}[/red]")
                raise SystemExit(1)

            time.sleep(2)

    console.print(f"[green]✓ 导入完成: {info.get('processed', 0)} 个文件已处理[/green]")


@import_app.command("git")
def import_git(
    url: str = typer.Argument(help="Git 仓库 URL 或本地路径"),
    project: str = typer.Option("", help="目标项目名称"),
    branch: str = typer.Option("main", help="指定分支"),
    include: list[str] | None = typer.Option(None, help="文件过滤 glob"),  # noqa: B008
    exclude: list[str] | None = typer.Option(None, help="排除文件 glob"),  # noqa: B008
    depth: int = typer.Option(1, help="clone 深度"),
) -> None:
    """导入 Git 仓库"""
    body = {
        "url": url,
        "project": project,
        "branch": branch,
        "include": include or [],
        "exclude": exclude or [],
        "depth": depth,
    }
    try:
        with _client() as c:
            resp = c.post("/import/git", json=body)
            if resp.status_code not in (200, 201, 202):
                _handle_http_error(resp)
            task_id = resp.json()["task_id"]
            console.print(f"任务已创建: {task_id}")
            _poll_task(c, task_id)
    except httpx.ConnectError:
        _handle_connection_error()


@import_app.command("docs")
def import_docs(
    path: str = typer.Argument(help="文档目录路径"),
    project: str = typer.Option("", help="目标项目名称"),
    recursive: bool = typer.Option(True, "--recursive", "-r", help="递归扫描子目录"),
    type_: list[str] | None = typer.Option(None, "--type", help="文件类型过滤"),  # noqa: B008
) -> None:
    """导入文档目录"""
    body = {
        "path": path,
        "project": project,
        "recursive": recursive,
        "file_types": type_ or ["md", "txt", "pdf", "html"],
    }
    try:
        with _client() as c:
            resp = c.post("/import/docs", json=body)
            if resp.status_code not in (200, 201, 202):
                _handle_http_error(resp)
            task_id = resp.json()["task_id"]
            console.print(f"任务已创建: {task_id}")
            _poll_task(c, task_id)
    except httpx.ConnectError:
        _handle_connection_error()


@import_app.command("media")
def import_media(
    path: str = typer.Argument(help="音视频目录路径"),
    project: str = typer.Option("", help="目标项目名称"),
    recursive: bool = typer.Option(True, "--recursive", "-r", help="递归扫描子目录"),
    whisper_model: str = typer.Option("large-v3", "--model", help="Whisper 模型大小"),
) -> None:
    """导入音视频文件（转录后入库）"""
    body = {
        "path": path,
        "project": project,
        "recursive": recursive,
        "whisper_model": whisper_model,
    }
    try:
        with _client() as c:
            resp = c.post("/import/media", json=body)
            if resp.status_code not in (200, 201, 202):
                _handle_http_error(resp)
            task_id = resp.json()["task_id"]
            console.print(f"任务已创建: {task_id}")
            _poll_task(c, task_id)
    except httpx.ConnectError:
        _handle_connection_error()


# --- query ---


@app.command()
def query(
    question: str = typer.Argument(help="查询问题"),
    project: str = typer.Option("", help="指定查询的项目"),
    top_k: int = typer.Option(5, help="召回文档数量"),
    stream: bool = typer.Option(False, "--stream/--no-stream", help="流式输出"),
    show_sources: bool = typer.Option(False, "--show-sources", help="显示引用来源"),
) -> None:
    """查询知识库"""
    body = {"question": question, "project": project, "top_k": top_k}
    try:
        with _client() as c:
            if stream:
                with c.stream("POST", "/query/stream", json=body) as resp:
                    if resp.status_code != 200:
                        resp.read()
                        _handle_http_error(resp)
                    for line in resp.iter_lines():
                        if line.startswith("data: "):
                            token = line[6:]
                            console.print(token, end="")
                console.print()
            else:
                resp = c.post("/query", json=body)
                if resp.status_code != 200:
                    _handle_http_error(resp)
                data = resp.json()
                console.print(data["answer"])
                if show_sources and data.get("sources"):
                    console.print("\n[bold]来源:[/bold]")
                    for i, src in enumerate(data["sources"], 1):
                        score = src.get("score", 0)
                        console.print(f"  [{i}] {src['file']} (相关度 {score:.2f})")
    except httpx.ConnectError:
        _handle_connection_error()


# --- agent ---


@app.command()
def agent(
    question: str = typer.Argument(help="查询问题"),
    project: str = typer.Option("", help="指定查询的项目"),
    max_steps: int = typer.Option(5, help="最大推理步数"),
    stream: bool = typer.Option(False, "--stream/--no-stream", help="流式输出"),
    show_steps: bool = typer.Option(False, "--show-steps", help="显示推理步骤"),
    show_sources: bool = typer.Option(False, "--show-sources", help="显示引用来源"),
) -> None:
    """Agent 模式查询：多步推理回答复杂问题"""
    import json as _json

    body = {"question": question, "project": project, "max_steps": max_steps}
    try:
        with _client() as c:
            if stream:
                with c.stream("POST", "/agent/query/stream", json=body, timeout=120) as resp:
                    if resp.status_code != 200:
                        resp.read()
                        _handle_http_error(resp)
                    for line in resp.iter_lines():
                        if not line.startswith("data: "):
                            continue
                        data = _json.loads(line[6:])
                        evt_type = data.get("type", "")
                        if evt_type == "thought" and show_steps:
                            console.print(f"[dim]💭 {data['content']}[/dim]")
                        elif evt_type == "action" and show_steps:
                            console.print(f"[dim]🔧 {data.get('args', '')}[/dim]")
                        elif evt_type == "observation" and show_steps:
                            obs = data.get("content", "")
                            if len(obs) > 200:
                                obs = obs[:200] + "..."
                            console.print(f"[dim]📋 {obs}[/dim]")
                        elif evt_type == "token":
                            console.print(data.get("content", ""), end="")
                        elif evt_type == "sources" and show_sources:
                            console.print("\n\n[bold]来源:[/bold]")
                            for src in data.get("sources", []):
                                console.print(f"  [{src.get('index', '')}] {src.get('file', '')}")
                        elif evt_type == "done":
                            pass
                console.print()
            else:
                resp = c.post("/agent/query", json=body, timeout=120)
                if resp.status_code != 200:
                    _handle_http_error(resp)
                data = resp.json()

                if show_steps and data.get("steps"):
                    console.print("[bold]推理过程:[/bold]")
                    for i, step in enumerate(data["steps"], 1):
                        console.print(f"\n[dim]--- 步骤 {i} ---[/dim]")
                        console.print(f"[dim]💭 {step['thought']}[/dim]")
                        if step.get("action"):
                            console.print(f"[dim]🔧 {step['action']}[/dim]")
                        if step.get("observation"):
                            obs = step["observation"]
                            if len(obs) > 200:
                                obs = obs[:200] + "..."
                            console.print(f"[dim]📋 {obs}[/dim]")
                    console.print()

                console.print(data["answer"])

                if show_sources and data.get("sources"):
                    console.print("\n[bold]来源:[/bold]")
                    for src in data["sources"]:
                        console.print(f"  [{src.get('index', '')}] {src.get('file', '')}")
    except httpx.ConnectError:
        _handle_connection_error()


# --- projects ---

projects_app = typer.Typer(help="项目管理")
app.add_typer(projects_app, name="projects")


@projects_app.command("list")
def projects_list() -> None:
    """列出所有项目"""
    try:
        with _client() as c:
            resp = c.get("/projects")
    except httpx.ConnectError:
        _handle_connection_error()

    if resp.status_code != 200:
        _handle_http_error(resp)

    projects = resp.json()
    if not projects:
        console.print("暂无项目")
        return

    table = Table(title="项目列表")
    table.add_column("名称", style="cyan")
    table.add_column("文档块数", justify="right")
    table.add_column("创建时间")
    for p in projects:
        table.add_row(p["name"], str(p.get("chunk_count", 0)), p.get("created_at", ""))
    console.print(table)


@projects_app.command("create")
def projects_create(
    name: str = typer.Argument(help="项目名称"),
    description: str = typer.Option("", help="项目描述"),
) -> None:
    """创建项目"""
    try:
        with _client() as c:
            resp = c.post("/projects", json={"name": name, "description": description})
    except httpx.ConnectError:
        _handle_connection_error()

    if resp.status_code not in (200, 201):
        _handle_http_error(resp)

    console.print(f"[green]✓ 项目 '{name}' 已创建[/green]")


@projects_app.command("delete")
def projects_delete(
    name: str = typer.Argument(help="项目名称"),
    yes: bool = typer.Option(False, "--yes", "-y", help="跳过确认"),
) -> None:
    """删除项目"""
    if not yes:
        confirm = typer.confirm(f"确认删除项目 '{name}'？此操作不可恢复")
        if not confirm:
            raise typer.Abort()

    try:
        with _client() as c:
            resp = c.delete(f"/projects/{name}")
    except httpx.ConnectError:
        _handle_connection_error()

    if resp.status_code not in (200, 204):
        _handle_http_error(resp)

    console.print(f"[green]✓ 项目 '{name}' 已删除[/green]")


# --- finetune ---

finetune_app = typer.Typer(help="微调数据生成")
app.add_typer(finetune_app, name="finetune")


def _poll_finetune_task(client: httpx.Client, task_id: str) -> None:
    """Poll a finetune task until completion."""
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        bar = progress.add_task("生成中...", total=None)
        while True:
            resp = client.get(f"/finetune/tasks/{task_id}")
            if resp.status_code != 200:
                _handle_http_error(resp)
            info = resp.json()
            status = info.get("status", "pending")
            processed = info.get("processed", 0)
            total = info.get("total", 0)

            if total > 0:
                progress.update(bar, total=total, completed=processed)

            if status == "done":
                progress.update(bar, total=total, completed=total)
                break
            if status == "failed":
                err_console.print(f"[red]生成失败: {info.get('error', '未知错误')}[/red]")
                raise SystemExit(1)

            time.sleep(2)

    console.print(f"[green]✓ 生成完成: {info.get('processed', 0)} 条 Q&A 对[/green]")


@finetune_app.command("generate")
def finetune_generate(
    project: str = typer.Option(..., "--project", "-p", help="项目名称"),
    samples: int = typer.Option(100, "--samples", "-n", help="采样 chunk 数量"),
    questions_per_chunk: int = typer.Option(2, "--qpc", help="每个 chunk 生成的问题数"),
    fmt: str = typer.Option("jsonl", "--format", "-f", help="输出格式: jsonl | alpaca | sharegpt"),
    output: str = typer.Option("", "--output", "-o", help="输出文件路径"),
) -> None:
    """从知识库生成微调训练数据"""
    body = {
        "project": project,
        "num_samples": samples,
        "questions_per_chunk": questions_per_chunk,
        "format": fmt,
        "output_path": output,
    }
    try:
        with _client() as c:
            resp = c.post("/finetune/generate", json=body)
            if resp.status_code not in (200, 201, 202):
                _handle_http_error(resp)
            task_id = resp.json()["task_id"]
            console.print(f"任务已创建: {task_id}")
            _poll_finetune_task(c, task_id)
    except httpx.ConnectError:
        _handle_connection_error()


# --- models ---


models_app = typer.Typer(help="模型管理")
app.add_typer(models_app, name="models")


@models_app.command("list")
def models_list() -> None:
    """列出所有已注册模型"""
    try:
        with _client() as c:
            resp = c.get("/models")
    except httpx.ConnectError:
        _handle_connection_error()

    if resp.status_code != 200:
        _handle_http_error(resp)

    models = resp.json()
    if not models:
        console.print("暂无已注册模型")
        return

    table = Table(title="模型列表")
    table.add_column("名称", style="cyan")
    table.add_column("路径")
    table.add_column("类型")
    table.add_column("基础模型")
    table.add_column("活跃", justify="center")
    for m in models:
        active = "✓" if m.get("active") else ""
        table.add_row(
            m["name"],
            m.get("model_path", ""),
            m.get("model_type", "base"),
            m.get("base_model", ""),
            active,
        )
    console.print(table)


@models_app.command("register")
def models_register(
    name: str = typer.Argument(help="模型名称"),
    path: str = typer.Option(..., "--path", "-p", help="模型路径或 HuggingFace ID"),
    model_type: str = typer.Option("base", "--type", "-t", help="模型类型: base | lora"),
    base_model: str = typer.Option("", "--base", "-b", help="LoRA 基础模型（仅 lora 类型需要）"),
    description: str = typer.Option("", "--desc", "-d", help="模型描述"),
) -> None:
    """注册新模型"""
    body = {
        "name": name,
        "model_path": path,
        "model_type": model_type,
        "base_model": base_model,
        "description": description,
    }
    try:
        with _client() as c:
            resp = c.post("/models/register", json=body)
    except httpx.ConnectError:
        _handle_connection_error()

    if resp.status_code not in (200, 201):
        _handle_http_error(resp)

    console.print(f"[green]✓ 模型 '{name}' 已注册[/green]")


@models_app.command("activate")
def models_activate(
    name: str = typer.Argument(help="模型名称"),
) -> None:
    """激活/切换模型"""
    try:
        with _client() as c:
            resp = c.post("/models/activate", json={"name": name})
    except httpx.ConnectError:
        _handle_connection_error()

    if resp.status_code != 200:
        _handle_http_error(resp)

    console.print(f"[green]✓ 已切换到模型 '{name}'[/green]")


@models_app.command("remove")
def models_remove(
    name: str = typer.Argument(help="模型名称"),
    yes: bool = typer.Option(False, "--yes", "-y", help="跳过确认"),
) -> None:
    """注销模型"""
    if not yes:
        confirm = typer.confirm(f"确认注销模型 '{name}'？")
        if not confirm:
            raise typer.Abort()

    try:
        with _client() as c:
            resp = c.delete(f"/models/{name}")
    except httpx.ConnectError:
        _handle_connection_error()

    if resp.status_code not in (200, 204):
        _handle_http_error(resp)

    console.print(f"[green]✓ 模型 '{name}' 已注销[/green]")


# --- graph ---

graph_app = typer.Typer(help="代码关系图谱")
app.add_typer(graph_app, name="graph")


@graph_app.command("build")
def graph_build(
    project: str = typer.Option(..., "--project", "-p", help="项目名称"),
    path: str = typer.Option(..., "--path", help="代码目录路径"),
    include: list[str] | None = typer.Option(None, "--include", help="文件过滤 glob"),  # noqa: B008
    exclude: list[str] | None = typer.Option(None, "--exclude", help="排除文件 glob"),  # noqa: B008
) -> None:
    """构建代码关系图谱"""
    body = {
        "project": project,
        "path": path,
        "include": include or [],
        "exclude": exclude or [],
    }
    try:
        with _client() as c:
            resp = c.post("/graph/build", json=body)
            if resp.status_code not in (200, 201, 202):
                _handle_http_error(resp)
            task_id = resp.json()["task_id"]
            console.print(f"任务已创建: {task_id}")
            _poll_graph_task(c, task_id)
    except httpx.ConnectError:
        _handle_connection_error()


def _poll_graph_task(client: httpx.Client, task_id: str) -> None:
    """Poll a graph build task until completion."""
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        bar = progress.add_task("构建图谱中...", total=None)
        while True:
            resp = client.get(f"/import/tasks/{task_id}")
            if resp.status_code != 200:
                _handle_http_error(resp)
            info = resp.json()
            total = info.get("total", 0)
            processed = info.get("processed", 0)
            status = info.get("status", "pending")

            if total > 0:
                progress.update(bar, total=total, completed=processed)

            if status == "done":
                progress.update(bar, total=total, completed=total)
                break
            if status == "failed":
                err_console.print(f"[red]图谱构建失败: {info.get('error', '未知错误')}[/red]")
                raise SystemExit(1)

            time.sleep(2)

    console.print(f"[green]✓ 图谱构建完成: {info.get('processed', 0)} 个符号已提取[/green]")


@graph_app.command("show")
def graph_show(
    project: str = typer.Argument(help="项目名称"),
) -> None:
    """显示图谱统计"""
    try:
        with _client() as c:
            resp = c.get(f"/graph/{project}")
    except httpx.ConnectError:
        _handle_connection_error()

    if resp.status_code != 200:
        _handle_http_error(resp)

    data = resp.json()
    symbols = data.get("symbols", [])
    relations = data.get("relations", [])

    console.print(f"\n[bold]图谱: {project}[/bold]")
    console.print(f"  符号数: {len(symbols)}")
    console.print(f"  关系数: {len(relations)}")

    # 按类型统计
    kind_counts: dict[str, int] = {}
    for s in symbols:
        k = s.get("kind", "unknown")
        kind_counts[k] = kind_counts.get(k, 0) + 1
    if kind_counts:
        console.print("\n  符号类型:")
        for k, v in sorted(kind_counts.items()):
            console.print(f"    {k}: {v}")

    rel_counts: dict[str, int] = {}
    for r in relations:
        k = r.get("kind", "unknown")
        rel_counts[k] = rel_counts.get(k, 0) + 1
    if rel_counts:
        console.print("\n  关系类型:")
        for k, v in sorted(rel_counts.items()):
            console.print(f"    {k}: {v}")
    console.print()


@graph_app.command("query")
def graph_query(
    project: str = typer.Argument(help="项目名称"),
    symbol: str = typer.Option(..., "--symbol", "-s", help="符号名称"),
) -> None:
    """查询符号关系"""
    try:
        with _client() as c:
            resp = c.get(f"/graph/{project}/symbol/{symbol}")
    except httpx.ConnectError:
        _handle_connection_error()

    if resp.status_code != 200:
        _handle_http_error(resp)

    data = resp.json()
    symbols = data.get("symbols", [])
    relations = data.get("relations", [])

    if symbols:
        table = Table(title=f"符号: {symbol}")
        table.add_column("名称", style="cyan")
        table.add_column("类型")
        table.add_column("文件")
        table.add_column("行号")
        for s in symbols:
            table.add_row(
                s["qualified_name"],
                s["kind"],
                s["file_path"],
                f"{s['start_line']}-{s['end_line']}",
            )
        console.print(table)

    if relations:
        rel_table = Table(title="关系")
        rel_table.add_column("来源", style="cyan")
        rel_table.add_column("类型", style="yellow")
        rel_table.add_column("目标", style="green")
        for r in relations:
            rel_table.add_row(r["source"], r["kind"], r["target"])
        console.print(rel_table)


# --- eval ---

eval_app = typer.Typer(help="RAG 评估")
app.add_typer(eval_app, name="eval")


@eval_app.command("run")
def eval_run(
    dataset: str = typer.Argument(help="评估数据集 JSON 文件路径"),
    project: str = typer.Option("", help="项目 ID（覆盖数据集中的 project_id）"),
    output: str = typer.Option("", help="结果输出 JSON 文件路径"),
) -> None:
    """运行 RAG 评估流水线"""
    import asyncio
    import json as _json
    from pathlib import Path

    from delphi.evaluation.runner import run_evaluation

    with console.status("正在运行评估..."):
        result = asyncio.run(run_evaluation(dataset, project_id=project or None))

    metrics = result["metrics"]
    table = Table(title=f"评估结果 ({result['total']} 条, {result['elapsed_seconds']}s)")
    table.add_column("指标", style="cyan")
    table.add_column("值", style="green")
    table.add_row("Recall", f"{metrics['avg_recall']:.4f}")
    table.add_row("Precision", f"{metrics['avg_precision']:.4f}")
    table.add_row("MRR", f"{metrics['avg_mrr']:.4f}")
    table.add_row("Faithfulness", f"{metrics['avg_faithfulness']:.4f}")
    table.add_row("Relevance", f"{metrics['avg_relevance']:.4f}")
    console.print(table)

    if output:
        Path(output).write_text(_json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        console.print(f"[green]✓ 结果已保存到 {output}[/green]")
    else:
        console.print_json(data=result)


@eval_app.command("generate")
def eval_generate(
    project: str = typer.Option(..., help="项目 ID"),
    num: int = typer.Option(50, help="生成问答对数量"),
    output: str = typer.Option("eval_dataset.json", help="输出文件路径"),
) -> None:
    """从知识库自动生成评估数据集"""
    import asyncio

    from delphi.evaluation.dataset import generate_eval_dataset

    with console.status(f"正在生成 {num} 条评估数据..."):
        result = asyncio.run(generate_eval_dataset(project, num_questions=num, output_path=output))

    console.print(f"[green]✓ 已生成 {len(result['items'])} 条评估数据 -> {output}[/green]")


# --- schedule ---

schedule_app = typer.Typer(help="定时同步调度")
app.add_typer(schedule_app, name="schedule")


@schedule_app.command("add")
def schedule_add(
    project: str = typer.Option(..., "--project", "-p", help="项目 ID"),
    repo: str = typer.Option(..., "--repo", "-r", help="Git 仓库 URL"),
    cron: str = typer.Option("0 */6 * * *", "--cron", "-c", help="Cron 表达式"),
    branch: str = typer.Option("main", "--branch", "-b", help="分支名称"),
) -> None:
    """添加定时同步任务"""
    body = {
        "project_id": project,
        "repo_url": repo,
        "cron_expr": cron,
        "branch": branch,
    }
    try:
        with _client() as c:
            resp = c.post("/scheduler/jobs", json=body)
    except httpx.ConnectError:
        _handle_connection_error()

    if resp.status_code not in (200, 201):
        _handle_http_error(resp)

    data = resp.json()
    console.print(f"[green]✓ 调度任务已创建: {data['project_id']}[/green]")
    console.print(f"  Cron: {data['cron_expr']}")
    console.print(f"  下次执行: {data.get('next_run_at', '-')}")


@schedule_app.command("list")
def schedule_list() -> None:
    """列出所有调度任务"""
    try:
        with _client() as c:
            resp = c.get("/scheduler/jobs")
    except httpx.ConnectError:
        _handle_connection_error()

    if resp.status_code != 200:
        _handle_http_error(resp)

    jobs = resp.json()
    if not jobs:
        console.print("暂无调度任务")
        return

    table = Table(title="调度任务列表")
    table.add_column("项目", style="cyan")
    table.add_column("仓库")
    table.add_column("Cron")
    table.add_column("分支")
    table.add_column("下次执行", style="green")
    table.add_column("上次执行")
    table.add_column("运行中", style="yellow")
    for j in jobs:
        table.add_row(
            j["project_id"],
            j["repo_url"],
            j["cron_expr"],
            j["branch"],
            j.get("next_run_at") or "-",
            j.get("last_run_at") or "-",
            "是" if j.get("running") else "否",
        )
    console.print(table)


@schedule_app.command("remove")
def schedule_remove(
    project: str = typer.Option(..., "--project", "-p", help="项目 ID"),
) -> None:
    """移除调度任务"""
    try:
        with _client() as c:
            resp = c.delete(f"/scheduler/jobs/{project}")
    except httpx.ConnectError:
        _handle_connection_error()

    if resp.status_code == 204:
        console.print(f"[green]✓ 已移除调度任务: {project}[/green]")
    elif resp.status_code == 404:
        err_console.print(f"[red]调度任务不存在: {project}[/red]")
        raise SystemExit(1)
    else:
        _handle_http_error(resp)


# --- tasks ---

tasks_app = typer.Typer(help="任务管理")
app.add_typer(tasks_app, name="tasks")


@tasks_app.command("list")
def tasks_list() -> None:
    """列出所有任务"""
    try:
        with _client() as c:
            import_resp = c.get("/import/tasks")
            eval_resp = c.get("/eval/tasks")
    except httpx.ConnectError:
        _handle_connection_error()

    for resp in (import_resp, eval_resp):
        if resp.status_code != 200:
            _handle_http_error(resp)

    tasks = []
    for t in import_resp.json():
        t["task_type"] = "import"
        tasks.append(t)
    for t in eval_resp.json():
        t["task_type"] = "eval"
        tasks.append(t)

    if not tasks:
        console.print("[dim]暂无任务[/dim]")
        return

    table = Table(title="任务列表")
    table.add_column("Task ID", style="cyan")
    table.add_column("Type")
    table.add_column("Status")
    table.add_column("Progress")
    table.add_column("Message")
    table.add_column("Created At", style="green")

    from datetime import datetime

    for t in tasks:
        created = t.get("created_at") or "-"
        if created != "-":
            try:
                dt = datetime.fromisoformat(created)
                created = dt.strftime("%Y-%m-%d %H:%M:%S")
            except (ValueError, TypeError):
                pass
        table.add_row(
            t.get("task_id", "-"),
            t.get("task_type", "-"),
            t.get("status", "-"),
            str(t.get("progress", "-")),
            t.get("message") or "-",
            created,
        )
    console.print(table)


@tasks_app.command("resume")
def tasks_resume(
    task_id: str = typer.Argument(..., help="任务 ID"),
) -> None:
    """恢复指定任务"""
    # First determine task type by fetching from both endpoints
    task_type = None
    try:
        with _client() as c:
            resp = c.get(f"/import/tasks/{task_id}")
            if resp.status_code == 200:
                task_type = "import"
            else:
                resp = c.get(f"/eval/tasks/{task_id}")
                if resp.status_code == 200:
                    task_type = "eval"
    except httpx.ConnectError:
        _handle_connection_error()

    if task_type is None:
        err_console.print(f"[red]任务不存在: {task_id}[/red]")
        raise SystemExit(1)

    try:
        with _client() as c:
            resp = c.post(f"/{task_type}/tasks/{task_id}/resume")
    except httpx.ConnectError:
        _handle_connection_error()

    if resp.status_code != 200:
        _handle_http_error(resp)

    console.print(f"[green]✓ 任务已恢复: {task_id} ({task_type})[/green]")


if __name__ == "__main__":
    app()
