"""General task: search for today's weather in Chrome."""

import re

import requests
from loguru import logger

from knowu_bench.runtime.controller import AndroidController
from knowu_bench.runtime.utils.helpers import execute_adb
from knowu_bench.runtime.utils.proxy_config import android_proxy_setting_command
from knowu_bench.runtime.utils.routine_time import format_adb_datetime, resolve_routine_datetime
from knowu_bench.tasks.base import BaseTask


class MorningWeatherCheckGeneralTask(BaseTask):
    """Search for weather information using Chrome."""

    task_tags = {"general", "hard"}
    snapshot_tag = "init_state"
    app_names = {"Chrome"}

    CHROME_PKG = "com.android.chrome"
    WEATHER_KEYWORDS = [
        "weather", "forecast", "temperature", "sunny", "cloudy",
        "rain", "snow", "wind", "humid", "天气", "气温", "°C", "°F",
    ]
    CITY = "Hangzhou"
    CITY_COORDS = (30.2741, 120.1551)
    TEMP_TOLERANCE = 3.0
    DEFAULT_SCENE_TIME = "08:10:00"

    goal = (
        "请用 Chrome 浏览器搜索今天杭州的天气情况，"
        "然后把天气信息（包括温度）告诉我。"
    )

    def __init__(self, params=None):
        super().__init__(params)
        self.simulation_dt = resolve_routine_datetime(
            default_time=self.DEFAULT_SCENE_TIME,
            task_name=self.name,
        )

    def initialize_task_hook(self, controller: AndroidController) -> bool:
        execute_adb("shell settings put global auto_time 0")
        execute_adb("shell settings put system time_12_24 24")
        execute_adb(f"shell su 0 date {format_adb_datetime(self.simulation_dt)}")
        cmds = [
            android_proxy_setting_command(),
            f"am force-stop {self.CHROME_PKG}",
            f"pm clear {self.CHROME_PKG}",
            f"am start -n {self.CHROME_PKG}/com.google.android.apps.chrome.Main",
        ]
        for cmd in cmds:
            execute_adb(f"shell {cmd}")
        return True

    def _answer_contains_weather(self, answer: str) -> bool:
        return any(k.lower() in answer.lower() for k in self.WEATHER_KEYWORDS)

    def _extract_numbers(self, text: str) -> list[float]:
        return [float(x) for x in re.findall(r"-?\d+\.?\d*", text)]

    def _target_date_str(self) -> str:
        return self.simulation_dt.strftime("%Y-%m-%d")

    def _fetch_weather_temp(self) -> float | None:
        lat, lon = self.CITY_COORDS
        target_date = self._target_date_str()
        try:
            resp = requests.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "daily": "temperature_2m_max",
                    "timezone": "Asia/Shanghai",
                    "start_date": target_date,
                    "end_date": target_date,
                },
                timeout=8,
            )
            resp.raise_for_status()
            daily = resp.json().get("daily", {})
            temps = daily.get("temperature_2m_max", [])
            dates = daily.get("time", [])
            for date_str, temp in zip(dates, temps):
                if date_str == target_date:
                    return float(temp)
            if temps:
                return float(temps[0])
        except Exception as e:
            logger.warning(f"Weather API call failed: {e}")
        return None

    def is_successful(self, controller: AndroidController) -> tuple[float, str]:
        self._check_is_initialized()
        answer = (controller.interaction_cache or "").strip()
        if not answer:
            return 0.0, "Failure: No weather answer provided."

        if not self._answer_contains_weather(answer):
            return 0.0, f"Failure: Answer lacks weather content: '{answer[:80]}'"

        api_temp = self._fetch_weather_temp()
        if api_temp is None:
            return 1.0, f"Success: Weather keywords found (API unavailable): '{answer[:80]}'"

        numbers = self._extract_numbers(answer)
        if not numbers:
            return 0.0, f"Failure: Weather keywords found but no temperature number: '{answer[:80]}'"

        if any(abs(n - api_temp) <= self.TEMP_TOLERANCE for n in numbers):
            return 1.0, f"Success: Temperature matches API ({api_temp}±{self.TEMP_TOLERANCE}°C)."
        return 0.0, f"Failure: Temperature mismatch: extracted {numbers}, API={api_temp}°C."

    def tear_down(self, controller: AndroidController) -> bool:
        super().tear_down(controller)
        execute_adb("shell settings put global http_proxy :0")
        execute_adb("shell settings put global auto_time 1")
        execute_adb("shell settings delete system time_12_24")
        return True
