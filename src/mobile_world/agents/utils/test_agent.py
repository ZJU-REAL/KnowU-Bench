"""
Unified testing script for all agent implementations.

Usage:
    python -m mobile_world.agents.utils.test_agent \
        --agent_type general_e2e \
        --model_name gpt-4o-mini \
        --llm_base_url https://api.openai.com/v1 \
        --api_key YOUR_API_KEY \
        --screenshot_path ./assets/screenshot_pil.png \
        --instruction "Click the search button"
"""

import argparse
import os
import sys
from pathlib import Path

from loguru import logger
from PIL import Image

from mobile_world.runtime.utils.trajectory_logger import (
    draw_clicks_on_image,
    extract_click_coordinates,
)


def get_agent_class(agent_type: str):
    """Import and return the appropriate agent class based on agent_type."""
    if agent_type == "general_e2e":
        from mobile_world.agents.implementations.general_e2e_agent import GeneralE2EAgentMCP
        return GeneralE2EAgentMCP
    elif agent_type == "planner_executor":
        from mobile_world.agents.implementations.planner_executor import PlannerExecutorAgentMCP
        return PlannerExecutorAgentMCP
    elif agent_type == "qwen3vl":
        from mobile_world.agents.implementations.qwen3vl import Qwen3VLAgentMCP
        return Qwen3VLAgentMCP
    elif agent_type == "mai_ui_agent":
        from mobile_world.agents.implementations.mai_ui_agent import MAIUINaivigationAgent
        return MAIUINaivigationAgent
    else:
        logger.error(f"Unknown agent type: {agent_type}")
        logger.info("Available agent types: general_e2e, planner_executor, qwen3vl, mai_ui_agent")
        sys.exit(1)


def test_agent(
    agent_type: str,
    model_name: str,
    llm_base_url: str,
    api_key: str,
    screenshot_path: str,
    instruction: str,
    output_image_path: str = None,
    runtime_conf: dict = None,
    **kwargs,
):
    """
    Test an agent implementation with a given screenshot and instruction.

    Args:
        agent_type: Type of agent to test (e.g., 'general_e2e', 'planner_executor')
        model_name: Name of the model to use
        llm_base_url: Base URL for the LLM API
        api_key: API key for authentication
        screenshot_path: Path to the test screenshot
        instruction: Instruction for the agent
        output_image_path: Path to save the visualization (optional)
        runtime_conf: Runtime configuration for the agent (optional)
        **kwargs: Additional arguments for agent initialization
    """
    # Validate screenshot path
    if not os.path.exists(screenshot_path):
        logger.error(f"Test image not found at {screenshot_path}")
        logger.info("Please provide a valid screenshot path for testing.")
        sys.exit(1)

    # Load test image
    test_image = Image.open(screenshot_path)
    logger.info(f"Loaded test image with size: {test_image.size}")

    # Set default runtime configuration
    if runtime_conf is None:
        runtime_conf = {
            "history_n_images": 3,
            "temperature": 0.0,
            "max_tokens": 2048,
        }

    # Get agent class
    AgentClass = get_agent_class(agent_type)
    logger.info(f"Using agent class: {AgentClass.__name__}")

    # Create agent instance
    try:
        if agent_type in ["general_e2e"]:
            # Extract parameters that we'll pass explicitly to avoid duplicates
            tools = kwargs.pop("tools", [])
            scale_factor = kwargs.pop("scale_factor", 1000)
            agent = AgentClass(
                model_name=model_name,
                llm_base_url=llm_base_url,
                api_key=api_key,
                observation_type="screenshot",
                runtime_conf=runtime_conf,
                tools=tools,
                scale_factor=scale_factor,
                **kwargs,
            )
        elif agent_type in ["planner_executor"]:
            # Planner-executor needs additional executor parameters
            if "executor_agent_class" not in kwargs:
                logger.warning(
                    "Planner-executor requires 'executor_agent_class'. "
                    "Add --executor_agent_class, --executor_model_name, --executor_llm_base_url"
                )
            # Extract tools to avoid duplicate
            tools = kwargs.pop("tools", [])
            agent = AgentClass(
                model_name=model_name,
                llm_base_url=llm_base_url,
                api_key=api_key,
                observation_type="screenshot",
                runtime_conf=runtime_conf,
                tools=tools,
                **kwargs,
            )
        elif agent_type in ["qwen3vl", "mai_ui_agent"]:
            # Other MCP agents
            agent = AgentClass(
                model_name=model_name,
                llm_base_url=llm_base_url,
                api_key=api_key,
                observation_type="screenshot",
                runtime_conf=runtime_conf,
                tools=kwargs.get("tools", []),
                **kwargs,
            )
        else:
            agent = AgentClass(
                model_name=model_name,
                llm_base_url=llm_base_url,
                api_key=api_key,
                observation_type="screenshot",
                runtime_conf=runtime_conf,
                tools=kwargs.get("tools", []),
                **kwargs,
            )
    except Exception as e:
        logger.error(f"Failed to create agent instance: {e}")
        sys.exit(1)

    # Initialize agent with instruction
    logger.info(f"Initializing agent with instruction: '{instruction}'")
    agent.initialize(instruction)

    # Build observation
    obs = {
        "screenshot": test_image,
        "tool_call": None,
        "ask_user_response": None,
    }

    # Call predict
    logger.info(f"Processing instruction: '{instruction}'")
    try:
        raw_response, action = agent.predict(obs)
    except Exception as e:
        logger.error(f"Prediction failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    # Print results
    logger.info("\n" + "=" * 60)
    logger.info("=== Raw Model Response ===")
    logger.info(raw_response)
    logger.info("\n" + "=" * 60)
    logger.info("=== Parsed Action ===")
    logger.info(action)
    logger.info("=" * 60 + "\n")

    # Visualize click actions if any
    action_dict = action.model_dump() if hasattr(action, "model_dump") else action.dict()
    
    # Try to extract coordinates based on action type
    action_type = action_dict.get("action_type", "")
    
    if action_type in ["click", "long_press", "double_tap"]:
        click_coordinates = extract_click_coordinates(action_dict)
        if click_coordinates and click_coordinates[0] is not None and click_coordinates[1] is not None:
            # Coordinates are already in absolute values from the agent
            logger.info(f"Click coordinates: {click_coordinates}")
            
            if output_image_path is None:
                output_image_path = f"./screenshot_with_{agent_type}_clicks.png"
            
            draw_clicks_on_image(screenshot_path, output_image_path, click_coordinates)
            logger.info(f"Click visualization saved to: {output_image_path}")
        else:
            logger.info(f"No valid click coordinates found.")
    elif action_type == "drag":
        # For drag actions, visualize both start and end points
        start_x = action_dict.get("start_x")
        start_y = action_dict.get("start_y")
        end_x = action_dict.get("end_x")
        end_y = action_dict.get("end_y")
        
        if all([start_x, start_y, end_x, end_y]):
            # Coordinates are already in absolute values from the agent
            logger.info(f"Drag action: from ({start_x}, {start_y}) to ({end_x}, {end_y})")
            
            if output_image_path is None:
                output_image_path = f"./screenshot_with_{agent_type}_drag.png"
            
            # Draw drag visualization using trajectory_logger style
            from PIL import ImageDraw
            from mobile_world.runtime.utils.trajectory_logger import save_screenshot
            
            image = Image.open(screenshot_path)
            draw = ImageDraw.Draw(image)
            
            radius = 20
            # Draw start point in red
            draw.ellipse(
                (start_x - radius, start_y - radius, 
                 start_x + radius, start_y + radius),
                fill="red",
                outline="red",
            )
            # Draw end point in blue
            draw.ellipse(
                (end_x - radius, end_y - radius, 
                 end_x + radius, end_y + radius),
                fill="blue",
                outline="blue",
            )
            # Draw line connecting them
            draw.line([(start_x, start_y), (end_x, end_y)], 
                     fill="green", width=5)
            
            save_screenshot(image, output_image_path)
        else:
            logger.info(f"No valid drag coordinates found.")
    else:
        logger.info(f"Action type '{action_type}' does not require visualization.")

    logger.info("\n✅ Test completed successfully!")
    return raw_response, action


def main():
    """Main entry point for the test script."""
    parser = argparse.ArgumentParser(
        description="Unified testing script for agent implementations",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Test General E2E Agent
  python -m mobile_world.agents.utils.test_agent \\
      --agent_type general_e2e \\
      --model_name gpt-4o-mini \\
      --llm_base_url https://api.openai.com/v1 \\
      --api_key YOUR_API_KEY \\
      --screenshot_path ./assets/screenshot.png \\
      --instruction "Click the search button"

  # Test Planner-Executor Agent
  python -m mobile_world.agents.utils.test_agent \\
      --agent_type planner_executor \\
      --model_name gpt-4o \\
      --llm_base_url https://api.openai.com/v1 \\
      --api_key YOUR_API_KEY \\
      --screenshot_path ./assets/screenshot.png \\
      --instruction "Open the settings app" \\
      --executor_agent_class qwen3vl \\
      --executor_model_name autoglm-phone-9b \\
      --executor_llm_base_url http://localhost:8000/v1

  # Test Qwen3VL Agent
  python -m mobile_world.agents.utils.test_agent \\
      --agent_type qwen3vl \\
      --model_name qwen-vl-plus \\
      --llm_base_url http://localhost:8000/v1 \\
      --api_key YOUR_API_KEY \\
      --screenshot_path ./assets/screenshot.png \\
      --instruction "Click the search icon"
        """,
    )

    # Required arguments
    parser.add_argument(
        "--agent_type",
        type=str,
        required=True,
        choices=["general_e2e", "planner_executor", "qwen3vl", "mai_ui_agent"],
        help="Type of agent to test",
    )
    parser.add_argument(
        "--model_name",
        type=str,
        required=True,
        help="Name of the model to use",
    )
    parser.add_argument(
        "--llm_base_url",
        type=str,
        required=True,
        help="Base URL for the LLM API",
    )
    parser.add_argument(
        "--screenshot_path",
        type=str,
        required=True,
        help="Path to the test screenshot",
    )
    parser.add_argument(
        "--instruction",
        type=str,
        required=True,
        help="Instruction for the agent to execute",
    )

    # Optional arguments
    parser.add_argument(
        "--api_key",
        type=str,
        default="empty",
        help="API key for authentication (default: 'empty')",
    )
    parser.add_argument(
        "--output_image_path",
        type=str,
        default=None,
        help="Path to save the visualization (default: auto-generated)",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.0,
        help="Temperature for model sampling (default: 0.0)",
    )
    parser.add_argument(
        "--max_tokens",
        type=int,
        default=2048,
        help="Maximum tokens for model response (default: 2048)",
    )
    parser.add_argument(
        "--history_n_images",
        type=int,
        default=3,
        help="Number of historical images to keep (default: 3)",
    )
    parser.add_argument(
        "--scale_factor",
        type=int,
        default=1000,
        help="Scale factor for coordinate conversion (default: 1000)",
    )

    # Executor-specific arguments (for planner_executor)
    parser.add_argument(
        "--executor_agent_class",
        type=str,
        default=None,
        help="Executor agent class name (for planner_executor)",
    )
    parser.add_argument(
        "--executor_model_name",
        type=str,
        default=None,
        help="Executor model name (for planner_executor)",
    )
    parser.add_argument(
        "--executor_llm_base_url",
        type=str,
        default=None,
        help="Executor LLM base URL (for planner_executor)",
    )

    args = parser.parse_args()

    # Build runtime configuration
    runtime_conf = {
        "history_n_images": args.history_n_images,
        "temperature": args.temperature,
        "max_tokens": args.max_tokens,
    }

    # Build kwargs for agent initialization
    kwargs = {}
    if args.executor_agent_class:
        kwargs["executor_agent_class"] = args.executor_agent_class
    if args.executor_model_name:
        kwargs["executor_model_name"] = args.executor_model_name
    if args.executor_llm_base_url:
        kwargs["executor_llm_base_url"] = args.executor_llm_base_url
    if args.scale_factor:
        kwargs["scale_factor"] = args.scale_factor

    # Run test
    test_agent(
        agent_type=args.agent_type,
        model_name=args.model_name,
        llm_base_url=args.llm_base_url,
        api_key=args.api_key,
        screenshot_path=args.screenshot_path,
        instruction=args.instruction,
        output_image_path=args.output_image_path,
        runtime_conf=runtime_conf,
        **kwargs,
    )


if __name__ == "__main__":
    main()

