export DASHSCOPE_API_KEY="sk-d038dfbcec894c7a801643f60ebc7477"  # 建议先设置环境变量
export NO_PROXY="localhost,127.0.0.1,::1,10.130.138.46,10.130.138.47,10.130.138.48"

LOG_ROOT="traj_logs/mai_ui_8b_rag_logs"
mkdir -p "$LOG_ROOT"
RUN_LOG="$LOG_ROOT/nohup_$(date +%Y%m%d_%H%M%S).log"

nohup mw eval \
    --agent_type mai_ui_agent \
    --task ALL \
    --task-tags routine,preference \
    --user user \
    --max_round 50 \
    --model_name mai-ui-8b \
    --enable-user-interaction \
    --llm_base_url http://10.130.138.48:8050/v1 \
    --api_key $DASHSCOPE_API_KEY \
    --step_wait_time 10 \
    --max-concurrency 4 \
    --log_file_root "$LOG_ROOT" \
    --aw-host "http://127.0.0.1:6800,http://127.0.0.1:6801,http://127.0.0.1:6802,http://127.0.0.1:6803" \
    --user-log-mode rag \
    --rag-top-k 10 > "$RUN_LOG" 2>&1 &

echo "任务已在后台启动 PID=$!"
echo "日志文件: $RUN_LOG"
