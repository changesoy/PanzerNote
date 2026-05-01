# -*- coding: utf-8 -*-
"""基准测试脚本 - 获取优化前的性能基线，结果写入JSON"""
import sys
import os
import time
import json
import tracemalloc
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

results_dir = os.path.join(BASE_DIR, "benchmarks", "results")
os.makedirs(results_dir, exist_ok=True)
result_file = os.path.join(results_dir, "baseline_pre_optimization.json")

results = {
    "timestamp": datetime.now().isoformat(),
    "phase": "pre_optimization",
    "metrics": {},
}

def save_results():
    with open(result_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

try:
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtCore import Qt
    app = QApplication.instance() or QApplication([])

    from src.core.config import Config
    tmp = os.path.join(BASE_DIR, "benchmarks", "_tmp_config")
    config = Config(app_dir=tmp)

    from src.editor.editor import Editor
    from benchmarks.test_data_generator import generate_python_file

    # 1. 文件打开
    print("测试: 文件打开...")
    file_open = {}
    for name, nlines in [("small", 500), ("medium", 5000), ("large", 50000)]:
        content = generate_python_file(nlines)
        times = []
        for i in range(3):
            editor = Editor(config)
            editor.resize(800, 600)
            editor.show()
            t0 = time.perf_counter()
            editor.setPlainText(content)
            editor.set_file_type("test.py")
            app.processEvents()
            t1 = time.perf_counter()
            times.append(t1 - t0)
            editor.deleteLater()
            app.processEvents()
        file_open[name] = {
            "avg_ms": round(sum(times) / len(times) * 1000, 2),
            "min_ms": round(min(times) * 1000, 2),
            "max_ms": round(max(times) * 1000, 2),
        }
        print(f"  {name}({nlines}行): avg={file_open[name]['avg_ms']}ms")
    results["metrics"]["file_open"] = file_open
    save_results()

    # 2. 代码高亮
    print("测试: 代码高亮...")
    highlight = {}
    from src.editor.highlight_themes import highlight_code_html, HAS_PYGMENTS
    highlight["pygments_available"] = HAS_PYGMENTS
    if HAS_PYGMENTS:
        for name, nlines in [("small", 500), ("medium", 5000)]:
            content = generate_python_file(nlines)
            times = []
            for i in range(3):
                t0 = time.perf_counter()
                html = highlight_code_html(content, "python")
                t1 = time.perf_counter()
                times.append(t1 - t0)
            highlight[name] = {
                "avg_ms": round(sum(times) / len(times) * 1000, 2),
                "min_ms": round(min(times) * 1000, 2),
            }
            print(f"  {name}({nlines}行): avg={highlight[name]['avg_ms']}ms")
    results["metrics"]["highlight_code"] = highlight
    save_results()

    # 3. Minimap渲染
    print("测试: Minimap渲染...")
    minimap_metrics = {}
    for name, nlines in [("small", 500), ("medium", 5000), ("large", 50000)]:
        content = generate_python_file(nlines)
        editor = Editor(config)
        editor.resize(800, 600)
        editor.show()
        editor.setPlainText(content)
        editor.set_file_type("test.py")
        app.processEvents()
        mw = editor.minimap
        if mw:
            times = []
            for i in range(3):
                mw._cache_valid = False
                t0 = time.perf_counter()
                mw._rebuild_cache()
                t1 = time.perf_counter()
                times.append(t1 - t0)
            minimap_metrics[name] = {
                "avg_ms": round(sum(times) / len(times) * 1000, 2),
                "min_ms": round(min(times) * 1000, 2),
            }
            print(f"  {name}({nlines}行): avg={minimap_metrics[name]['avg_ms']}ms")
        else:
            minimap_metrics[name] = None
        editor.deleteLater()
        app.processEvents()
    results["metrics"]["minimap_render"] = minimap_metrics
    save_results()

    # 4. 内存占用
    print("测试: 内存占用...")
    memory = {}
    for name, nlines in [("small", 500), ("medium", 5000), ("large", 50000)]:
        content = generate_python_file(nlines)
        tracemalloc.start()
        editor = Editor(config)
        editor.setPlainText(content)
        editor.set_file_type("test.py")
        app.processEvents()
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        memory[name] = {
            "current_mb": round(current / 1024 / 1024, 2),
            "peak_mb": round(peak / 1024 / 1024, 2),
        }
        print(f"  {name}({nlines}行): peak={memory[name]['peak_mb']}MB")
        editor.deleteLater()
        app.processEvents()
    results["metrics"]["memory_usage"] = memory
    save_results()

    # 5. 滚动FPS
    print("测试: 滚动FPS...")
    scroll = {}
    for name, nlines in [("small", 500), ("medium", 5000), ("large", 50000)]:
        content = generate_python_file(nlines)
        editor = Editor(config)
        editor.resize(800, 600)
        editor.show()
        editor.setPlainText(content)
        editor.set_file_type("test.py")
        app.processEvents()
        scroll_count = 60
        t0 = time.perf_counter()
        for _ in range(scroll_count):
            sb = editor.verticalScrollBar()
            sb.setValue(sb.value() + 3)
            app.processEvents()
        t1 = time.perf_counter()
        elapsed = t1 - t0
        fps = scroll_count / elapsed if elapsed > 0 else 0
        scroll[name] = {
            "fps": round(fps, 1),
            "total_ms": round(elapsed * 1000, 2),
        }
        print(f"  {name}({nlines}行): {fps:.1f}FPS")
        editor.deleteLater()
        app.processEvents()
    results["metrics"]["scroll_fps"] = scroll
    save_results()

    print(f"\n基线测试完成，结果已保存: {result_file}")

except Exception as e:
    import traceback
    traceback.print_exc()
    results["error"] = str(e)
    save_results()
    print(f"测试出错: {e}")
