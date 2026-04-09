sudo mw env run --count 5 --launch-interval 20


# make sure your model name has "claude" in it, the general_e2e agent use partial match to recognize Claudes. As claude's grounding requires image resize.
sudo mw eval \
    --agent_type general_e2e \
    --task ALL \
    --max_round 50 \
    --step_wait_time 3 \
    --model_name claude-sonnet-4-5-20250929 \
    --llm_base_url [gemini_openai_compatible_base_url] \
    --enable_mcp
