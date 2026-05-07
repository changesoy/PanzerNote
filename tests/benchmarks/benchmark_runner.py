# -*- coding: utf-8 -*-
"""
性能基准测试运行器
自动化执行性能测试并收集指标
"""

import json
import os
import sys
import time
import tracemalloc
from datetime import datetime
from typing import Dict, List, Any, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from benchmarks.test_data_generator import (
    generate_all_test_data, FILE_GENERATORS,
    SMALL_FILE_SIZE, MEDIUM_FILE_SIZE, LARGE_FILE_SIZE,
)


class BenchmarkResult:
    def __init__(self, name: str):
        self.name = name
        self.metrics: Dict[str, Any] = {}
        self.timestamp = datetime.now().isoformat()

    def add_metric(self, key: str, value: Any):
        self.metrics[key] = value

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "timestamp": self.timestamp,
            "metrics": self.metrics,
        }


class BenchmarkRunner:
    def __init__(self, base_dir: str):
        self.base_dir = base_dir
        self.results: List[BenchmarkResult] = []
        self.data_dir = generate_all_test_data(base_dir)

    def _load_test_file(self, size: str, file_type: str) -> str:
        num_lines = {"small": SMALL_FILE_SIZE, "medium": MEDIUM_FILE_SIZE, "large": LARGE_FILE_SIZE}[size]
        filename = f"{size}_{file_type}_{num_lines}lines.txt"
        filepath = os.path.join(self.data_dir, filename)
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()

    def benchmark_file_open(self) -> BenchmarkResult:
        result = BenchmarkResult("file_open")
        from PyQt5.QtWidgets import QApplication
        from src.core.config import Config
        from src.editor.editor import Editor

        app = QApplication.instance()
        if app is None:
            app = QApplication([])

        tmp_path = os.path.join(self.base_dir, "benchmarks", "_tmp_config")
        os.makedirs(os.path.join(tmp_path, "data", "config"), exist_ok=True)
        os.makedirs(os.path.join(tmp_path, "data", "gamedata"), exist_ok=True)
        with open(os.path.join(tmp_path, "user_data_path.txt"), "w") as f:
            f.write(tmp_path)
        config = Config(app_dir=tmp_path)

        for size in ["small", "medium", "large"]:
            content = self._load_test_file(size, "python")
            times = []
            for _ in range(3):
                editor = Editor(config)
                t0 = time.perf_counter()
                editor.setPlainText(content)
                editor.set_file_type("test.py")
                app.processEvents()
                t1 = time.perf_counter()
                times.append(t1 - t0)
                editor.deleteLater()
                app.processEvents()

            avg_time = sum(times) / len(times)
            result.add_metric(f"{size}_avg_ms", round(avg_time * 1000, 2))
            result.add_metric(f"{size}_min_ms", round(min(times) * 1000, 2))
            result.add_metric(f"{size}_max_ms", round(max(times) * 1000, 2))

        self.results.append(result)
        return result

    def benchmark_scroll_fps(self) -> BenchmarkResult:
        result = BenchmarkResult("scroll_fps")
        from PyQt5.QtWidgets import QApplication
        from PyQt5.QtCore import QEvent
        from PyQt5.QtGui import QKeyEvent, QWheelEvent, QPoint
        from src.core.config import Config
        from src.editor.editor import Editor

        app = QApplication.instance()
        if app is None:
            app = QApplication([])

        tmp_path = os.path.join(self.base_dir, "benchmarks", "_tmp_config")
        config = Config(app_dir=tmp_path)

        for size in ["small", "medium", "large"]:
            content = self._load_test_file(size, "python")
            editor = Editor(config)
            editor.resize(800, 600)
            editor.show()
            editor.setPlainText(content)
            editor.set_file_type("test.py")
            app.processEvents()

            scroll_count = 100
            t0 = time.perf_counter()
            for _ in range(scroll_count):
                scroll_event = QWheelEvent(
                    QPoint(400, 300), QPoint(400, 300),
                    QPoint(0, -120), QPoint(0, -120),
                    0, Qt.Vertical, Qt.NoButton, Qt.NoModifier,
                )
                app.sendEvent(editor.viewport(), scroll_event)
                app.processEvents()
            t1 = time.perf_counter()

            total_ms = (t1 - t0) * 1000
            fps = scroll_count / (t1 - t0) if (t1 - t0) > 0 else 0
            result.add_metric(f"{size}_total_ms", round(total_ms, 2))
            result.add_metric(f"{size}_fps", round(fps, 1))

            editor.deleteLater()
            app.processEvents()

        self.results.append(result)
        return result

    def benchmark_minimap_render(self) -> BenchmarkResult:
        result = BenchmarkResult("minimap_render")
        from PyQt5.QtWidgets import QApplication
        from src.core.config import Config
        from src.editor.editor import Editor

        app = QApplication.instance()
        if app is None:
            app = QApplication([])

        tmp_path = os.path.join(self.base_dir, "benchmarks", "_tmp_config")
        config = Config(app_dir=tmp_path)

        for size in ["small", "medium", "large"]:
            content = self._load_test_file(size, "python")
            editor = Editor(config)
            editor.resize(800, 600)
            editor.show()
            editor.setPlainText(content)
            editor.set_file_type("test.py")
            app.processEvents()

            minimap = editor.minimap
            if minimap:
                times = []
                for _ in range(5):
                    minimap._cache_valid = False
                    t0 = time.perf_counter()
                    minimap._rebuild_cache()
                    t1 = time.perf_counter()
                    times.append(t1 - t0)

                avg_ms = sum(times) / len(times) * 1000
                result.add_metric(f"{size}_avg_ms", round(avg_ms, 2))
                result.add_metric(f"{size}_min_ms", round(min(times) * 1000, 2))
            else:
                result.add_metric(f"{size}_avg_ms", -1)

            editor.deleteLater()
            app.processEvents()

        self.results.append(result)
        return result

    def benchmark_highlight_code(self) -> BenchmarkResult:
        result = BenchmarkResult("highlight_code")
        from src.editor.highlight_themes import highlight_code_html, HAS_PYGMENTS

        if not HAS_PYGMENTS:
            result.add_metric("available", False)
            self.results.append(result)
            return result

        result.add_metric("available", True)

        for size in ["small", "medium"]:
            content = self._load_test_file(size, "python")
            times = []
            for _ in range(3):
                t0 = time.perf_counter()
                html = highlight_code_html(content, "python")
                t1 = time.perf_counter()
                times.append(t1 - t0)

            avg_ms = sum(times) / len(times) * 1000
            result.add_metric(f"{size}_avg_ms", round(avg_ms, 2))

        self.results.append(result)
        return result

    def benchmark_memory_usage(self) -> BenchmarkResult:
        result = BenchmarkResult("memory_usage")
        from PyQt5.QtWidgets import QApplication
        from src.core.config import Config
        from src.editor.editor import Editor

        app = QApplication.instance()
        if app is None:
            app = QApplication([])

        tmp_path = os.path.join(self.base_dir, "benchmarks", "_tmp_config")
        config = Config(app_dir=tmp_path)

        for size in ["small", "medium", "large"]:
            content = self._load_test_file(size, "python")

            tracemalloc.start()
            editor = Editor(config)
            editor.setPlainText(content)
            editor.set_file_type("test.py")
            app.processEvents()

            current, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()

            result.add_metric(f"{size}_current_mb", round(current / 1024 / 1024, 2))
            result.add_metric(f"{size}_peak_mb", round(peak / 1024 / 1024, 2))

            editor.deleteLater()
            app.processEvents()

        self.results.append(result)
        return result

    def benchmark_startup(self) -> BenchmarkResult:
        result = BenchmarkResult("startup")
        import subprocess

        script = (
            "import sys, time; "
            "sys.path.insert(0, r'" + self.base_dir + "'); "
            "t0 = time.perf_counter(); "
            "from src.core.config import Config; "
            "from src.main_window import MainWindow; "
            "t1 = time.perf_counter(); "
            "print(f'IMPORT_TIME:{(t1-t0)*1000:.2f}')"
        )

        times = []
        for _ in range(3):
            t0 = time.perf_counter()
            proc = subprocess.run(
                [sys.executable, "-c", script],
                capture_output=True, text=True,
                cwd=self.base_dir,
                timeout=30,
            )
            t1 = time.perf_counter()
            times.append(t1 - t0)

        avg_ms = sum(times) / len(times) * 1000
        result.add_metric("cold_start_avg_ms", round(avg_ms, 2))
        result.add_metric("cold_start_min_ms", round(min(times) * 1000, 2))

        self.results.append(result)
        return result

    def run_all(self) -> List[BenchmarkResult]:
        print("=" * 60)
        print("PanzerNote 性能基准测试")
        print(f"时间: {datetime.now().isoformat()}")
        print("=" * 60)

        benchmarks = [
            ("文件打开性能", self.benchmark_file_open),
            ("滚动FPS", self.benchmark_scroll_fps),
            ("缩略图渲染", self.benchmark_minimap_render),
            ("代码高亮", self.benchmark_highlight_code),
            ("内存占用", self.benchmark_memory_usage),
            ("启动性能", self.benchmark_startup),
        ]

        for name, func in benchmarks:
            print(f"\n>>> 运行: {name}")
            try:
                result = func()
                print(f"    完成: {json.dumps(result.metrics, indent=2, ensure_ascii=False)}")
            except Exception as e:
                print(f"    失败: {e}")
                result = BenchmarkResult(name)
                result.add_metric("error", str(e))
                self.results.append(result)

        return self.results

    def save_results(self, filepath: Optional[str] = None):
        if filepath is None:
            results_dir = os.path.join(self.base_dir, "benchmarks", "results")
            os.makedirs(results_dir, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = os.path.join(results_dir, f"bench_{timestamp}.json")

        data = {
            "timestamp": datetime.now().isoformat(),
            "results": [r.to_dict() for r in self.results],
        }

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        print(f"\n结果已保存: {filepath}")
        return filepath


def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    runner = BenchmarkRunner(base_dir)
    runner.run_all()
    runner.save_results()


if __name__ == "__main__":
    main()
