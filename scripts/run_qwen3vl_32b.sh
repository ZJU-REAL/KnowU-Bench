export DASHSCOPE_API_KEY="sk-d038dfbcec894c7a801643f60ebc7477"  # 建议先设置环境变量

LOG_ROOT="traj_logs/qwen3_vl_32b_logs"
mkdir -p "$LOG_ROOT"
RUN_LOG="$LOG_ROOT/nohup_$(date +%Y%m%d_%H%M%S).log"

nohup uv run mw eval \
    --agent_type qwen3vl \
    --task MattermostOnCallTask@user,MorningPaperReadingTask@user,PreMeetingPrepTask@user,WeekendSleeperTask@user,BatterySaverRoutineTask@user,DeepWorkRoutineTask@user \
    --task-tags routine \
    --max_round 50 \
    --model_name qwen3-vl-32b \
    --enable-user-interaction \
    --llm_base_url http://10.130.138.46:8050/v1 \
    --api_key $DASHSCOPE_API_KEY \
    --step_wait_time 10 \
    --max-concurrency 2 \
    --log_file_root "$LOG_ROOT" \
    --aw-host "http://127.0.0.1:6800" > "$RUN_LOG" 2>&1 &

echo "任务已在后台启动 PID=$!"
echo "日志文件: $RUN_LOG"