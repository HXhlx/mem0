#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DashScope model benchmark v2 - all embeddings + rerankers, large doc test data."""
import json, os, sys, time, urllib.request, urllib.error
from datetime import datetime

HOST = os.environ.get("MEM0_HOST", "http://localhost:8888")
API_KEY = ""
with open(os.path.expanduser("~/AI/Ext/mem0/server/.env")) as f:
    for line in f:
        if line.startswith("ADMIN_API_KEY="):
            API_KEY = line.strip().split("=", 1)[1]
            break

TEST_MEMORIES = [
    {"content": "## FastAPI 后端架构设计\n\n我们采用 FastAPI 作为核心 Web 框架，搭配 uvicorn 作为 ASGI 服务器。后端三层：路由层(APIRouter)、服务层(Repository Pattern)、数据层(PostgreSQL+pgvector)。认证用 JWT+X-API-Key+Token scheme。API 响应统一 {success,data,error,meta}。部署 Docker Compose 三服务编排。", "tags": ["architecture", "backend", "fastapi"]},
    {"content": "## PostgreSQL pgvector 向量检索方案\n\npgvector 扩展让 PostgreSQL 支持高维向量相似度搜索。维度固定：建表时指定 embedding_model_dims，不可修改。索引选择：<100万 IVFFlat，>100万 HNSW。cosine 适合语义搜索，metadata 子键需 client post-filter。数据从远程 VM 合入 11,138 行，UUID 无冲突。PG 数据迁移到 /data/postgres bind mount。", "tags": ["database", "vector", "pgvector"]},
    {"content": "## 前端工程化规范\n\n包管理：pnpm v10+统一，禁止 npm/yarn。原因：硬链接节省 40%+ 磁盘，且隔离 phantom deps。工具链：TypeScript strict+tsup(CJS/ESM)+ESLint/Prettier+vitest/jest。文件组织：按功能/领域组织，典型 200-400行，上限 800行。", "tags": ["frontend", "tooling", "pnpm"]},
    {"content": "## mem0 记忆层架构\n\nmem0 是 AI 记忆基础设施。两种模式：自托管 Memory/AsyncMemory、托管平台 MemoryClient。核心 API：add/search/get_all/update/delete。多 agent 隔离：4 bucket(user_id 硬隔离)。自托管适配层 self-mem0/：sdk_compat 24+ 端点。DashScope reranker 通过 RerankerFactory 注入。", "tags": ["ai", "memory", "mem0"]},
    {"content": "## 开发环境硬件与系统配置\n\nUbuntu 24.04 LTS，16核 AMD CPU，64GB DDR5，RTX 4090(24GB VRAM)。GPU：Ollama本地推理，CUDA Faiss索引构建，LoRA微调。存储：/data(ntfs3 2TB NVMe PG数据)、/home(ext4 500GB SSD)。网络：frp VPS(47.108.94.163)、http_proxy=127.0.0.1:20171。", "tags": ["hardware", "environment", "infrastructure"]},
    {"content": "## 代码风格与质量标准\n\n不可变性原则(CRITICAL)：始终创建新对象，永不修改现有对象。update 返回新副本，而非 modify 就地修改。理由：防止隐藏副作用，简化调试，启用安全并发。函数<50行，文件<800行，嵌套<4层，显式错误处理。camelCase变量，PascalCase类，UPPER_SNAKE_CASE常量。", "tags": ["coding", "style", "quality"]},
    {"content": "## DashScope 模型集成方案\n\nDashScope通过 OpenAI-compatible API 接入。LLM：deepseek-v4-flash文本，qwen3.6-flash多模态。Embedding：text-embedding-v4(512-2048d)，text-embedding-v3(64-1024d)，qwen3-vl-embedding多模态(1024d)，tongyi-embedding-vision-plus多模态(1536d)。Reranker：qwen3-rerank文本，qwen3-vl-rerank多模态，调用DashScope原生API。API Key统一使用。", "tags": ["ai", "dashscope", "models"]},
    {"content": "## CI/CD 与团队协作流程\n\nConventional Commits：<type>:<description>。禁止 --no-verify。PR：feature分支→lint+test→填写模板→CI通过→review。团队：每周五下午 code review，Ruff+pytest+pre-commit。CI矩阵：Python 3.9-3.12×Ruff+pytest，Node 20/22×Prettier+jest/vitest。", "tags": ["process", "team", "cicd"]},
    {"content": "## Claude Code 与 AI 编辑器生态\n\nClaude Code是主力 AI 编码工具，通过 mem0 插件自动记忆捕获。Hook：SessionStart/UserPromptSubmit/PreToolUse/PostToolUse/PostCompact。记忆格式：metadata.session_id/source/type/confidence。其他编辑器：OpenCode(run_id)，OpenClaw(app_id+categories)。MCP：stdio 9工具→REST，Token scheme。", "tags": ["tooling", "claude-code", "ai-editor"]},
    {"content": "## Docker 与部署运维\n\nDocker Compose三服务编排，override扩展base配置。PG数据迁移到 /data/postgres bind mount(ntfs3)。frp内网穿透 VPS(47.108.94.163)，TCP 8888。容器管理：docker compose up/restart。端口：8888:8000，5432:5432，Neo4j 8474:7474/8687:6877。监控：docker logs+request_id。", "tags": ["devops", "docker", "deployment"]},
]

SEARCH_QUERIES = [
    ("FastAPI后端用了什么ASGI服务器和认证方案？", [0]),
    ("pgvector的索引选择和维度固定怎么处理？", [1]),
    ("为什么禁止npm和yarn只用pnpm？", [2]),
    ("mem0的多agent隔离机制是什么？", [3]),
    ("本地GPU用来做什么推理和训练？", [4]),
    ("不可变性原则为什么是CRITICAL级别？", [5]),
    ("DashScope reranker用原生API还是兼容API？", [6]),
    ("PR提交前需要跑哪些检查？", [7]),
    ("Claude Code的mem0插件有哪些hook？", [8]),
    ("PG数据迁移到哪个目录？", [9]),
]

PROFILES = {
    "A": {"name": "基线: deepseek-v4-flash + text-emb-v4(1536) + qwen3-rerank",
        "llm": {"provider": "openai", "config": {"model": "deepseek-v4-flash", "openai_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1"}},
        "embedder": {"provider": "openai", "config": {"model": "text-embedding-v4", "openai_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "embedding_dims": 1536}},
        "reranker": {"provider": "dashscope", "config": {"model": "qwen3-rerank"}},
        "collection": "memories", "dims": 1536},
    "B1": {"name": "Embed-v3: deepseek-v4-flash + text-emb-v3(1536) + qwen3-rerank",
        "llm": {"provider": "openai", "config": {"model": "deepseek-v4-flash", "openai_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1"}},
        "embedder": {"provider": "openai", "config": {"model": "text-embedding-v3", "openai_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "embedding_dims": 1536}},
        "reranker": {"provider": "dashscope", "config": {"model": "qwen3-rerank"}},
        "collection": "mem_b1", "dims": 1536},
    "B2": {"name": "V4-1024d: deepseek-v4-flash + text-emb-v4(1024) + qwen3-rerank",
        "llm": {"provider": "openai", "config": {"model": "deepseek-v4-flash", "openai_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1"}},
        "embedder": {"provider": "openai", "config": {"model": "text-embedding-v4", "openai_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "embedding_dims": 1024}},
        "reranker": {"provider": "dashscope", "config": {"model": "qwen3-rerank"}},
        "collection": "mem_b2", "dims": 1024},
    "B3": {"name": "VL-embed: deepseek-v4-flash + qwen3-vl-emb(1024) + qwen3-rerank",
        "llm": {"provider": "openai", "config": {"model": "deepseek-v4-flash", "openai_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1"}},
        "embedder": {"provider": "openai", "config": {"model": "qwen3-vl-embedding", "openai_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "embedding_dims": 1024}},
        "reranker": {"provider": "dashscope", "config": {"model": "qwen3-rerank"}},
        "collection": "mem_b3", "dims": 1024},
    "C1": {"name": "VL-rerank: deepseek-v4-flash + text-emb-v4(1536) + qwen3-vl-rerank",
        "llm": {"provider": "openai", "config": {"model": "deepseek-v4-flash", "openai_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1"}},
        "embedder": {"provider": "openai", "config": {"model": "text-embedding-v4", "openai_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "embedding_dims": 1536}},
        "reranker": {"provider": "dashscope", "config": {"model": "qwen3-vl-rerank"}},
        "collection": "memories", "dims": 1536},
    "D1": {"name": "Vision+: deepseek-v4-flash + tongyi-emb-vision(1536) + qwen3-vl-rerank",
        "llm": {"provider": "openai", "config": {"model": "deepseek-v4-flash", "openai_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1"}},
        "embedder": {"provider": "openai", "config": {"model": "tongyi-embedding-vision-plus-2026-03-06", "openai_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "embedding_dims": 1536}},
        "reranker": {"provider": "dashscope", "config": {"model": "qwen3-vl-rerank"}},
        "collection": "mem_d1", "dims": 1536},
    "E": {"name": "LLM升级: qwen3.6-flash + text-emb-v4(1536) + qwen3-vl-rerank",
        "llm": {"provider": "openai", "config": {"model": "qwen3.6-flash", "openai_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1"}},
        "embedder": {"provider": "openai", "config": {"model": "text-embedding-v4", "openai_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "embedding_dims": 1536}},
        "reranker": {"provider": "dashscope", "config": {"model": "qwen3-vl-rerank"}},
        "collection": "mem_e", "dims": 1536},
}

def api_call(method, path, body=None, timeout=120):
    url = f"{HOST}{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method,
        headers={"Authorization": f"Token {API_KEY}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        err = e.read().decode()
        try: return json.loads(err)
        except: return {"error": {"message": err[:300], "code": e.code}}
    except Exception as e:
        return {"error": {"message": str(e)[:300]}}

def configure(cfg):
    payload = {"llm": cfg["llm"], "embedder": cfg["embedder"]}
    if cfg.get("reranker"): payload["reranker"] = cfg["reranker"]
    payload["vector_store"] = {"provider": "pgvector", "config": {
        "collection_name": cfg["collection"], "embedding_model_dims": cfg["dims"]}}
    return api_call("POST", "/configure", payload)

def clear(user_id="bench-test"):
    r = api_call("GET", f"/v3/memories/?user_id={user_id}&limit=1000")
    if "results" not in r:
        print("  list failed")
        return
    count = len(r["results"])
    if count == 0: print("  No data to clear"); return
    for m in r["results"]:
        api_call("DELETE", f"/v1/memories/{m['id']}/")
    print(f"  Cleared {count} memories")

def add_memories(user_id="bench-test"):
    results = []
    for i, mem in enumerate(TEST_MEMORIES):
        t0 = time.time()
        r = api_call("POST", "/v3/memories/add/", {
            "messages": [{"role": "user", "content": mem["content"]}],
            "user_id": user_id, "infer": True,
            "metadata": {"test_idx": i, "tags": mem["tags"]}})
        elapsed = (time.time() - t0) * 1000
        ok = "results" in r if isinstance(r, dict) else False
        mem_count = len(r.get("results", [])) if ok else 0
        err_msg = r.get("error", {}).get("message", "")[:100] if isinstance(r, dict) and "error" in r else ""
        results.append({"idx": i, "ms": round(elapsed), "ok": ok, "memories": mem_count, "error": err_msg})
        status = "OK" if ok else f"FAIL: {err_msg}"
        print(f"    #{i}: {status} {mem_count}mem {elapsed:.0f}ms")
    return results

def search_memories(user_id="bench-test"):
    results = []
    for query, relevant in SEARCH_QUERIES:
        t0 = time.time()
        r = api_call("POST", "/v3/memories/search/", {
            "query": query,
            "filters": {"AND": [{"user_id": user_id}]},
            "limit": 10, "rerank": True})
        elapsed = (time.time() - t0) * 1000
        hits = r.get("results", []) if isinstance(r, dict) and "results" in r else []
        hit_idxs = [h.get("metadata", {}).get("test_idx") for h in hits if h.get("metadata", {}).get("test_idx") is not None]
        recalled = len(set(hit_idxs) & set(relevant))
        mrr = 0.0
        for rank, idx in enumerate(hit_idxs):
            if idx in relevant: mrr = 1.0/(rank+1); break
        results.append({"query": query, "ms": round(elapsed),
            "total_hits": len(hits), "hit_idxs": hit_idxs,
            "relevant": relevant, "recalled": recalled,
            "recall_pct": recalled/len(relevant)*100, "mrr": mrr})
        tag = "HIT" if recalled > 0 else "MISS"
        print(f"    {query[:30]:30s} {tag} recall={recalled}/{len(relevant)} mrr={mrr:.2f} {elapsed:.0f}ms")
    return results

def run_profile(pid):
    cfg = PROFILES[pid]
    print(f"\n{'='*70}")
    print(f"Profile {pid}: {cfg['name']}")
    print(f"{'='*70}")
    print("  [1] Configure...")
    r = configure(cfg)
    if "error" in r:
        print(f"  FAIL: {r['error'].get('message','')[:200]}")
        return None
    print("  OK")
    print("  [2] Clear...")
    clear()
    time.sleep(1)
    print("  [3] Add 10 large docs...")
    add_r = add_memories()
    ok_count = sum(1 for r in add_r if r["ok"])
    avg_ms = sum(r["ms"] for r in add_r)/len(add_r)
    total_mem = sum(r["memories"] for r in add_r if r["ok"])
    print(f"  Summary: {ok_count}/10 OK, avg {avg_ms:.0f}ms, {total_mem} memories")
    time.sleep(3)
    print("  [4] Search 10 queries...")
    search_r = search_memories()
    avg_s = sum(r["ms"] for r in search_r)/len(search_r)
    total_rec = sum(r["recalled"] for r in search_r)
    total_rel = sum(len(r["relevant"]) for r in search_r)
    avg_mrr = sum(r["mrr"] for r in search_r)/len(search_r)
    print(f"  Search avg {avg_s:.0f}ms, recall {total_rec}/{total_rel}={total_rec/total_rel*100:.1f}%, MRR {avg_mrr:.3f}")

    result = {"profile": pid, "name": cfg["name"], "ts": datetime.now().isoformat(),
        "add_ok": ok_count, "add_avg_ms": round(avg_ms), "total_memories": total_mem,
        "search_avg_ms": round(avg_s),
        "recall": f"{total_rec}/{total_rel}", "recall_pct": round(total_rec/total_rel*100,1),
        "mrr": round(avg_mrr, 3)}
    rdir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
    os.makedirs(rdir, exist_ok=True)
    path = os.path.join(rdir, f"{pid}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    with open(path, "w") as f: json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"  Saved: {path}")
    return result

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--profile", nargs="+", default=["A"])
    p.add_argument("--all", action="store_true")
    args = p.parse_args()
    profiles = list(PROFILES.keys()) if args.all else args.profile

    r = api_call("GET", "/v1/ping/")
    print(f"Server: {r}")
    if "status" not in r: print(f"DOWN: {r}"); sys.exit(1)

    all_r = []
    for pid in profiles:
        r = run_profile(pid)
        if r: all_r.append(r)
        time.sleep(2)

    print(f"\n{'='*70}")
    print("SUMMARY")
    print(f"{'='*70}")
    print(f"{'PID':5s} {'Add':6s} {'Add ms':8s} {'Mem#':6s} {'Srch ms':8s} {'Recall':8s} {'MRR':6s} Name")
    for r in all_r:
        print(f"{r['profile']:5s} {r['add_ok']:3d}/10 {r['add_avg_ms']:6d}   {r['total_memories']:4d}   {r['search_avg_ms']:6d}   {r['recall']:>8s} {r['mrr']:5.3f} {r['name'][:50]}")
