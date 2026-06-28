#!/usr/bin/env python3
"""Test DashScope embedding models for dimensions and image support."""
import json, os, sys, time, urllib.request, urllib.error

# Load API key from server .env
API_KEY = None
with open(os.path.expanduser("~/AI/Ext/mem0/server/.env")) as f:
    for line in f:
        if line.startswith("OPENAI_API_KEY="):
            API_KEY = line.strip().split("=", 1)[1]
            break
if not API_KEY:
    print("ERROR: OPENAI_API_KEY not found in server/.env")
    sys.exit(1)

BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"
NATIVE_BASE = "https://dashscope.aliyuncs.com/api/v1/services"

def api_call(url, body, timeout=30):
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        err = e.read().decode()
        try:
            return json.loads(err)
        except:
            return {"error": {"message": err[:300]}}
    except Exception as e:
        return {"error": {"message": str(e)[:300]}}

def test_text_embed(model, dims=None):
    body = {"model": model, "input": "测试文本embedding维度"}
    if dims:
        body["dimensions"] = dims
    d = api_call(f"{BASE}/embeddings", body)
    if "data" in d:
        return {"dims": len(d["data"][0]["embedding"]), "model": d.get("model", ""), "status": "OK"}
    elif "error" in d:
        return {"status": "ERROR", "error": d["error"].get("message", "")[:200]}
    return {"status": "UNKNOWN", "raw": str(d)[:200]}

def test_vl_embed_image(model):
    """Test multimodal embedding with image input via compatible API."""
    body = {
        "model": model,
        "input": [
            {"type": "image_url", "image_url": {"url": "https://dashscope.oss-cn-beijing.aliyuncs.com/images/dog_and_cat.png"}}
        ]
    }
    d = api_call(f"{BASE}/embeddings", body)
    if "data" in d:
        return {"dims": len(d["data"][0]["embedding"]), "model": d.get("model", ""), "status": "OK"}
    elif "error" in d:
        return {"status": "ERROR", "error": d["error"].get("message", "")[:200]}
    return {"status": "UNKNOWN", "raw": str(d)[:200]}

def test_native_vision_embed(model):
    """Test via DashScope native multimodal embeddings API."""
    body = {
        "model": model,
        "input": {
            "messages": [
                {"role": "user", "content": [
                    {"type": "image_url", "image_url": "https://dashscope.oss-cn-beijing.aliyuncs.com/images/dog_and_cat.png"},
                    {"type": "text", "text": "描述这张图片"}
                ]}
            ]
        }
    }
    d = api_call(f"{NATIVE_BASE}/embeddings/multimodal-embeddings/multimodal-embeddings", body)
    if "output" in d:
        emb = d["output"].get("embeddings", [{}])
        return {"status": "OK", "dims": len(emb[0].get("embedding", [])) if emb else 0, "keys": list(d["output"].keys())}
    elif "error" in d:
        return {"status": "ERROR", "error": d.get("error", {}).get("message", "")[:300]}
    return {"status": "UNKNOWN", "raw": str(d)[:300]}

def test_rerank(model, query, documents):
    """Test reranker via native DashScope API."""
    body = {
        "model": model,
        "input": {"query": query, "documents": documents}
    }
    d = api_call(f"{NATIVE_BASE}/rerank/text-rerank/text-rerank", body)
    if "output" in d:
        results = d["output"].get("results", [])
        return {"status": "OK", "scores": [(r["index"], round(r["relevance_score"], 4)) for r in results]}
    elif "error" in d:
        return {"status": "ERROR", "error": d.get("error", {}).get("message", "")[:300]}
    return {"status": "UNKNOWN", "raw": str(d)[:300]}

# === Run Tests ===
print("=" * 70)
print("DashScope Embedding Model Dimension Test")
print("=" * 70)

# 1. Text embedding dimensions
print("\n--- Text Embedding ---")
for model in ["text-embedding-v3", "text-embedding-v4", "qwen3-vl-embedding", "tongyi-embedding-vision-plus-2026-03-06"]:
    r = test_text_embed(model)
    if r["status"] == "OK":
        print(f"  {model:45s} dims={r['dims']:5d}  returned_model={r['model']}")
    else:
        print(f"  {model:45s} ERROR: {r.get('error', '')[:100]}")

# 2. text-embedding-v4 with different dimensions
print("\n--- text-embedding-v4 dimension options ---")
for dims in [2048, 1536, 1024, 768, 512]:
    r = test_text_embed("text-embedding-v4", dims=dims)
    if r["status"] == "OK":
        print(f"  dims={dims}: actual={r['dims']}")
    else:
        print(f"  dims={dims}: ERROR {r.get('error', '')[:100]}")

# 3. VL/Vision embedding with image input (compatible API)
print("\n--- VL/Vision Embedding with Image (compatible API) ---")
for model in ["qwen3-vl-embedding", "tongyi-embedding-vision-plus-2026-03-06"]:
    r = test_vl_embed_image(model)
    if r["status"] == "OK":
        print(f"  {model}: image dims={r['dims']}")
    else:
        print(f"  {model}: ERROR {r.get('error', '')[:150]}")

# 4. Native multimodal embedding API
print("\n--- Native Multimodal Embedding API ---")
for model in ["tongyi-embedding-vision-plus-2026-03-06", "qwen3-vl-embedding"]:
    r = test_native_vision_embed(model)
    print(f"  {model}: {r}")

# 5. Reranker tests
print("\n--- Reranker Test (text) ---")
docs = ["我在用FastAPI写后端", "今天天气不错", "PostgreSQL的pgvector支持向量检索"]
for model in ["qwen3-rerank", "qwen3-vl-rerank"]:
    r = test_rerank(model, "后端开发框架", docs)
    print(f"  {model}: {r}")

print("\n--- Done ---")
