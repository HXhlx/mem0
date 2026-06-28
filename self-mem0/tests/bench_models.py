#!/usr/bin/env python3
"""DashScope model quality benchmark for mem0 self-hosted server."""
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
    "我在用 FastAPI 写后端项目，uvicorn 做 ASGI 服务器，部署在 Docker 容器里",
    "PostgreSQL 的 pgvector 扩展支持向量检索，embedding 维度在建表时固定",
    "我偏好用 pnpm 管理前端依赖，不用 npm 和 yarn，因为硬链接节省磁盘",
    "项目使用 mem0 作为 AI 记忆层，支持多 agent 隔离，user_id 是主键",
    "我的开发机器是 Ubuntu 24.04，16核 CPU，64GB 内存，显卡 RTX 4090",
    "代码风格偏好：函数不超过50行，文件不超过800行，不可变数据优先",
    "DashScope 的 qwen3-rerank 模型可以做 cross-encoder 重排序提升检索精度",
    "每周五下午是团队 code review 时间，需要提前准备好 PR 和测试报告",
    "我使用 Claude Code 作为主力编码工具，配合 mem0 插件做自动记忆捕获",
    "Docker Compose 的 override 文件可以不修改 git 跟踪配置就扩展服务",
]

SEARCH_QUERIES = [
    ("我用的什么后端框架？", [0]),
    ("向量数据库维度怎么处理？", [1]),
    ("前端包管理工具偏好", [2]),
    ("AI记忆是怎么隔离的？", [3]),
    ("代码规范和风格", [5]),
    ("重排序模型", [6]),
    ("开发环境硬件配置", [4]),
    ("code review 流程", [7]),
]

PROFILES = {
    "A": {
        "name": "基线: deepseek-v4-flash + text-embedding-v4 + qwen3-rerank",
        "llm": {"provider": "openai", "config": {"model": "deepseek-v4-flash", "openai_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1"}},
        "embedder": {"provider": "openai", "config": {"model": "text-embedding-v4", "openai_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "embedding_dims": 1536}},
        "reranker": {"provider": "dashscope", "config": {"model": "qwen3-rerank"}},
        "collection": "memories", "dims": 1536,
    },
    "B": {
        "name": "LLM升级: qwen3.6-flash + text-embedding-v4 + qwen3-rerank",
        "llm": {"provider": "openai", "config": {"model": "qwen3.6-flash", "openai_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1"}},
        "embedder": {"provider": "openai", "config": {"model": "text-embedding-v4", "openai_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "embedding_dims": 1536}},
        "reranker": {"provider": "dashscope", "config": {"model": "qwen3-rerank"}},
        "collection": "memories", "dims": 1536,
    },
    "C": {
        "name": "VL-rerank: qwen3.6-flash + text-embedding-v4 + qwen3-vl-rerank",
        "llm": {"provider": "openai", "config": {"model": "qwen3.6-flash", "openai_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1"}},
        "embedder": {"provider": "openai", "config": {"model": "text-embedding-v4", "openai_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "embedding_dims": 1536}},
        "reranker": {"provider": "dashscope", "config": {"model": "qwen3-vl-rerank"}},
        "collection": "memories", "dims": 1536,
    },
}

def api_call(method, path, body=None, timeout=60):
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
    if cfg.get("reranker"):
        payload["reranker"] = cfg["reranker"]
    payload["vector_store"] = {"provider": "pgvector", "config": {
        "collection_name": cfg["collection"], "embedding_model_dims": cfg["dims"]}}
    return api_call("POST", "/configure", payload)

def clear(user_id="bench-test"):
    r = api_call("GET", f"/v3/memories/?user_id={user_id}&limit=1000")
    if "results" not in r:
        print(f"  WARNING: list failed")
        return
    count = len(r["results"])
    if count == 0:
        print(f"  No test memories to clear")
        return
    for m in r["results"]:
        api_call("DELETE", f"/v1/memories/{m['id']}/")
    print(f"  Cleared {count} test memories")

def add_memories(user_id="bench-test"):
    results = []
    for i, text in enumerate(TEST_MEMORIES):
        t0 = time.time()
        r = api_call("POST", "/v3/memories/add/", {
            "messages": [{"role": "user", "content": text}],
            "user_id": user_id, "infer": True,
            "metadata": {"test_idx": i}})
        elapsed = (time.time() - t0) * 1000
        ok = "results" in r if isinstance(r, dict) else False
        mem_count = len(r.get("results", [])) if ok else 0
        results.append({"idx": i, "ms": round(elapsed), "ok": ok, "memories": mem_count,
            "error": r.get("error", {}).get("message", "")[:100] if isinstance(r, dict) and "error" in r else ""})
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
            if idx in relevant:
                mrr = 1.0 / (rank + 1)
                break
        results.append({"query": query, "ms": round(elapsed),
            "total_hits": len(hits), "hit_idxs": hit_idxs,
            "relevant": relevant, "recalled": recalled,
            "recall_pct": recalled/len(relevant)*100 if relevant else 0,
            "mrr": mrr})
    return results

def run_profile(pid):
    cfg = PROFILES[pid]
    print(f"\n{'='*70}")
    print(f"Profile {pid}: {cfg['name']}")
    print(f"{'='*70}")

    print("  [1] Configure...")
    r = configure(cfg)
    if "error" in r:
        print(f"  CONFIGURE FAILED: {r['error'].get('message','')[:200]}")
        return None
    print(f"  OK")

    print("  [2] Clear test data...")
    clear()
    time.sleep(1)

    print("  [3] Add 10 memories...")
    add_r = add_memories()
    ok_count = sum(1 for r in add_r if r["ok"])
    avg_ms = sum(r["ms"] for r in add_r) / len(add_r)
    total_mem = sum(r["memories"] for r in add_r if r["ok"])
    print(f"  {ok_count}/10 OK, avg {avg_ms:.0f}ms, {total_mem} memories extracted")
    for r in add_r:
        if not r["ok"]:
            print(f"    FAIL #{r['idx']}: {r['error']}")

    time.sleep(2)

    print("  [4] Search 8 queries...")
    search_r = search_memories()
    avg_search_ms = sum(r["ms"] for r in search_r) / len(search_r)
    total_recall = sum(r["recalled"] for r in search_r)
    total_relevant = sum(len(r["relevant"]) for r in search_r)
    avg_mrr = sum(r["mrr"] for r in search_r) / len(search_r)
    print(f"  avg {avg_search_ms:.0f}ms, recall {total_recall}/{total_relevant}={total_recall/total_relevant*100:.1f}%, MRR {avg_mrr:.3f}")

    for r in search_r:
        tag = "HIT" if r["recalled"] > 0 else "MISS"
        print(f"    {r['query'][:25]:25s} {tag:4s} recall={r['recall_pct']:.0f}% mrr={r['mrr']:.2f} {r['ms']}ms")

    result = {
        "profile": pid, "name": cfg["name"], "ts": datetime.now().isoformat(),
        "add_ok": ok_count, "add_avg_ms": round(avg_ms), "total_memories": total_mem,
        "search_avg_ms": round(avg_search_ms),
        "recall": f"{total_recall}/{total_relevant}",
        "recall_pct": round(total_recall/total_relevant*100, 1),
        "mrr": round(avg_mrr, 3),
        "add_details": add_r, "search_details": search_r,
    }

    rdir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
    os.makedirs(rdir, exist_ok=True)
    path = os.path.join(rdir, f"{pid}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    with open(path, "w") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"  Saved: {path}")
    return result

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--profile", nargs="+", default=["A"])
    p.add_argument("--all", action="store_true")
    args = p.parse_args()
    if args.all:
        profiles = list(PROFILES.keys())
    else:
        profiles = args.profile

    r = api_call("GET", "/v1/ping/")
    print(f"Server: {r}")
    if "status" not in r:
        print(f"Server down: {r}")
        sys.exit(1)

    all_r = []
    for pid in profiles:
        r = run_profile(pid)
        if r:
            all_r.append(r)
        time.sleep(1)

    print(f"\n{'='*70}")
    print(f"SUMMARY")
    print(f"{'='*70}")
    print(f"{'Profile':8s} {'Add OK':8s} {'Add ms':8s} {'Mem#':6s} {'Search ms':10s} {'Recall':10s} {'MRR':8s}")
    for r in all_r:
        print(f"{r['profile']:8s} {r['add_ok']:3d}/10  {r['add_avg_ms']:6d}   {r['total_memories']:4d}   {r['search_avg_ms']:8d}   {r['recall']:>8s}   {r['mrr']:6.3f}")
