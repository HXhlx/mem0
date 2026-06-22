# Mem0 自托管服务 + Codex 插件本地适配指南

## 当前兼容性状态

| 组件 | 状态 | 说明 |
|------|------|------|
| MCP 9 工具 | ✅ 已实现 | `add_memory`, `search_memories`, `get_memories`, `get_memory`, `update_memory`, `delete_memory`, `delete_all_memories`, `list_entities`, `delete_entities`（由 `mem0-mcp/` 提供） |
| Bearer/Token 认证 | ✅ 已支持 | `mem0-mcp` 的 `TokenAuthMiddleware` 同时支持两种 scheme |
| SSE + Streamable HTTP 传输 | ✅ 已支持 | `combined` 模式在 9003 端口同端口提供 `/sse` + `/mcp` |
| Docker 配置 | ✅ 已配置 | `docker-compose.override.yaml` 构建 `../mem0-mcp` |
| SDK 兼容端点 | ✅ 已实现 | `/v3/memories/add/` 等（由 `self_mem0/server/sdk_compat.py` 提供） |
| 生命周期 Hooks | ✅ 已支持 | `install_codex_hooks.py --self-hosted` |

---

## 快速开始

### 1. 启动自托管服务

```bash
cd server
docker-compose -f docker-compose.yaml -f docker-compose.override.yaml up -d
```

服务启动后：
- **REST API**: http://localhost:8888
- **MCP Bridge SSE**: http://localhost:9003

### 2. 设置环境变量

在 shell profile 中添加：

```bash
export MEM0_HOST="http://localhost:8888"   # REST API 端点
export MEM0_API_KEY="your-admin-api-key"   # 与 docker-compose .env 中的 ADMIN_API_KEY 一致
```

### 3. 配置 Codex

#### 方式 A：仅 MCP（最快）

编辑 `~/.codex/config.toml`：

```toml
[mcp_servers.mem0]
url = "http://localhost:9003/sse"
bearer_token_env_var = "MEM0_API_KEY"
```

或使用模板：`cp mem0-plugin/config.local.toml ~/.codex/config.toml`

#### 方式 B：MCP + 生命周期 Hooks（完整体验）

```bash
# 1. 安装 hooks（自动替换 API URL 为本地地址）
python3 mem0-plugin/scripts/install_codex_hooks.py --self-hosted

# 2. 切换 MCP 配置到本地
cp mem0-plugin/.codex-mcp.local.json mem0-plugin/.codex-mcp.json

# 3. 确保 config.toml 包含 feature flag
# （installer 会在未启用时提示）
```

`--self-hosted` 参数会：
- 将 hooks 脚本中的 `https://api.mem0.ai` 替换为 `$MEM0_HOST`
- 支持 `--host` 指定自定义地址（默认 `http://localhost:8888`）

Hooks 提供以下自动行为：

| 事件 | 作用 |
|------|------|
| `SessionStart` | 加载历史记忆作为启动上下文 |
| `UserPromptSubmit` | 向提示注入相关记忆 |
| `PreToolUse` | 强制 MCP 工具调用带默认元数据 |
| `PostToolUse` | 工具调用后处理 |
| `Stop` | 提醒 Agent 持久化学习结果 |

### 4. 配置 Claude Code（可选）

编辑 `~/.claude/settings.json`：

```json
{
  "mcpServers": {
    "mem0": {
      "serverUrl": "http://localhost:9003/",
      "headers": {
        "Authorization": "Token $MEM0_API_KEY"
      }
    }
  }
}
```

配置模板：`cp self-mem0/examples/claude-mcp.local.json ~/.claude/settings.json`

### 5. 运行插件补丁脚本（每次插件升级后）

```bash
./self-mem0/plugins/patch_mem0_plugin.sh
```

这会将插件内的硬编码 URL `https://api.mem0.ai` 替换为读取 `MEM0_HOST` 环境变量。

---

## 配置文件清单

| 文件 | 用途 | 适用场景 |
|------|------|----------|
| `mem0-plugin/.codex-mcp.json` | Codex MCP 配置（托管） | 默认 |
| `mem0-plugin/.codex-mcp.local.json` | Codex MCP 配置（本地） | 自托管 |
| `mem0-plugin/config.local.toml` | Codex config.toml 模板 | 自托管 |
| `mem0-plugin/mcp_config.json` | Claude Code MCP（托管） | 默认 |
| `self-mem0/examples/codex-mcp.local.json` | Codex MCP 示例 | 参考 |
| `self-mem0/examples/claude-mcp.local.json` | Claude Code MCP 示例 | 参考 |

---

## 故障排除

### MCP 连接失败

```bash
# 检查 mem0-mcp 服务
curl http://localhost:9003/health  # 应返回: ok

# 检查环境变量
echo $MEM0_API_KEY
echo $MEM0_HOST

# 查看 mem0-mcp 日志
docker logs mem0-mcp
```

### 认证失败

确保 `MEM0_API_KEY` 与 docker-compose `.env` 中的 `ADMIN_API_KEY` 一致。`mem0-mcp` 的 `TokenAuthMiddleware` 同时支持 `Bearer` 和 `Token` scheme。

### Hooks 不触发

1. 检查 `~/.codex/config.toml` 是否有 `codex_hooks = true`
2. 检查 `~/.codex/hooks.json` 是否有 mem0 条目
3. 重启 Codex

### REST API 404

确保 `MEM0_HOST=http://localhost:8888`（REST API 端口，不是 MCP 的 9003）。