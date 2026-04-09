"""MCP helper functions for stock and ESG rating operations."""

import json
import re
from typing import Any

from loguru import logger

from mobile_world.runtime.mcp_server import init_mcp_clients


def extract_stocks_from_result(
    result: list[dict[str, Any]] | dict[str, Any],
) -> list[dict[str, Any]]:
    """Extract stock data from MCP tool result."""
    return _extract_list_from_result(result, "Failed to extract stock data from MCP result")


def parse_esg_result(result: list[dict[str, Any]] | dict[str, Any]) -> dict[str, Any]:
    """Parse ESG rating result from MCP tool result."""
    if isinstance(result, dict):
        result = [result]

    for item in result:
        if not isinstance(item, dict):
            continue
        if "esg_rate" in item or "security_code" in item:
            return item
        text_content = _get_text_from_item(item)
        if text_content:
            try:
                data = json.loads(text_content)
                if isinstance(data, str):
                    data = json.loads(data)
                if isinstance(data, dict):
                    return data
                if isinstance(data, list) and data:
                    return data[0] if isinstance(data[0], dict) else {}
            except Exception:
                continue
    return {}


def sort_stocks_by_code(stock_list: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sort stocks by security code."""

    def sort_key(stock):
        code = stock.get("security_code", "")
        try:
            if isinstance(code, str) and code.isdigit():
                return int(code)
            return str(code)
        except:
            return str(code)

    return sorted(stock_list, key=sort_key)


def extract_esg_rate(result: list[dict[str, Any]] | dict[str, Any]) -> str:
    """Extract ESG rating from tool result."""
    try:
        text = _get_text_from_item(result)
        data = json.loads(text)
        if isinstance(data, str):
            data = json.loads(data)
        if isinstance(data, dict):
            esg_rate = data.get("esg_rate")
            if esg_rate:
                return str(esg_rate)
        elif isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
            esg_rate = data[0].get("esg_rate")
            if esg_rate:
                return str(esg_rate)
        raise ValueError("ESG rate not found in result")
    except Exception as e:
        raise RuntimeError("Failed to extract ESG rating from tool result") from e


async def get_stocks_esg_ratings(
    filter_type: int = 1,
    filter_value: float = 15.0,
) -> str:
    """
    筛选股票并获取第一只股票的 ESG 评级

    Args:
        filter_type: 筛选类型 (1: 大于, 2: 大于等于, 3: 小于, 4: 小于等于, 5: 等于)
        filter_value: 筛选值 (默认 15.0，表示 ROE 阈值)

    Returns:
        str: 格式为 "code:rate" 的字符串，例如 "600000:BB"

    Raises:
        AssertionError: 当 MCP 调用失败或数据解析失败时抛出异常
    """
    client = init_mcp_clients()
    roe_tool_name = "stockstar_stk_eval_filter_by_roe_3y"
    esg_tool_name = "stockstar_miotech_esg_rating"

    result = await client.call_tool(
        name=roe_tool_name,
        arguments={"filter_value": filter_value, "filter_type": filter_type},
    )

    assert result and isinstance(result, list) and len(result) > 0, (
        "MCP call failed or returned empty result"
    )

    stock_list = extract_stocks_from_result(result)
    assert stock_list, "Failed to extract stock list from MCP result"

    stock_list = sort_stocks_by_code(stock_list)
    first_stock = stock_list[0]
    security_code = first_stock.get("security_code")
    assert security_code, "First stock missing security_code"

    esg_result = await client.call_tool(
        name=esg_tool_name,
        arguments={"security_code": security_code},
    )

    assert esg_result and isinstance(esg_result, list) and len(esg_result) > 0, (
        "ESG rating MCP call failed"
    )

    esg_data = parse_esg_result(esg_result)
    assert esg_data, "Failed to parse ESG rating result"

    esg_rate = esg_data.get("esg_rate", "N/A")
    return f"{security_code}:{esg_rate}"


async def get_high_dividend_stocks(
    div_filter_type: int = 1,
    div_filter_value: float = 10.0,
) -> list[dict[str, Any]]:
    """
    筛选股息率大于指定值的股票名单

    Args:
        div_filter_type: 股息率筛选类型 (1: 大于, 2: 大于等于, 3: 小于, 4: 小于等于, 5: 等于)
        div_filter_value: 股息率筛选值 (默认 10.0，表示 10%)

    Returns:
        list: 符合条件的股票列表，每个元素包含股票信息：
        [
            {
                "security_code": "600000",
                "security_name": "浦发银行",
                "security_id": "600000.SH",
                "security_market": "SH",
                "div_rate": 10.5
            },
            ...
        ]

    Raises:
        Exception: 当 MCP 调用失败或数据解析失败时抛出异常
    """
    client = init_mcp_clients()
    div_tool_name = "stockstar_stk_eval_filter_by_div_rate"

    div_result = await client.call_tool(
        name=div_tool_name,
        arguments={"filter_type": div_filter_type, "filter_value": div_filter_value},
    )

    assert div_result and isinstance(div_result, list) and len(div_result) > 0, (
        "MCP call failed or returned empty result"
    )

    stock_list = extract_stocks_from_result(div_result)
    assert stock_list, "Failed to extract stock list from MCP result"

    stock_list = sort_stocks_by_code(stock_list)

    result_list = []
    for stock in stock_list:
        stock_info = {
            "security_code": stock.get("security_code", ""),
            "security_name": stock.get("security_name", ""),
            "security_id": stock.get("security_id", ""),
            "security_market": stock.get("security_market", ""),
            "div_rate": stock.get("value", ""),
        }
        result_list.append(stock_info)

    return result_list


async def get_stocks_by_div_rate_and_esg(
    div_filter_type: int = 1,
    div_filter_value: float = 4.0,
    min_esg_rating: str = "BBB",
    max_stocks: int = 5,
) -> list[dict[str, Any]]:
    """
    筛选股息率大于指定值的股票，并从中找出 ESG 评级在指定级别及以上的股票

    Args:
        div_filter_type: 股息率筛选类型 (1: 大于, 2: 大于等于, 3: 小于, 4: 小于等于, 5: 等于)
        div_filter_value: 股息率筛选值 (默认 4.0，表示 4%)
        min_esg_rating: 最低 ESG 评级 (默认 "BBB"，表示 BBB 及以上)
        max_stocks: 最大返回股票数量 (默认 5)

    Returns:
        list: 符合条件的股票列表，每个元素包含股票信息：
        [
            {
                "security_code": "600000",
                "security_name": "浦发银行",
                "div_rate": 4.5,
                "esg_rate": "BBB"
            },
            ...
        ]
    """
    client = init_mcp_clients()
    div_tool_name = "stockstar_stk_eval_filter_by_div_rate"
    esg_tool_name = "stockstar_miotech_esg_rating"

    esg_ratings_order = [
        "AAA",
        "AA+",
        "AA",
        "AA-",
        "A+",
        "A",
        "A-",
        "BBB+",
        "BBB",
        "BBB-",
        "BB+",
        "BB",
        "BB-",
        "B+",
        "B",
        "B-",
        "CCC+",
        "CCC",
        "CCC-",
        "CC",
        "C",
        "D",
    ]

    min_rating_index = (
        esg_ratings_order.index(min_esg_rating.upper())
        if min_esg_rating.upper() in esg_ratings_order
        else len(esg_ratings_order)
    )

    div_result = await client.call_tool(
        name=div_tool_name,
        arguments={"filter_type": div_filter_type, "filter_value": div_filter_value},
    )

    assert len(div_result) > 0, "MCP call failed or returned empty result"

    stock_list = extract_stocks_from_result(div_result)
    assert stock_list, "Failed to extract stock list from MCP result"

    stock_list = sort_stocks_by_code(stock_list)

    result_list = []
    for stock in stock_list:
        if len(result_list) >= max_stocks:
            break

        security_code = stock.get("security_code")
        if not security_code:
            continue

        try:
            esg_result = await client.call_tool(
                name=esg_tool_name,
                arguments={"security_code": security_code},
            )
            esg_rate = extract_esg_rate(esg_result)

            if esg_rate:
                esg_rate_upper = str(esg_rate).strip().upper()
                if esg_rate_upper in esg_ratings_order:
                    rating_index = esg_ratings_order.index(esg_rate_upper)
                    if rating_index <= min_rating_index:
                        result_list.append(
                            {
                                "security_code": security_code,
                                "security_name": stock.get("security_name", ""),
                                "div_rate": stock.get("value", ""),
                                "esg_rate": esg_rate,
                            }
                        )
        except Exception as e:
            logger.error(f"Failed to get ESG for {security_code}: {e}")
            continue

    return result_list


def extract_weather_info(result: list[dict[str, Any]] | dict[str, Any]) -> dict[str, Any]:
    """Extract weather information from MCP tool result."""
    if isinstance(result, dict):
        result = [result]

    weather_info = {}
    for item in result:
        if not isinstance(item, dict):
            continue
        text_content = _get_text_from_item(item)
        if text_content:
            try:
                data = json.loads(text_content)
                if isinstance(data, str):
                    data = json.loads(data)
                if isinstance(data, dict):
                    weather_info.update(data)
                elif isinstance(data, str):
                    weather_info["description"] = data
            except Exception:
                weather_info["description"] = text_content
        else:
            weather_info.update(item)
    return weather_info


async def query_weather(
    city: str,
    date: str | None = None,
) -> dict[str, Any]:
    """
    Query weather information for a city.

    Args:
        city: City name, e.g., "杭州"
        date: Date in format "YYYY-MM-DD", if None then query tomorrow

    Returns:
        dict: Weather information dictionary
    """
    client = init_mcp_clients()
    tool_name = "amap_maps_weather"

    # Try different parameter combinations
    possible_args = [
        {"city": city, "date": date},
        {"location": city, "date": date},
        {"city_name": city, "date": date},
        {"city": city},
        {"location": city},
    ]

    result = None
    for args in possible_args:
        try:
            result = await client.call_tool(name=tool_name, arguments=args)
            if result and isinstance(result, list) and len(result) > 0:
                break
        except Exception:
            continue

    if not result or not isinstance(result, list) or len(result) == 0:
        raise RuntimeError(f"Failed to query weather for city: {city}")

    return extract_weather_info(result)


def extract_route_result(result: list[dict[str, Any]]) -> dict[str, Any]:
    """Extract route information from MCP tool result."""
    route_info = {}
    for item in result:
        if not isinstance(item, dict):
            continue
        text_content = _get_text_from_item(item)
        if text_content:
            try:
                data = json.loads(text_content)
                if isinstance(data, str):
                    data = json.loads(data)
                if isinstance(data, dict):
                    route_info.update(data)
            except Exception:
                route_info["description"] = text_content
        else:
            route_info.update(item)
    return route_info


def _is_coordinate(coord: str) -> None:
    """Validate coordinate format (longitude,latitude)."""
    parts = coord.split(",")
    if len(parts) != 2:
        raise ValueError(f"Invalid coordinate format: {coord}")
    try:
        float(parts[0].strip())
        float(parts[1].strip())
    except ValueError:
        raise ValueError(f"Invalid coordinate format: {coord}")


def extract_distance_result(result: list[dict[str, Any]]) -> dict[str, Any]:
    """Extract distance calculation result from MCP tool result."""
    for item in result:
        if not isinstance(item, dict):
            continue
        text_content = _get_text_from_item(item)
        if not text_content:
            continue
        try:
            data = json.loads(text_content)
            if isinstance(data, str):
                data = json.loads(data)
            if isinstance(data, dict):
                return data
        except Exception:
            continue
    raise RuntimeError("Failed to extract distance calculation result from MCP tool")


async def calculate_distance(origins: str, destination: str) -> dict[str, Any]:
    """Calculate distance between origins and destination."""
    client = init_mcp_clients()
    result = await client.call_tool(
        name="amap_maps_distance", arguments={"origins": origins, "destination": destination}
    )
    return extract_distance_result(result)


def parse_arxiv_html(html_content: str, max_results: int = 5) -> list[dict[str, str]]:
    """Parse arXiv HTML content to extract paper titles and IDs."""
    papers = []
    entries = re.split(r"<dt>\s*<a name=", html_content)

    for entry in entries[1 : max_results + 1]:
        arxiv_id_match = re.search(r"arXiv:(\d+\.\d+)", entry)
        title_match = re.search(
            r"<div class=\'list-title mathjax\'><span class=\'descriptor\'>Title:</span>\s*(.*?)\s*</div>",
            entry,
        )

        if arxiv_id_match and title_match:
            papers.append(
                {
                    "title": title_match.group(1).strip(),
                    "url": f"https://arxiv.org/abs/{arxiv_id_match.group(1)}",
                }
            )

    return papers


async def get_latest_arxiv_papers(
    category: str = "cs.AI", max_results: int = 5
) -> list[dict[str, str]]:
    """Get latest arXiv papers from specified category."""
    client = init_mcp_clients()
    tool_name = "arXiv_get_recent_ai_papers"

    result = await client.call_tool(name=tool_name, arguments={"max_results": max_results})
    assert result and isinstance(result, list) and len(result) > 0, (
        "MCP call failed or returned empty result"
    )

    # Extract HTML content from result
    html_content = None
    for item in result:
        if not isinstance(item, dict):
            continue
        text_content = _get_text_from_item(item)
        if text_content and ("<!DOCTYPE html>" in text_content or "<dt>" in text_content):
            html_content = text_content
            break

    assert html_content, "Failed to extract HTML content from MCP result"
    return parse_arxiv_html(html_content, max_results)


def extract_papers_from_text(text: str, max_results: int = 5) -> list[dict[str, str]]:
    """Extract paper information from search results."""
    papers = []
    pattern = r"\*\*(.*?)\*\*\s+ID:\s+(\d+\.\d+)"
    matches = re.findall(pattern, text)

    for title, arxiv_id in matches[:max_results]:
        papers.append({"title": title.strip(), "url": f"https://arxiv.org/abs/{arxiv_id}"})

    return papers


async def search_arxiv_papers(query: str, max_results: int = 5) -> list[dict[str, str]]:
    """Search arXiv papers by query."""
    client = init_mcp_clients()
    tool_name = "arXiv_search_arxiv"

    result = await client.call_tool(
        name=tool_name, arguments={"query": query, "max_results": max_results}
    )

    assert len(result) > 0, "MCP call failed or returned empty result"

    text = _get_text_from_item(result)

    papers = extract_papers_from_text(text, max_results)
    assert papers, "Failed to extract papers from MCP result"
    return papers


async def get_driving_direction(origin: str, destination: str) -> dict[str, Any]:
    """Get driving direction between two coordinates using maps_direction_driving."""
    client = init_mcp_clients()
    tool_name = "amap_maps_direction_driving"

    result = await client.call_tool(
        name=tool_name, arguments={"origin": origin, "destination": destination}
    )
    assert result and isinstance(result, list) and len(result) > 0, (
        "MCP call failed or returned empty result"
    )

    route_info = extract_route_result(result)
    assert route_info, "Failed to extract route info from MCP result"

    return route_info


def extract_distance_and_duration(route_info: dict[str, Any]) -> dict[str, Any]:
    """Extract distance and duration from route information."""
    result = {}
    paths = route_info.get("paths", [])
    if paths and isinstance(paths, list):
        path = paths[0]
        if "distance" in path:
            result["distance"] = path["distance"]
        if "duration" in path:
            result["duration"] = path["duration"]
    return result


async def plan_bicycling_route(origin: str, destination: str) -> dict[str, Any]:
    """Plan a bicycling route from origin to destination and return distance and duration.

    Args:
        origin: Origin coordinate (format: "longitude,latitude")
        destination: Destination coordinate (format: "longitude,latitude")

    Returns:
        dict with "distance" (meters) and "duration" (seconds)
    """
    _is_coordinate(origin)
    _is_coordinate(destination)

    origin_coord = origin.strip()
    destination_coord = destination.strip()

    client = init_mcp_clients()
    tool_name = "amap_maps_direction_bicycling"

    result = await client.call_tool(
        name=tool_name, arguments={"origin": origin_coord, "destination": destination_coord}
    )
    assert result and isinstance(result, list) and len(result) > 0, (
        "MCP call failed or returned empty result"
    )

    route_data = extract_route_result(result)
    assert route_data, "Failed to extract route info from MCP result"

    distance_info = extract_distance_and_duration(route_data)
    assert distance_info, "Failed to extract distance info from MCP result"
    return distance_info


async def get_walking_direction(origin: str, destination: str) -> dict[str, Any]:
    """Get walking direction between two coordinates using maps_direction_walking."""
    client = init_mcp_clients()
    tool_name = "amap_maps_direction_walking"

    result = await client.call_tool(
        name=tool_name, arguments={"origin": origin, "destination": destination}
    )
    assert result and isinstance(result, list) and len(result) > 0, (
        "MCP call failed or returned empty result"
    )

    route_info = extract_route_result(result)
    assert route_info, "Failed to extract route info from MCP result"

    return route_info


async def plan_walking_route(origin: str, destination: str) -> dict[str, Any]:
    """Plan a walking route from origin to destination.

    Args:
        origin: Origin coordinate (format: "longitude,latitude")
        destination: Destination coordinate (format: "longitude,latitude")
    """
    _is_coordinate(origin)
    _is_coordinate(destination)

    origin_coord = origin.strip()
    destination_coord = destination.strip()

    return {
        "origin": {"coordinates": origin_coord},
        "destination": {"coordinates": destination_coord},
        "route": await get_walking_direction(origin_coord, destination_coord),
    }


async def plan_route(origin: str, destination: str) -> dict[str, Any]:
    """Plan a driving route from origin to destination.

    Args:
        origin: Origin coordinate (format: "longitude,latitude")
        destination: Destination coordinate (format: "longitude,latitude")
    """
    _is_coordinate(origin)
    _is_coordinate(destination)

    origin_coord = origin.strip()
    destination_coord = destination.strip()

    return {
        "origin": {"coordinates": origin_coord},
        "destination": {"coordinates": destination_coord},
        "route": await get_driving_direction(origin_coord, destination_coord),
    }


def format_places_result(result: dict[str, Any]) -> list[str]:
    """Format places search result as name：address list."""
    formatted = []
    if "results" in result:
        for place in result["results"]:
            name = place.get("name", "")
            address = place.get("address", place.get("location", ""))
            if name:
                formatted.append(f"{name}：{address}")
    elif "pois" in result:
        for place in result["pois"]:
            name = place.get("name", "")
            address = place.get("address", place.get("location", ""))
            if name:
                formatted.append(f"{name}：{address}")
    return formatted


async def search_nearby(location: str, radius: str, keywords: str) -> list[str]:
    """Search nearby places using maps_around_search."""
    client = init_mcp_clients()
    tool_name = "amap_maps_around_search"

    result = await client.call_tool(
        name=tool_name,
        arguments={"location": location, "radius": radius, "keywords": keywords},
    )
    assert result and isinstance(result, list) and len(result) > 0, (
        "MCP call failed or returned empty result"
    )

    route_info = extract_route_result(result)
    assert route_info, "Failed to extract route info from MCP result"

    return format_places_result(route_info)


async def list_open_issues(owner: str, repo: str, state: str = "open") -> str:
    """List open issues from a GitHub repository."""
    client = init_mcp_clients()
    tool_name = "gitHub_list_issues"

    result = await client.call_tool(
        name=tool_name, arguments={"owner": owner, "repo": repo, "state": state}
    )
    assert result and isinstance(result, list) and len(result) > 0, (
        "MCP call failed or returned empty result"
    )

    issues = extract_issues_result(result)
    assert issues, "Failed to extract issues list from MCP result"

    open_issues = [issue for issue in issues if issue.get("state", "").lower() == "open"]

    return open_issues


async def search_issues(owner: str, repo: str, query: str) -> list[str]:
    """Search issues in a GitHub repository and return URLs using gitHub_search_issues."""
    client = init_mcp_clients()
    tool_name = "gitHub_search_issues"

    # Build search query: repo:owner/repo is:issue query
    search_query = f"repo:{owner}/{repo} is:issue {query}"

    result = await client.call_tool(name=tool_name, arguments={"q": search_query})
    assert result and isinstance(result, list) and len(result) > 0, (
        "MCP call failed or returned empty result"
    )

    issues = extract_issues_result(result)
    assert issues, "Failed to extract issues list from MCP result"

    return [
        issue.get("html_url", issue.get("url", ""))
        for issue in issues
        if issue.get("html_url") or issue.get("url")
    ]


def extract_commits_result(result: list[dict[str, Any]] | dict[str, Any]) -> list[dict[str, Any]]:
    """Extract commits list from MCP tool result."""
    return _extract_list_from_result(
        result, "Failed to extract commits list from MCP result", ["commits", "items"]
    )


async def list_recent_commits(owner: str, repo: str, limit: int = 5, page: int = 1) -> list[str]:
    """List recent commits from a GitHub repository."""
    client = init_mcp_clients()
    tool_name = "gitHub_list_commits"

    result = await client.call_tool(
        name=tool_name, arguments={"owner": owner, "repo": repo, "page": page}
    )
    assert result and isinstance(result, list) and len(result) > 0, (
        "MCP call failed or returned empty result"
    )

    commits = extract_commits_result(result)
    assert commits, "Failed to extract commits list from MCP result"

    formatted = []
    for commit in commits[:limit]:
        # Try multiple paths for author: commit.commit.author (GitHub API format), commit.author
        commit_obj = commit.get("commit", {})
        author = commit_obj.get("author", {}) or commit.get("author", {})
        if isinstance(author, dict):
            # Prefer login (GitHub username) over name, but use name if login not available
            author_name = author.get("login") or author.get("name") or ""
        else:
            author_name = str(author) if author else ""

        # Try multiple paths for message: commit.commit.message (GitHub API format), commit.message
        message = commit_obj.get("message", "") or commit.get("message", "")
        message = message.split("\n")[0].strip() if isinstance(message, str) else ""

        if author_name and message:
            formatted.append(f"{author_name}: {message}")

    assert formatted, "Failed to extract commits list from MCP result"
    return formatted


def _get_text_from_item(item: dict[str, Any]) -> str | None:
    """Extract text content from MCP result item."""
    if "content" in item and isinstance(item["content"], list) and item["content"]:
        return item["content"][0].get("text")
    if isinstance(item, list) and len(item) > 0:
        return item[0].get("text")
    return item.get("text")


def _extract_list_from_dict(
    data: dict[str, Any], list_keys: list[str] | None = None
) -> list[dict[str, Any]]:
    """Extract list from dictionary data."""
    if list_keys:
        for key in list_keys:
            if key in data:
                value = data[key]
                return value if isinstance(value, list) else [value]
    for key in ["items", "commits", "issues"]:
        if key in data:
            value = data[key]
            return value if isinstance(value, list) else [value]
    return [data]


def _extract_list_from_result(
    result: list[dict[str, Any]] | dict[str, Any],
    error_msg: str,
    list_keys: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Extract list data from MCP tool result."""
    items = []

    # Normalize to list format
    if isinstance(result, dict):
        result = [result]

    # Process each item
    for item in result:
        if not isinstance(item, dict):
            continue

        # Check for direct item (has number or title)
        if "number" in item or "title" in item:
            items.append(item)
            continue

        # Try to extract from text content
        text_content = _get_text_from_item(item)
        if not text_content:
            continue

        try:
            data = json.loads(text_content)
            if isinstance(data, str):
                data = json.loads(data)

            if isinstance(data, list):
                items.extend(data)
            elif isinstance(data, dict):
                items.extend(_extract_list_from_dict(data, list_keys))
        except Exception:
            continue

    if items:
        return items
    raise RuntimeError(error_msg)


def extract_issues_result(result: list[dict[str, Any]] | dict[str, Any]) -> list[dict[str, Any]]:
    """Extract issues list from MCP tool result."""
    return _extract_list_from_result(
        result, "Failed to extract issues list from MCP result", ["items", "issues"]
    )


def extract_user_result(result: list[dict[str, Any]] | dict[str, Any]) -> list[dict[str, Any]]:
    """Extract user search results from MCP tool result."""
    return _extract_list_from_result(
        result, "Failed to extract user search results from MCP result"
    )


async def search_users(
    query: str, sort: str = "followers", order: str = "desc", per_page: int = 5
) -> list[dict[str, Any]]:
    """Search GitHub users sorted by followers."""
    client = init_mcp_clients()
    tool_name = "gitHub_search_users"

    result = await client.call_tool(
        name=tool_name,
        arguments={"q": f"{query}", "per_page": per_page, "sort": sort, "order": order},
    )
    assert result and isinstance(result, list) and len(result) > 0, (
        "MCP call failed or returned empty result"
    )

    users = extract_user_result(result)
    assert users, "Failed to extract users from MCP result"
    return users


def extract_repo_result(result: list[dict[str, Any]] | dict[str, Any]) -> list[dict[str, Any]]:
    """Extract repository search results from MCP tool result."""
    return _extract_list_from_result(
        result, "Failed to extract repository search results from MCP result"
    )


async def search_repositories(query: str, per_page: int = 5) -> list[dict[str, Any]]:
    """Search GitHub repositories."""
    client = init_mcp_clients()
    tool_name = "gitHub_search_repositories"

    result = await client.call_tool(
        name=tool_name, arguments={"query": query, "per_page": per_page, "page": 1}
    )
    assert result and isinstance(result, list) and len(result) > 0, (
        "MCP call failed or returned empty result"
    )
    repos = extract_repo_result(result)[:per_page]
    assert repos, "Failed to extract repositories from MCP result"

    return repos
