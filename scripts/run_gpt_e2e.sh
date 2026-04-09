sudo mw env run --count 5 --launch-interval 20

sudo mw eval \
    --agent_type general_e2e \
    --task ALL \
    --max_round 50 \
    --step_wait_time 3 \
    --model_name gpt-5.4 \
    --llm_base_url https://api.openai.com/v1 \
    --api_key $OPENAI_API_KEY \
    --enable_mcp
