import json
import os
from datetime import datetime

from loguru import logger
from PIL import Image, ImageDraw

from mobile_world.runtime.utils.models import Observation


def save_screenshot(screenshot, path) -> None:
    screenshot.save(path)
    logger.info(f"Screenshot saved in {path}")


def extract_click_coordinates(action):
    x = action.get("x")
    y = action.get("y")
    action_corr = (x, y)
    return action_corr


def extract_drag_coordinates(action):
    start_x = action.get("start_x")
    start_y = action.get("start_y")
    end_x = action.get("end_x")
    end_y = action.get("end_y")
    return (start_x, start_y, end_x, end_y)


# Function to draw points on an image
def draw_clicks_on_image(image_path, output_path, click_coords):
    image = Image.open(image_path)
    draw = ImageDraw.Draw(image)

    # Draw each click coordinate as a red circle
    (x, y) = click_coords
    radius = 20
    if x and y:  # if get the coordinate, draw a circle
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill="red", outline="red")

    # Save the modified image
    save_screenshot(image, output_path)


# Function to draw a drag line on an image
def draw_drag_on_image(image_path, output_path, drag_coords):
    image = Image.open(image_path)
    draw = ImageDraw.Draw(image)

    (start_x, start_y, end_x, end_y) = drag_coords
    if start_x and start_y and end_x and end_y:
        # Draw a line from start to end
        draw.line((start_x, start_y, end_x, end_y), fill="blue", width=5)
        # Draw circles at start (green) and end (red) points
        radius = 15
        draw.ellipse(
            (start_x - radius, start_y - radius, start_x + radius, start_y + radius),
            fill="green",
            outline="green",
        )
        draw.ellipse(
            (end_x - radius, end_y - radius, end_x + radius, end_y + radius),
            fill="red",
            outline="red",
        )

    # Save the modified image
    save_screenshot(image, output_path)


LOG_FILE_NAME = "traj.json"
SCORE_FILE_NAME = "result.txt"


class TrajLogger:
    def __init__(self, log_file_root: str, task_name: str):
        self.log_file_dir = os.path.join(log_file_root, task_name)
        self.log_file_name = LOG_FILE_NAME
        self.score_file_name = SCORE_FILE_NAME
        self.screenshots_dir = "screenshots"
        self.marked_screenshots_dir = "marked_screenshots"
        self.tools = None

        if os.path.exists(self.log_file_dir) and os.path.exists(
            os.path.join(self.log_file_dir, self.screenshots_dir)
        ):
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_dir = f"{self.log_file_dir}_backup_{timestamp}"

            # Rename existing folder to backup
            os.rename(self.log_file_dir, backup_dir)
            logger.info(f"Existing folder renamed to: {backup_dir}")

        os.makedirs(self.log_file_dir, exist_ok=True)
        os.makedirs(os.path.join(self.log_file_dir, self.screenshots_dir), exist_ok=True)
        os.makedirs(os.path.join(self.log_file_dir, self.marked_screenshots_dir), exist_ok=True)
        with open(os.path.join(self.log_file_dir, self.log_file_name), "w") as f:
            json.dump({}, f)

    def log_traj(
        self,
        task_name: str,
        task_goal: str,
        step: int,
        prediction: str,
        action: dict,
        obs: Observation,
        token_usage: dict[str, int] = None,
    ) -> None:
        task_id = "0"

        with open(os.path.join(self.log_file_dir, self.log_file_name)) as f:
            log_data = json.load(f)

        if task_id not in log_data:
            log_data[task_id] = {"tools": self.tools, "traj": []}

        log_data[task_id]["traj"].append(
            {
                "task_goal": task_goal,
                "step": step,
                "prediction": prediction,
                "action": action,
                "ask_user_response": obs.ask_user_response,
                "tool_call": obs.tool_call,
            }
        )
        log_data[task_id]["token_usage"] = token_usage

        with open(os.path.join(self.log_file_dir, self.log_file_name), "w") as f:
            json.dump(log_data, f, ensure_ascii=False, indent=4)

        original_screenshot_path = os.path.join(
            self.log_file_dir, self.screenshots_dir, f"{task_name}-{task_id}-{step}.png"
        )
        save_screenshot(obs.screenshot, original_screenshot_path)

        action_type = action.get("action_type")
        if action_type in ["click", "double_tap", "long_press"]:
            click_coordinates = extract_click_coordinates(action)
            marked_screenshot_path = os.path.join(
                self.log_file_dir,
                self.marked_screenshots_dir,
                f"marked-{task_name}-{task_id}-{step}.png",
            )
            draw_clicks_on_image(
                original_screenshot_path, marked_screenshot_path, click_coordinates
            )
        elif action_type == "drag":
            drag_coordinates = extract_drag_coordinates(action)
            marked_screenshot_path = os.path.join(
                self.log_file_dir,
                self.marked_screenshots_dir,
                f"marked-{task_name}-{task_id}-{step}.png",
            )
            draw_drag_on_image(original_screenshot_path, marked_screenshot_path, drag_coordinates)

    def log_tools(self, tools: list[dict]):
        self.tools = tools

    def log_score(self, score: float, reason: str = "Unknown reason"):
        with open(os.path.join(self.log_file_dir, self.score_file_name), "w") as f:
            f.write(f"score: {score}\nreason: {reason}")

        # reset tools after logging score
        self.tools = None

    def log_token_usage(self, token_usage: dict[str, int]) -> None:
        """Log token usage to traj.json."""
        with open(os.path.join(self.log_file_dir, self.log_file_name)) as f:
            log_data = json.load(f)

        log_data["token_usage"] = token_usage

        with open(os.path.join(self.log_file_dir, self.log_file_name), "w") as f:
            json.dump(log_data, f, ensure_ascii=False, indent=4)

    def reset_traj(self):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Backup screenshots dir
        screenshots_path = os.path.join(self.log_file_dir, self.screenshots_dir)
        if os.path.exists(screenshots_path):
            os.rename(screenshots_path, f"{screenshots_path}_backup_{timestamp}")

        # Backup marked_screenshots dir
        marked_path = os.path.join(self.log_file_dir, self.marked_screenshots_dir)
        if os.path.exists(marked_path):
            os.rename(marked_path, f"{marked_path}_backup_{timestamp}")

        # Backup traj.json
        traj_path = os.path.join(self.log_file_dir, self.log_file_name)
        if os.path.exists(traj_path):
            backup_traj_path = os.path.join(self.log_file_dir, f"traj_backup_{timestamp}.json")
            os.rename(traj_path, backup_traj_path)

        # Recreate directories and empty traj.json
        os.makedirs(screenshots_path, exist_ok=True)
        os.makedirs(marked_path, exist_ok=True)
        with open(traj_path, "w") as f:
            json.dump({}, f)

        self.tools = None
        logger.info(f"Trajectory reset with backup timestamp: {timestamp}")
