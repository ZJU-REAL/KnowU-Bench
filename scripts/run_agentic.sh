sudo mw env run --count 5 --launch-interval 20

sudo mw eval \
    --agent_type planner_executor \
    --task ALL \
    --max_round 50 \
    --step_wait_time 3 \
    --model_name [planner_model_name] \
    --llm_base_url [planner_model_openai_base_url] \
    --executor_agent_class uiins \
    --executor_llm_base_url [ui_ins_model_openai_base_url] \
    --executor_model_name [ui_ins_model_name] \
    --enable_mcp
