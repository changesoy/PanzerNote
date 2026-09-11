# C 路线 Handoff

## 定位

C 路线面向完整形态的 PanzerNote。

它保留编辑器主体，同时继续承载 PanzerNote 真正的长期目标：

- Markdown 与富文档能力；
- Mermaid；
- 数学公式；
- HTML / CSS；
- 更丰富的交互式预览；
- 游戏资源循环；
- 建造、收集、图鉴、车库、小秘书等游戏系统。

对于完整版而言，未来存在一个 Web runtime 是合理且很可能必要的。

问题不再是“要不要 Web”，而是：

> **怎样以尽可能低的发行成本获得成熟、完整的 Web 能力。**

## Web 路线

C 从现有 WebEngine 实现的经验出发，但不将 Qt WebEngine 本身视为最终答案。

长期更值得关注的是类似 **WebView2** 的系统共享 Web Runtime：

```text
PanzerNote
    ↓
Web Preview Adapter
    ↓
System Web Runtime
```

这样可以继续使用成熟的 HTML / CSS / JavaScript / Mermaid / MathJax 生态，同时避免 PanzerNote 自己携带一整套 Chromium。

当前 Qt / PyQt 与 WebView2 的结合仍需要验证，因此 C 首先是一个实验和演进方向，而不是提前锁死具体实现。

最好让上层 Preview 尽量依赖抽象能力，例如 HTML 加载、JavaScript 执行、消息通信、本地资源访问等，而不是过度依赖某一种 Web 控件的专有 API。

## 关于 B 路线

`refactor20260910-webengine_single_path` 到此可以视为完成使命。

B 证明了：

- 单一路径 Web Preview 是可行的；
- Web 技术非常适合复杂 Markdown、HTML 和未来富文档能力；
- 删除 fallback 后架构可以明显简化；
- 但随应用分发 Qt WebEngine / Chromium 的固定体积成本仍然过高。

因此 B 不再作为长期产品路线继续优化。

建议将其冻结并保留为历史参考或打 tag。

它今后的主要价值是：

1. 作为完整 Web Preview 的行为参考实现；
2. 为 C 提供迁移依据；
3. 如果 WebView2 等方案遇到不可接受的问题，保留一个已经验证过的 WebEngine 后备方案。

换句话说：

> **B 不是失败路线，而是已经完成验证任务的原型。**

## 与 A 的关系

A 和 C 不应该最终发展成两个互不相关的项目。

理想状态仍然是：

```text
                 Shared Core / Editor
                         │
              ┌──────────┴──────────┐
              │                     │
          Lite Build            Full Build
              │                     │
       Native Preview          Web Preview
          No Game              Full Game
```

A 负责持续验证轻量化边界。

C 负责允许 PanzerNote 在真正需要的地方使用成熟技术，不因为包体目标而重复实现整个 Web 生态。

两条路线共同约束最终架构。

## 完成状态（迁移已落地：WebView2 单路径）

C 路线的迁移目标已完成：Qt WebEngine 已从应用与打包中摘除，**WebView2 成为唯一的预览 / PDF 导出后端**。

- **后端**：`src/editor/web_preview.py`（抽象接口，8 项能力）之下只保留 `WebView2PreviewAdapter`（`src/editor/web_preview_webview2.py`，PyWinRT 绑定）；`create_preview_adapter()` 恒返回该后端，无 feature flag 分支。WebEngine 后端 `web_preview_webengine.py` 与启动锚点 `webengine_runtime.py` 已删除，`main.py` 移除为 WebEngine 加的 `AA_ShareOpenGLContexts`。
- **事件循环**：`main.py` 以 `qasync.QEventLoop` 取代 `app.exec()`，把 asyncio 与 Qt 事件循环合并到同一线程（PyWinRT 的硬性前提），并在主窗口创建前 `set_event_loop`。
- **运行前提**：需系统安装 Microsoft Edge WebView2 Runtime（**不随包分发**）。`src/editor/webview2_runtime.py` 只读注册表检测；缺失时启动记录 error 日志并在窗口显示后弹一次可见提示，预览区显示同一份安装指引。
- **依赖变化**：移除 `PyQt6-WebEngine`；新增 `qasync`、`webview2-Microsoft.Web.WebView2.Core`、`winrt-Windows.Foundation`（传递依赖 `winrt-runtime`）。
- **打包体积**：冻结产物 **92.8 MB**（对照此前 WebEngine 形态约 362 MB）；WebEngine 相关占用 343.3 MB（`Qt6WebEngineCore.dll` 195.3 MB、devtools debug pak 72.3 MB、`icudtl.dat` 10 MB 等）随依赖一并消失。
- **验证结论**：全量 pytest 1454 passed / 32 skipped / 0 failed；mypy 126 文件 0 错；真机启动日志显示 WebView2 后端就绪、导航成功。

后续功能对齐与发行收尾见 `111.md` 的 C4 / C5 / C6。
