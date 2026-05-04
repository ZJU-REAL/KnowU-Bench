#!/usr/bin/env bash
set -euo pipefail

# ===== 按需修改以下变量 =====
AGENT_TYPE="${AGENT_TYPE:-general_e2e}"      # 使用通用端到端 agent
TASK="${TASK:-ALL}"                          # 配合 TASK_TAGS，仅评测指定标签任务
TASK_TAGS="${TASK_TAGS:-routine,preference}" # 只评测 routine / preference
MODEL_NAME="${MODEL_NAME:-claude-opus-4-6-20260205}" # 名称里建议保留 claude，触发 Claude 专用缩放逻辑
LLM_BASE_URL="${LLM_BASE_URL:-http://101.37.174.109:8010/v1}" # 必须是 OpenAI-compatible 地址
CLAUDE_API_KEY="sk-E7cpAYEyWA098oDM5URpPQ"   # 直接把 Claude / OpenRouter 的 key 写在这里
MAX_CONCURRENCY="${MAX_CONCURRENCY:-4}"      # 并发数，建议不超过可用环境数
MAX_ROUND="${MAX_ROUND:-50}"                 # 每个任务最多交互轮数
STEP_WAIT_TIME="${STEP_WAIT_TIME:-4}"        # 每步后的等待时间
ENV_IMAGE="${ENV_IMAGE:-ghcr.io/yaosqz/knowu-bench:latest}" # 自动发现容器时使用的默认镜像
AW_HOST="${AW_HOST:-http://127.0.0.1:6805,http://127.0.0.1:6806,http://127.0.0.1:6807,http://127.0.0.1:6808}"
USER_FILTER="${USER_FILTER:-}"               # 可选: user / student / developer / grandma
USER_LOG_SOURCE="${USER_LOG_SOURCE:-noise}"  # clean / noise
USER_LOG_MODE="${USER_LOG_MODE:-all}"        # all / rag
RAG_TOP_K="${RAG_TOP_K:-10}"
RAG_BACKEND="${RAG_BACKEND:-embedding}"      # tfidf / embedding
ENABLE_MCP="${ENABLE_MCP:-false}"            # true 时额外纳入带 agent-mcp 的 routine/preference 任务
# ============================

# 主评测模型 API Key 直接取脚本里的 CLAUDE_API_KEY。
AGENT_API_KEY="$CLAUDE_API_KEY"
if [[ -z "$AGENT_API_KEY" || "$AGENT_API_KEY" == "REPLACE_WITH_YOUR_API_KEY" ]]; then
    echo "请先在脚本顶部把 CLAUDE_API_KEY 改成你的真实 API Key。" >&2
    exit 1
fi

# routine / preference 任务通常会触发 ask-user 或 preference judge。
# 如果你没有单独指定 USER_AGENT_*，这里默认复用主模型配置，保证脚本可直接运行。
export USER_AGENT_API_KEY="${USER_AGENT_API_KEY:-$AGENT_API_KEY}"
export USER_AGENT_BASE_URL="${USER_AGENT_BASE_URL:-$LLM_BASE_URL}"
export USER_AGENT_MODEL="${USER_AGENT_MODEL:-$MODEL_NAME}"

export NO_PROXY="${NO_PROXY:-localhost,127.0.0.1,::1,10.130.138.46,10.130.138.47,10.130.138.48}"

MODEL_TAG="${MODEL_NAME//\//_}"
MODEL_TAG="${MODEL_TAG//-/_}"
TASK_TAGS_TAG="${TASK_TAGS//,/_}"
USER_TAG="${USER_FILTER:-all_users}"
MCP_TAG="no_mcp"
if [[ "$ENABLE_MCP" == "true" ]]; then
    MCP_TAG="with_mcp"
fi

LOG_ROOT="traj_logs/${MODEL_TAG}_${TASK_TAGS_TAG}_${USER_TAG}_${USER_LOG_SOURCE}_${USER_LOG_MODE}_${RAG_BACKEND}_${MCP_TAG}"
mkdir -p "$LOG_ROOT"
RUN_LOG="$LOG_ROOT/nohup_$(date +%Y%m%d_%H%M%S).log"

USER_ARGS=()
if [[ -n "$USER_FILTER" ]]; then
    USER_ARGS=(--user "$USER_FILTER")
fi

MCP_ARGS=()
if [[ "$ENABLE_MCP" == "true" ]]; then
    MCP_ARGS=(--enable_mcp)
fi

AW_HOST_ARGS=()
if [[ -n "$AW_HOST" ]]; then
    AW_HOST_ARGS=(--aw-host "$AW_HOST")
fi

nohup mw eval \
    --agent_type "$AGENT_TYPE" \
    --task "$TASK" \
    --task-tags "$TASK_TAGS" \
    --enable-user-interaction \
    --max_round "$MAX_ROUND" \
    --model_name "$MODEL_NAME" \
    --llm_base_url "$LLM_BASE_URL" \
    --api_key "$AGENT_API_KEY" \
    --step_wait_time "$STEP_WAIT_TIME" \
    --env-image "$ENV_IMAGE" \
    --max-concurrency "$MAX_CONCURRENCY" \
    --log_file_root "$LOG_ROOT" \
    "${AW_HOST_ARGS[@]}" \
    --user-log-source "$USER_LOG_SOURCE" \
    --user-log-mode "$USER_LOG_MODE" \
    --rag-top-k "$RAG_TOP_K" \
    --rag-backend "$RAG_BACKEND" \
    "${MCP_ARGS[@]}" \
    "${USER_ARGS[@]}" > "$RUN_LOG" 2>&1 &

echo "任务已在后台启动 PID=$!"
echo "主模型: $MODEL_NAME"
echo "Base URL: $LLM_BASE_URL"
echo "任务标签: $TASK_TAGS"
echo "并发数: $MAX_CONCURRENCY"
echo "日志文件: $RUN_LOG"
echo "USER_AGENT_MODEL: $USER_AGENT_MODEL"
if [[ -n "$AW_HOST" ]]; then
    echo "后端地址: $AW_HOST"
else
    echo "后端地址: 自动发现 knowu_bench_env_* 容器（镜像过滤: $ENV_IMAGE）"
fi
