#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

if [[ -f "$REPO_ROOT/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "$REPO_ROOT/.env"
    set +a
fi

cd "$REPO_ROOT"

# ===== 按需修改以下变量 =====
AGENT_TYPE="${AGENT_TYPE:-qwen3_6_plus}"                          # 使用专用 Qwen3.6-plus agent
TASK="${TASK:-ALL}"                                                # 配合 TASK_TAGS，仅评测指定标签任务
TASK_TAGS="${TASK_TAGS:-routine,preference,general}"               # 默认评测 routine / preference / general
MODEL_NAME="${MODEL_NAME:-qwen3.6-plus}"                           # DashScope 上的 Qwen 模型名
LLM_BASE_URL="${LLM_BASE_URL:-https://dashscope.aliyuncs.com/compatible-mode/v1}" # DashScope OpenAI-compatible 地址
QWEN3_6_PLUS_API_KEY="${QWEN3_6_PLUS_API_KEY:-sk-E7cpAYEyWA098oDM5URpPQ}" # 仅供本脚本主模型使用，避免和 .env 中的 DASHSCOPE_API_KEY 混用
MAX_CONCURRENCY="${MAX_CONCURRENCY:-8}"                            # 并发数，建议不超过可用环境数
MAX_ROUND="${MAX_ROUND:-50}"                                       # 每个任务最多交互轮数
STEP_WAIT_TIME="${STEP_WAIT_TIME:-3}"                              # 每步后的等待时间
ENV_IMAGE="${ENV_IMAGE:-ghcr.io/yaosqz/knowu-bench:latest}"       # 自动发现容器时使用的默认镜像
AW_HOST="${AW_HOST:-http://127.0.0.1:6800,http://127.0.0.1:6801,http://127.0.0.1:6802,http://127.0.0.1:6803,http://127.0.0.1:6804,http://127.0.0.1:6805,http://127.0.0.1:6806,http://127.0.0.1:6807}" # 多环境地址；留空可自动发现
USER_FILTER="${USER_FILTER:-}"                                     # 可选: user / student / developer / grandma
USER_LOG_SOURCE="${USER_LOG_SOURCE:-noise}"                        # clean / noise
USER_LOG_MODE="${USER_LOG_MODE:-all}"                              # all / rag
RAG_TOP_K="${RAG_TOP_K:-10}"
RAG_BACKEND="${RAG_BACKEND:-embedding}"                            # tfidf / embedding
ENABLE_MCP="${ENABLE_MCP:-false}"                                  # true 时额外纳入带 agent-mcp 的任务
# ============================

is_placeholder() {
    local value="$1"
    shift

    if [[ -z "$value" ]]; then
        return 0
    fi

    for placeholder in "$@"; do
        if [[ "$value" == "$placeholder" ]]; then
            return 0
        fi
    done

    return 1
}

AGENT_API_KEY="$QWEN3_6_PLUS_API_KEY"
if is_placeholder \
    "$AGENT_API_KEY" \
    "REPLACE_WITH_YOUR_API_KEY" \
    "your_qwen3_6_plus_api_key" \
    "your_api_key_for_agent_model" \
    "EMPTY"; then
    echo "请先设置 QWEN3_6_PLUS_API_KEY。" >&2
    exit 1
fi

if [[ "$LLM_BASE_URL" == "[dashscope_openai_compatible_base_url]" ]]; then
    echo "请先设置 LLM_BASE_URL 为 DashScope 的 OpenAI-compatible 服务地址。" >&2
    exit 1
fi

export QWEN3_6_PLUS_API_KEY="$AGENT_API_KEY"

# routine / preference 任务通常会触发 ask-user 或 preference judge。
# 如果你没有单独指定 USER_AGENT_*，这里默认复用主模型配置，保证脚本可直接运行。
if is_placeholder \
    "${USER_AGENT_API_KEY:-}" \
    "your_user_agent_llm_api_key" \
    "REPLACE_WITH_YOUR_API_KEY" \
    "EMPTY"; then
    export USER_AGENT_API_KEY="$AGENT_API_KEY"
fi
export USER_AGENT_API_KEY="${USER_AGENT_API_KEY:-$AGENT_API_KEY}"

if is_placeholder \
    "${USER_AGENT_BASE_URL:-}" \
    "your_user_agent_base_url" \
    "https://your-openai-compatible-endpoint/v1"; then
    export USER_AGENT_BASE_URL="$LLM_BASE_URL"
fi
export USER_AGENT_BASE_URL="${USER_AGENT_BASE_URL:-$LLM_BASE_URL}"

if is_placeholder \
    "${USER_AGENT_MODEL:-}" \
    "your_user_agent_model" \
    "placeholder_user_agent_model"; then
    export USER_AGENT_MODEL="$MODEL_NAME"
fi
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
echo "Agent 类型: $AGENT_TYPE"
echo "Base URL: $LLM_BASE_URL"
echo "任务标签: $TASK_TAGS"
echo "并发数: $MAX_CONCURRENCY"
echo "日志目录: $LOG_ROOT"
echo "日志文件: $RUN_LOG"
echo "USER_AGENT_MODEL: $USER_AGENT_MODEL"
if [[ -n "$AW_HOST" ]]; then
    echo "后端地址: $AW_HOST"
else
    echo "后端地址: 自动发现 knowu_bench_env_* 容器（镜像过滤: $ENV_IMAGE）"
fi
