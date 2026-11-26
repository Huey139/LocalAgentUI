# LocalAgentUI

**本地 AI 团队管理与编排系统（Local AI Workforce Management & Orchestration System）**

LocalAgentUI 是一个实验性本地项目，尝试借鉴人类团队的管理方式来组织和管理多个 AI Agent。它不是把一个目标交给 AI 后，就允许 AI 不受限制地自行决定所有任务和操作；项目希望通过角色、职责、专业能力、工具、权限、工作规划和人工审批机制，建立一个可管理、可监督的 AI 团队。

项目也希望通过图形化界面降低 Agent 管理的技术门槛，让非技术用户能够配置 Agent、Capability、Tool、模型和项目流程，而不必直接处理所有底层代码和接口。

> **项目状态：早期开发 / 实验性项目。** LocalAgentUI 是基于个人设备开展的小规模实践，目前主要在 macOS 上开发和测试。项目重点是探索 AI 组织管理与受管理的自主性，并非已经具备生产级能力的企业平台。功能和界面仍可能发生变化。

## 设计理念

- **组织 AI，而不只是使用 AI：** 通过角色和职责组织专业 Agent，由 Main Agent 负责协调工作。
- **受管理的自主性：** 区分目标方向、任务规划和具体操作权限；重要决策及敏感操作应受人工审批和策略检查约束。
- **可视化管理：** 通过界面配置 Agent、Capability、Tool 和项目，让非技术人员也能参与管理本地 Agent。
- **结构化工作：** 将对话、Proposal、Project、Workspace、Task 和交付物关联起来，而不是把每次请求都当作孤立 Prompt。
- **证据与责任：** 优先采用 Backend 验证的执行状态和登记的 Artifact，而不是仅凭 Agent 自述认定任务完成。
- **持续发展：** 探索 Agent 如何配置、评估、扩展能力并根据经验改进。

## 当前功能范围

当前代码库包含以下模块，具体实现和限制请参阅 `docs/`：

- React/Vite 前端和 FastAPI 后端。
- Main Agent 对话及 Specialist Agent 调度。
- Agent 管理、模型分配和 Capability/Tool 权限解析。
- Proposal、Project 工作流、任务规划和执行授权。
- P0–P6 Prompt 组装及运行时/会话上下文。
- SQLite 数据库初始化和版本化迁移。
- Temporary、Project、Global Workspace 记录及 Artifact Registry。
- Ollama 本地模型发现，以及 OpenAI 兼容的 Chat Completion 请求。
- 配置 SerpApi Key 后可使用的可选网页搜索。

## 环境要求

- macOS：当前主要开发和测试平台。
- Python **3.10 或更高版本**。
- Node.js **20.19+ 或 22.13+**（当前 Vite 依赖树要求）；npm 随 Node.js 安装。
- Ollama 和至少一个兼容的本地模型：使用 LLM 功能时需要。
- Git：建议安装，用于克隆和更新代码。

SQLite 使用 Python 标准库，通常不需要单独安装。

## macOS 快速开始

1. 安装 Python、Node.js 和 Ollama，详见[安装指南](docs/INSTALLATION.md)。
2. 使用 Ollama 下载并安装一个模型，例如：

   ```bash
   ollama pull qwen3:1.7b
   ```

3. 克隆项目并进入目录：

   ```bash
   git clone https://github.com/Huey139/LocalAgentUI.git
   cd LocalAgentUI
   ```

4. 如需自定义配置，可复制环境变量模板：

   ```bash
   cp .env.example .env
   ```

5. 启动应用：

   ```bash
   chmod +x START_LOCAL_AGENT.command
   ./START_LOCAL_AGENT.command
   ```

   首次启动时，脚本会按需创建 Python 虚拟环境、安装后端依赖；当前端依赖目录不存在时，会安装前端依赖，然后启动前后端服务。

6. 浏览器访问 `http://127.0.0.1:5173`。Backend API 地址为 `http://127.0.0.1:8000`，API 文档为 `http://127.0.0.1:8000/docs`。

停止服务：

```bash
./STOP_LOCAL_AGENT.command
```

详细安装、配置和故障排查请查看：

- [安装指南](docs/INSTALLATION.md)
- [配置说明](docs/CONFIGURATION.md)
- [故障排查](docs/TROUBLESHOOTING.md)
- [架构总览](docs/architecture/README.md)

## 数据与隐私

默认 SQLite 数据库位于 `data/local_agent.db`。聊天记录和 Agent 配置默认存储在 `~/AgentWorkspace/.agent_state`。受管工作区位于项目目录下的 `workspaces/`，公共输出位于 `global/outputs/`。这些位置可能包含个人或项目数据，不应提交到公开 Git 仓库。

本地模型请求会发送到配置的 Ollama Endpoint。启用可选网页搜索后，搜索查询会发送给 SerpApi。处理敏感信息前，请自行确认相关服务条款和数据处理要求。

## 代码目录

```text
backend/       FastAPI 应用、Agent Runtime、治理、工具和数据库
frontend/      React/Vite 用户界面
docs/          安装、配置、架构和工作流文档
workspaces/    运行时工作区（用户数据，内容由 Git 忽略）
global/        运行时公共输出（内容由 Git 忽略）
data/          本地 SQLite 数据库（由 Git 忽略）
```

## 参与开发与安全问题

项目仍处于早期阶段。提交改进前请阅读 [CONTRIBUTING.md](CONTRIBUTING.md)。安全问题请按照 [SECURITY.md](SECURITY.md) 中的方式报告。

## 开源许可

目前尚未选择开源许可证。在正式添加许可证之前，请勿假设项目代码可以不受限制地复用、修改或再分发。
