import os
import ast
import json
from pathlib import Path

# 配置项
SEARCH_DIR = "tasks/definitions"  # 你刚才 ls 看到的目录
TARGET_TAG = "agent-user-interaction"
OUTPUT_FILE = "agent_interaction_tasks.jsonl"

def extract_task_from_file(file_path):
    """解析单个 Python 文件，提取符合条件的类信息"""
    found_tasks = []
    
    with open(file_path, "r", encoding="utf-8") as f:
        try:
            file_content = f.read()
            tree = ast.parse(file_content)
        except Exception as e:
            print(f"Skipping {file_path}: {e}")
            return []

    # 遍历文件中的每个节点
    for node in ast.walk(tree):
        # 我们只关心类定义 (ClassDef)
        if isinstance(node, ast.ClassDef):
            task_info = {
                "file_path": str(file_path),
                "class_name": node.name,
                "goal": None,
                "task_tags": set(),
                "app_names": []
            }

            # 遍历类体内的赋值语句 (例如 goal = "...", task_tags = {...})
            for item in node.body:
                if isinstance(item, ast.Assign):
                    for target in item.targets:
                        if isinstance(target, ast.Name):
                            # 提取 task_tags
                            if target.id == "task_tags":
                                try:
                                    # 安全地评估字面量集合/列表
                                    val = ast.literal_eval(item.value)
                                    if isinstance(val, (set, list, tuple)):
                                        task_info["task_tags"] = set(val)
                                except ValueError:
                                    pass # 忽略复杂的表达式
                            
                            # 提取 goal
                            elif target.id == "goal":
                                try:
                                    val = ast.literal_eval(item.value)
                                    task_info["goal"] = val
                                except ValueError:
                                    pass

                            # 提取 app_names (可选，方便查看涉及哪些APP)
                            elif target.id == "app_names":
                                try:
                                    val = ast.literal_eval(item.value)
                                    task_info["app_names"] = list(val)
                                except ValueError:
                                    pass

            # 检查是否包含目标 tag
            if TARGET_TAG in task_info["task_tags"]:
                # 将 set 转回 list 以便 JSON 序列化
                task_info["task_tags"] = list(task_info["task_tags"])
                found_tasks.append(task_info)
    
    return found_tasks

def main():
    root_path = Path(SEARCH_DIR)
    all_matched_tasks = []

    print(f"🔍 开始扫描 {root_path} 下的所有任务...")

    # 递归查找所有 .py 文件
    for file_path in root_path.rglob("*.py"):
        if file_path.name == "__init__.py":
            continue
            
        tasks = extract_task_from_file(file_path)
        if tasks:
            all_matched_tasks.extend(tasks)
            print(f"✅ 发现: {tasks[0]['class_name']} ({file_path.name})")

    # 写入 JSONL 文件
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for task in all_matched_tasks:
            f.write(json.dumps(task, ensure_ascii=False) + "\n")

    print(f"\n🎉 完成！共找到 {len(all_matched_tasks)} 个任务。")
    print(f"📂 结果已保存至: {os.path.abspath(OUTPUT_FILE)}")

if __name__ == "__main__":
    main()