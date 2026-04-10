#!/usr/bin/env bash
set -euo pipefail

# ===== 按需修改以下变量 =====
AGENT_TYPE="${AGENT_TYPE:-general_e2e}"            # 使用通用端到端 agent
TASK="${TASK:-ALL}"                                # 配合 TASK_TAGS，仅评测指定标签任务
TASK_TAGS="${TASK_TAGS:-routine,preference}"       # 默认只评测 routine / preference
MODEL_NAME="${MODEL_NAME:-google/gemini-3.1-pro-preview}"   # Gemini 模型名
LLM_BASE_URL="${LLM_BASE_URL:-https://openrouter.ai/api/v1}" # 必须是 OpenAI-compatible 地址
GEMINI_API_KEY="${GEMINI_API_KEY:-${GOOGLE_API_KEY:-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}}"            # 优先读取 GEMINI_API_KEY，其次读取 GOOGLE_API_KEY
MAX_CONCURRENCY="${MAX_CONCURRENCY:-8}"            # 并发数，建议不超过可用环境数
MAX_ROUND="${MAX_ROUND:-50}"                       # 每个任务最多交互轮数
STEP_WAIT_TIME="${STEP_WAIT_TIME:-5}"              # 每步后的等待时间
AW_HOST="${AW_HOST:-http://127.0.0.1:6800,http://127.0.0.1:6801,http://127.0.0.1:6802,http://127.0.0.1:6803,http://127.0.0.1:6804,http://127.0.0.1:6805,http://127.0.0.1:6806,http://127.0.0.1:6807}" # 多环境地址；留空可自动发现
USER_FILTER="${USER_FILTER:-}"                     # 可选: user / student / developer / grandma
USER_LOG_SOURCE="${USER_LOG_SOURCE:-noise}"        # clean / noise
USER_LOG_MODE="${USER_LOG_MODE:-all}"              # all / rag
RAG_TOP_K="${RAG_TOP_K:-10}"
RAG_BACKEND="${RAG_BACKEND:-embedding}"            # tfidf / embedding
ENABLE_MCP="${ENABLE_MCP:-false}"                  # true 时额外纳入带 agent-mcp 的 routine/preference 任务
# ============================

AGENT_API_KEY="$GEMINI_API_KEY"
if [[ -z "$AGENT_API_KEY" || "$AGENT_API_KEY" == "REPLACE_WITH_YOUR_API_KEY" ]]; then
    echo "请先设置 GEMINI_API_KEY 或 GOOGLE_API_KEY。" >&2
    exit 1
fi

if [[ "$LLM_BASE_URL" == "[gemini_openai_compatible_base_url]" ]]; then
    echo "请先设置 LLM_BASE_URL 为 Gemini 的 OpenAI-compatible 服务地址。" >&2
    exit 1
fi

# routine / preference 任务通常会触发 ask-user 或 preference judge。
# 如果你没有单独指定 USER_AGENT_*，这里默认复用主模型配置，保证脚本可直接运行。
export USER_AGENT_API_KEY="${USER_AGENT_API_KEY:-$AGENT_API_KEY}"
export USER_AGENT_BASE_URL="${USER_AGENT_BASE_URL:-$LLM_BASE_URL}"
export USER_AGENT_MODEL="${USER_AGENT_MODEL:-$MODEL_NAME}"

export NO_PROXY="${NO_PROXY:-localhost,127.0.0.1,::1,10.130.138.46,10.130.138.47,10.130.138.48}"

MODEL_TAG="${MODEL_NAME//\//_}"
MODEL_TAG="${MODEL_TAG//./_}"
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

nohup mw eval     --agent_type "$AGENT_TYPE"     --task "$TASK"     --task-tags "$TASK_TAGS"     --enable-user-interaction     --max_round "$MAX_ROUND"     --model_name "$MODEL_NAME"     --llm_base_url "$LLM_BASE_URL"     --api_key "$AGENT_API_KEY"     --step_wait_time "$STEP_WAIT_TIME"     --max-concurrency "$MAX_CONCURRENCY"     --log_file_root "$LOG_ROOT"     "${AW_HOST_ARGS[@]}"     --user-log-source "$USER_LOG_SOURCE"     --user-log-mode "$USER_LOG_MODE"     --rag-top-k "$RAG_TOP_K"     --rag-backend "$RAG_BACKEND"     "${MCP_ARGS[@]}"     "${USER_ARGS[@]}" > "$RUN_LOG" 2>&1 &

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
    echo "后端地址: 自动发现 knowu_bench_env_* 容器"
fi
