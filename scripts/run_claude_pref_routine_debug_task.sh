#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

# ===== 按需修改以下变量 =====
DEFAULT_DEBUG_TASKS=(
    # Dynamic-time tasks changed in the latest pass.
    "MorningPaperReadingGeneralTask"
    "MorningWeatherCheckGeneralTask"
    "MattermostResponseGeneralTask"
    "NightSocialGeneralTask"
    "SendWeeklyReportGeneralTask"
    "WeeklyReportRoutineTask@user"
    "ClockOutGeneralTask"
    "ClockOutRoutineTask@developer"
    "DailyFamilyCallTask@grandma"
    "DeepWorkRoutineTask@user"
    "MorningPaperReadingTask@user"
    "MorningWeatherCheckTask@grandma"
    "ScamSmsInterceptRoutineTask@user"
    # Routine tasks that exercise Mattermost/Mastodon dynamic time paths.
    "MattermostOnCallTask@developer"
    "NightEyeCareRoutineTask@user"
    # Additional Mattermost smoke coverage.
    "MattermostLeaveNoticeGeneralTask"
    "MattermostLeaveNoticeTask@developer"
    "CommuteLateWithNoticeGeneralTask"
    "LateUrgentRouteWithNoticeTask@developer"
    "CalendarScheduleGroupMeetingGeneralTask"
    "CalendarScheduleGroupMeetingTask@developer"
    # Additional Mastodon smoke coverage.
    "MastodonInterestBoostGeneralTask"
    "MastodonInterestBoostTask@user"
    "MastodonPrivacyDefaultGeneralTask"
    "MastodonPrivacyDefaultTestTask@user"
    "MastodonSharePhotosGeneralTask"
    "MastodonSharePhotosPreferenceAskUserTask@user"
)
DEFAULT_TASK="$(IFS=,; echo "${DEFAULT_DEBUG_TASKS[*]}")"

AGENT_TYPE="${AGENT_TYPE:-general_e2e}"
TASK="${1:-${TASK:-$DEFAULT_TASK}}"                                    # 支持逗号分隔的多任务列表
TASK_TAGS="${TASK_TAGS:-}"
MODEL_NAME="${MODEL_NAME:-claude-opus-4-6-20260205}" # 名称里保留 claude，触发 Claude 专用缩放逻辑
LLM_BASE_URL="${LLM_BASE_URL:-http://101.37.174.109:8010/v1}" # OpenAI-compatible 中转地址
CLAUDE_API_KEY="${CLAUDE_API_KEY:-sk-E7cpAYEyWA098oDM5URpPQ}"
MAX_CONCURRENCY="${MAX_CONCURRENCY:-4}"
MAX_ROUND="${MAX_ROUND:-50}"
STEP_WAIT_TIME="${STEP_WAIT_TIME:-4}"
ENV_IMAGE="${ENV_IMAGE:-knowu-bench:latest}"
AW_HOST="${AW_HOST:-http://127.0.0.1:6800,http://127.0.0.1:6802,http://127.0.0.1:6803,http://127.0.0.1:6804}"
USER_FILTER="${USER_FILTER:-}"
USER_LOG_SOURCE="${USER_LOG_SOURCE:-noise}"
USER_LOG_MODE="${USER_LOG_MODE:-all}"
RAG_TOP_K="${RAG_TOP_K:-10}"
RAG_BACKEND="${RAG_BACKEND:-embedding}"
ENABLE_MCP="${ENABLE_MCP:-false}"
RUN_IN_BACKGROUND="${RUN_IN_BACKGROUND:-true}"
LOG_ROOT_BASE="${LOG_ROOT_BASE:-traj_logs/debug_dynamic_social}"
BATCH_EVAL="${BATCH_EVAL:-true}"               # true 时单个 mw eval 内用 MAX_CONCURRENCY 并行分发任务
PARALLEL="${PARALLEL:-false}"                  # BATCH_EVAL=false 时可用；true 表示多进程并行
# ============================

if [[ -z "$TASK" ]]; then
    cat >&2 <<'USAGE'
用法:
  bash scripts/run_claude_pref_routine_debug_task.sh <TASK_NAME>[,<TASK_NAME2>,...]

示例（单任务）:
  bash scripts/run_claude_pref_routine_debug_task.sh 'CommuteRoutingBadWeatherTask@developer'

示例（默认 smoke suite，4 个环境并行）:
  bash scripts/run_claude_pref_routine_debug_task.sh

示例（多任务，逗号分隔）:
  bash scripts/run_claude_pref_routine_debug_task.sh 'TaskA@user,TaskB@student,TaskC@developer'

示例（环境变量方式）:
  TASK='TaskA@user,TaskB@student' bash scripts/run_claude_pref_routine_debug_task.sh

示例（多任务并行 + 后台运行）:
  TASK='TaskA@user,TaskB@student' PARALLEL=true RUN_IN_BACKGROUND=true bash scripts/run_claude_pref_routine_debug_task.sh

选项:
  BATCH_EVAL=true        单个 mw eval 内并行分发任务（默认）
  PARALLEL=true           多任务并行执行（默认串行）
  RUN_IN_BACKGROUND=true  后台运行，日志写入文件
  MAX_CONCURRENCY=N       每个任务内部的并发数
USAGE
    exit 1
fi

AGENT_API_KEY="$CLAUDE_API_KEY"
if [[ -z "$AGENT_API_KEY" || "$AGENT_API_KEY" == "REPLACE_WITH_YOUR_API_KEY" ]]; then
    echo "请先在脚本顶部把 CLAUDE_API_KEY 改成你的真实 API Key。" >&2
    exit 1
fi

export USER_AGENT_API_KEY="${USER_AGENT_API_KEY:-$AGENT_API_KEY}"
export USER_AGENT_BASE_URL="${USER_AGENT_BASE_URL:-$LLM_BASE_URL}"
export USER_AGENT_MODEL="${USER_AGENT_MODEL:-$MODEL_NAME}"
export NO_PROXY="${NO_PROXY:-localhost,127.0.0.1,::1,10.130.138.46,10.130.138.47,10.130.138.48}"

# ---------- 工具函数 ----------

make_tag() {
    local s="$1"
    s="${s//\//_}"
    s="${s//@/_at_}"
    s="${s//./_}"
    s="${s//-/_}"
    s="${s// /_}"
    echo "$s"
}

build_cmd() {
    local task="$1"
    local log_root="$2"

    local user_args=()
    if [[ -n "$USER_FILTER" ]]; then
        user_args=(--user "$USER_FILTER")
    fi

    local mcp_args=()
    if [[ "$ENABLE_MCP" == "true" ]]; then
        mcp_args=(--enable_mcp)
    fi

    local aw_host_args=()
    if [[ -n "$AW_HOST" ]]; then
        aw_host_args=(--aw-host "$AW_HOST")
    fi

    local task_tag_args=()
    if [[ -n "$TASK_TAGS" ]]; then
        task_tag_args=(--task-tags "$TASK_TAGS")
    fi

    CMD=(
        mw eval
        --agent_type "$AGENT_TYPE"
        --task "$task"
        --enable-user-interaction
        --max_round "$MAX_ROUND"
        --model_name "$MODEL_NAME"
        --llm_base_url "$LLM_BASE_URL"
        --api_key "$AGENT_API_KEY"
        --step_wait_time "$STEP_WAIT_TIME"
        --env-image "$ENV_IMAGE"
        --max-concurrency "$MAX_CONCURRENCY"
        --log_file_root "$log_root"
        --user-log-source "$USER_LOG_SOURCE"
        --user-log-mode "$USER_LOG_MODE"
        --rag-top-k "$RAG_TOP_K"
        --rag-backend "$RAG_BACKEND"
    )
    CMD+=("${aw_host_args[@]}")
    CMD+=("${task_tag_args[@]}")
    CMD+=("${mcp_args[@]}")
    CMD+=("${user_args[@]}")
}

run_batch_tasks() {
    local model_tag
    model_tag="$(make_tag "$MODEL_NAME")"
    local user_tag="${USER_FILTER:-all_users}"
    local mcp_tag="no_mcp"
    [[ "$ENABLE_MCP" == "true" ]] && mcp_tag="with_mcp"

    local run_id
    run_id="$(date +%Y%m%d_%H%M%S)"
    local log_root="${LOG_ROOT_BASE}/${model_tag}_dynamic_social_smoke_${user_tag}_${USER_LOG_SOURCE}_${USER_LOG_MODE}_${RAG_BACKEND}_${mcp_tag}_${run_id}"
    mkdir -p "$log_root"
    local run_log="$log_root/debug.log"

    build_cmd "$TASK" "$log_root"

    echo "============================================"
    echo "[批量 smoke] 单个 mw eval 内并行运行 $TASK_COUNT 个任务"
    echo "  并发数: $MAX_CONCURRENCY"
    echo "  日志目录: $log_root"
    echo "  日志文件: $run_log"
    echo "============================================"

    if [[ "$RUN_IN_BACKGROUND" == "true" ]]; then
        nohup "${CMD[@]}" > "$run_log" 2>&1 &
        local pid=$!
        echo "[批量 smoke] 已在后台启动 PID=$pid"
        echo "  tail -f '$run_log'"
        echo "  可视化结果: mw logs view --log_dir '$log_root'"
        return 0
    fi

    set +e
    "${CMD[@]}" 2>&1 | tee "$run_log"
    local rc=${PIPESTATUS[0]}
    set -e
    echo "[批量 smoke] 完成 (exit=$rc)"
    echo "  可视化结果: mw logs view --log_dir '$log_root'"
    return $rc
}

run_single_task() {
    local task="$1"
    local idx="$2"
    local total="$3"

    # --- 校验 user 一致性 ---
    if [[ "$task" == *@* && -n "$USER_FILTER" ]]; then
        local task_user="${task##*@}"
        if [[ "$task_user" != "$USER_FILTER" ]]; then
            echo "[任务 $idx/$total] 跳过: TASK=$task 和 USER_FILTER=$USER_FILTER 不一致" >&2
            return 1
        fi
    fi

    # --- 构造日志目录 ---
    local model_tag
    model_tag="$(make_tag "$MODEL_NAME")"
    local task_log_tag
    task_log_tag="$(make_tag "$task")"
    local user_tag="${USER_FILTER:-all_users}"
    local mcp_tag="no_mcp"
    [[ "$ENABLE_MCP" == "true" ]] && mcp_tag="with_mcp"

    local run_id
    run_id="$(date +%Y%m%d_%H%M%S)"
    local log_root="${LOG_ROOT_BASE}/${model_tag}_${task_log_tag}_${user_tag}_${USER_LOG_SOURCE}_${USER_LOG_MODE}_${RAG_BACKEND}_${mcp_tag}_${run_id}"
    mkdir -p "$log_root"
    local run_log="$log_root/debug.log"

    build_cmd "$task" "$log_root"

    echo "============================================"
    echo "[任务 $idx/$total] $task"
    echo "  日志目录: $log_root"
    echo "  日志文件: $run_log"
    echo "============================================"

    if [[ "$RUN_IN_BACKGROUND" == "true" ]]; then
        nohup "${CMD[@]}" > "$run_log" 2>&1 &
        local pid=$!
        echo "[任务 $idx/$total] 已在后台启动 PID=$pid"
        echo "$pid" >> "$PIDS_FILE"
    else
        set +e
        "${CMD[@]}" 2>&1 | tee "$run_log"
        local rc=${PIPESTATUS[0]}
        set -e
        echo "[任务 $idx/$total] 完成 (exit=$rc)"
        echo "  可视化结果: mw logs view --log_dir '$log_root'"
        return $rc
    fi
}

# ---------- 解析任务列表 ----------

IFS=',' read -ra TASKS <<< "$TASK"
TASK_COUNT=${#TASKS[@]}

echo "========================================"
echo "批量评估启动"
echo "  任务数量: $TASK_COUNT"
echo "  任务列表: ${TASKS[*]}"
echo "  主模型: $MODEL_NAME"
echo "  Agent 类型: $AGENT_TYPE"
echo "  Base URL: $LLM_BASE_URL"
echo "  最大轮数: $MAX_ROUND"
echo "  单任务并发: $MAX_CONCURRENCY"
echo "  批量并发模式: $BATCH_EVAL"
echo "  多任务并行: $PARALLEL"
echo "  后台运行: $RUN_IN_BACKGROUND"
echo "  USER_AGENT_MODEL: $USER_AGENT_MODEL"
if [[ -n "$TASK_TAGS" ]]; then
    echo "  任务标签过滤: $TASK_TAGS"
fi
if [[ -n "$AW_HOST" ]]; then
    echo "  后端地址: $AW_HOST"
else
    echo "  后端地址: 自动发现 knowu_bench_env_* 容器（镜像过滤: $ENV_IMAGE）"
fi
echo "========================================"

# ---------- 执行 ----------

PIDS_FILE="$(mktemp)"
trap 'rm -f "$PIDS_FILE"' EXIT

FAILED=0
IDX=0

if [[ "$BATCH_EVAL" == "true" ]]; then
    run_batch_tasks
    exit $?
elif [[ "$PARALLEL" == "true" ]]; then
    # --- 并行模式：所有任务同时启动 ---
    # 并行模式强制后台写日志（前台 tee 多进程会混乱）
    RUN_IN_BACKGROUND=true
    for task in "${TASKS[@]}"; do
        task="$(echo "$task" | xargs)"  # trim 空格
        [[ -z "$task" ]] && continue
        ((IDX+=1))
        run_single_task "$task" "$IDX" "$TASK_COUNT" || true
    done

    # 等待所有后台进程
    echo ""
    echo "等待所有后台任务完成..."
    while IFS= read -r pid; do
        if wait "$pid" 2>/dev/null; then
            echo "  PID $pid 完成"
        else
            echo "  PID $pid 失败或已退出"
            ((FAILED+=1))
        fi
    done < "$PIDS_FILE"
else
    # --- 串行模式：逐个执行 ---
    for task in "${TASKS[@]}"; do
        task="$(echo "$task" | xargs)"
        [[ -z "$task" ]] && continue
        ((IDX+=1))
        if ! run_single_task "$task" "$IDX" "$TASK_COUNT"; then
            ((FAILED+=1))
        fi
    done
fi

# ---------- 汇总 ----------

echo ""
echo "========================================"
echo "全部完成: $TASK_COUNT 个任务, $FAILED 个失败"
if [[ "$RUN_IN_BACKGROUND" == "true" && "$PARALLEL" != "true" ]]; then
    echo "后台 PID 列表:"
    cat "$PIDS_FILE" 2>/dev/null | while read -r p; do echo "  $p"; done
fi
echo "========================================"

exit "$FAILED"
