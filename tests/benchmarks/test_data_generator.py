# -*- coding: utf-8 -*-
"""
性能基准测试数据生成器
生成不同规模的测试文件用于基准测试
"""

import os
import random
import string


PYTHON_TEMPLATE = '''# -*- coding: utf-8 -*-
"""Module {module_name}"""

import os
import sys
from typing import List, Dict, Optional


class MyClass{class_num}:
    """示例类 {class_num}"""

    def __init__(self, name: str, value: int = 0):
        self.name = name
        self.value = value
        self._data: Dict[str, any] = {{}}

    def process(self, items: List[str]) -> Optional[str]:
        """处理数据"""
        if not items:
            return None
        result = []
        for item in items:
            if item.startswith("test_"):
                result.append(item.upper())
            else:
                result.append(item.lower())
        return ", ".join(result)

    def calculate(self, x: int, y: int) -> int:
        """计算"""
        return x * y + self.value


def helper_function_{func_num}(data: List[int]) -> Dict[str, float]:
    """辅助函数"""
    if not data:
        return {{"count": 0, "avg": 0.0, "max": 0}}
    return {{
        "count": len(data),
        "avg": sum(data) / len(data),
        "max": max(data),
    }}


# 常量定义
CONSTANT_{const_num} = "{const_value}"
CONFIG_{config_num} = {{
    "debug": False,
    "port": {port},
    "host": "localhost",
    "timeout": 30,
}}
'''

MARKDOWN_TEMPLATE = '''# 文档标题 {title_num}

这是第 {section_num} 节的内容。包含一些**粗体文字**和*斜体文字*。

## 子标题 {sub_num}

- 列表项 1：普通文本
- 列表项 2：`行内代码` 示例
- 列表项 3：[链接文字](https://example.com)

> 引用文本：这是一段引用内容，用于测试 Markdown 渲染性能。

### 代码示例

```python
def example_function(x: int, y: int) -> int:
    """示例函数"""
    result = x + y
    return result * 2
```

### 表格

| 列1 | 列2 | 列3 |
|-----|-----|-----|
| 数据1 | 数据2 | 数据3 |
| 数据4 | 数据5 | 数据6 |

---

## 另一个章节

段落文本，包含普通内容和一些 `code` 片段。

1. 有序列表项
2. 另一个有序列表项
3. 第三个列表项

![图片描述](./images/example.png)
'''


def generate_python_file(num_lines: int) -> str:
    lines = []
    i = 0
    while len(lines) < num_lines:
        block = PYTHON_TEMPLATE.format(
            module_name=f"module_{i}",
            class_num=i,
            func_num=i,
            const_num=i,
            const_value=f"value_{i}",
            config_num=i,
            port=8000 + i,
        )
        block_lines = block.strip().split("\n")
        remaining = num_lines - len(lines)
        lines.extend(block_lines[:remaining])
        i += 1
    return "\n".join(lines[:num_lines])


def generate_markdown_file(num_lines: int) -> str:
    lines = []
    i = 0
    while len(lines) < num_lines:
        block = MARKDOWN_TEMPLATE.format(
            title_num=i,
            section_num=i,
            sub_num=i,
        )
        block_lines = block.strip().split("\n")
        remaining = num_lines - len(lines)
        lines.extend(block_lines[:remaining])
        i += 1
    return "\n".join(lines[:num_lines])


def generate_mixed_file(num_lines: int) -> str:
    lines = []
    for i in range(num_lines):
        r = random.random()
        if r < 0.3:
            lines.append(f"    x_{i} = {random.randint(0, 1000)}")
        elif r < 0.5:
            lines.append(f"def func_{i}():")
        elif r < 0.7:
            lines.append(f"    return {random.choice(string.ascii_letters)}")
        elif r < 0.85:
            lines.append(f"# Comment line {i}")
        else:
            lines.append("")
    return "\n".join(lines)


FILE_GENERATORS = {
    "python": generate_python_file,
    "markdown": generate_markdown_file,
    "mixed": generate_mixed_file,
}

SMALL_FILE_SIZE = 500
MEDIUM_FILE_SIZE = 5000
LARGE_FILE_SIZE = 50000


def ensure_test_data_dir(base_dir: str) -> str:
    data_dir = os.path.join(base_dir, "benchmarks", "test_data")
    os.makedirs(data_dir, exist_ok=True)
    return data_dir


def generate_all_test_data(base_dir: str):
    data_dir = ensure_test_data_dir(base_dir)

    sizes = {
        "small": SMALL_FILE_SIZE,
        "medium": MEDIUM_FILE_SIZE,
        "large": LARGE_FILE_SIZE,
    }

    for size_name, num_lines in sizes.items():
        for file_type, generator in FILE_GENERATORS.items():
            filename = f"{size_name}_{file_type}_{num_lines}lines.txt"
            filepath = os.path.join(data_dir, filename)
            if not os.path.exists(filepath):
                content = generator(num_lines)
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(content)

    return data_dir
