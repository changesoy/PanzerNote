# -*- coding: utf-8 -*-
"""
应用上下文（hotfix 阶段 7）

纯持有容器：承载已拆好的子模块，稳定依赖边界。
过渡期与 Config 门面共存；新代码鼓励直接使用
app_context.settings_store / workspace_store / path_resolver。
"""

from .config import Config
from .path_resolver import PathResolver
from .settings_store import SettingsStore
from .workspace_store import WorkspaceStore


class AppContext:
    """应用上下文：持有已拆分子模块与 Config 门面引用。"""

    def __init__(
        self,
        path_resolver: PathResolver,
        settings_store: SettingsStore,
        workspace_store: WorkspaceStore,
        config: Config,
    ):
        self.path_resolver = path_resolver
        self.settings_store = settings_store
        self.workspace_store = workspace_store
        self.config = config
