# -*- coding: utf-8 -*-
"""
配置管理模块
负责读写程序设置、会话状态等
支持方案A：在程序目录保存user_data_path.txt记住用户数据路径

v1.5.4 改动：
  - 新增 editor.show_minimap 默认值
  - 新增 editor.auto_minimap：勾选时仅代码文件显示缩略图
"""

import os
import json
from datetime import datetime
from typing import Optional, Dict, Any, List

from src.utils.logger import get_logger
from src.utils.exceptions import safe_call
from src.security.path_validator import PathValidator, PathSecurityError
from src.security.file_guard import FileGuard, FileSizeExceededError, FileOperationTimeoutError
from src.security.crypto_manager import CryptoManager, DecryptionError
from src.security.input_validator import InputValidator, SettingValidationError


class Config:
    """配置管理类"""
    
    # 默认设置
    DEFAULT_SETTINGS = {
        "initialized": False,
        "base_path": "",
        "editor": {
            "font_family": "Microsoft YaHei",
            "font_size": 12,
            "line_spacing": 1.5,
            "show_line_numbers": True,
            "auto_wrap": False,
            "wrap_mode": "no_wrap",
            "highlight_current_line": True,
            "auto_save_interval": 30,
            "max_history_count": 40,
            "default_encoding": "utf-8",
            "line_ending": "LF",
            "code_highlight_theme": "pycharm_light",
            "show_minimap": True,
            "auto_minimap": False,
            "auto_pair_brackets": True,  # 括号/引号自动配对

        },
        "game": {
            "typing_reward_rate": 1.0,
            "idle_reward_rate": 1.0,
            "daily_typing_limit": 10000,
            "construction_time_rate": 1.0,
            "construction_slots": 2,
            "bauxite_counter": 0
        },
        "secretary": {
            "character_id": None,
            "character_name": None,
            "skin_name": None,
            "state": "正常",
            "user_nickname": "指挥官",
            "secretary_self": "我",
            "enable_voice": False,
            "show_secretary": True,
            "size_percent": 7
        },
        "view": {
            "theme": "light",
            "sidebar_width": 200,
            "show_file_tree": True
        },
        "window": {
            "width": 1200,
            "height": 800,
            "x": 100,
            "y": 100,
            "maximized": False
        },
        "shortcuts": {}
    }
    
    DEFAULT_WORKSPACE = {
        "last_session": {
            "open_files": [],
            "active_tab_index": 0,
            "current_view": "editor",
            "file_tree_state": {
                "expanded_folders": []
            }
        },
        "recent_files": [],
        "external_files": []
    }
    
    DEFAULT_SAVEGAME = {
        "resources": {
            "fuel": 3000,
            "ammo": 3000,
            "steel": 3000,
            "bauxite": 1000
        },
        "cores": 0,
        "last_login": None,
        "today_date": None,
        "today_chars_typed": 0,
        "total_chars_typed": 0,
        "total_documents": 0,
        "construction_queue": [],
        "owned_characters": {},
        "achievements": []
    }
    
    def __init__(self, app_dir: Optional[str] = None):
        """初始化配置管理器
        
        Args:
            app_dir: 程序所在目录
        """
        self._app_dir = app_dir or os.path.dirname(os.path.dirname(__file__))
        self._base_path = None
        self._settings: Dict[str, Any] = {}
        self._workspace: Dict[str, Any] = {}
        self._savegame: Dict[str, Any] = {}
        self._encryption_password: Optional[str] = None

        self._path_validator = PathValidator()
        self._input_validator = InputValidator()

        self._path_validator.add_allowed_root(self._app_dir)

        self._file_guard = FileGuard(
            path_validator=self._path_validator,
            max_file_size=10 * 1024 * 1024,
            timeout=15,
        )
        
        # 尝试加载用户数据路径
        self._load_user_data_path()
        
        if self._base_path:
            self._path_validator.add_allowed_root(self._base_path)

        self._crypto_manager = CryptoManager(self._get_config_dir())

        # 尝试加载配置
        self._load_all()
    
    def _get_user_data_path_file(self) -> str:
        """获取用户数据路径文件"""
        return os.path.join(self._app_dir, "user_data_path.txt")
    
    @safe_call(catch=Exception)
    def _load_user_data_path(self):
        """从user_data_path.txt加载用户数据路径"""
        path_file = self._get_user_data_path_file()
        if os.path.exists(path_file):
            with open(path_file, 'r', encoding='utf-8') as f:
                path = f.read().strip()
                if path and os.path.exists(path):
                    self._base_path = path
    
    @safe_call()
    def _save_user_data_path(self):
        """保存用户数据路径到user_data_path.txt"""
        if self._base_path:
            path_file = self._get_user_data_path_file()
            with open(path_file, 'w', encoding='utf-8') as f:
                f.write(self._base_path)
    
    def _get_config_dir(self) -> str:
        """获取配置目录路径（用户数据目录）"""
        if self._base_path:
            return os.path.join(self._base_path, "data", "config")
        return os.path.join(self._app_dir, "data", "config")
    
    def _get_gamedata_dir(self) -> str:
        """获取游戏数据目录路径（用户数据目录）"""
        if self._base_path:
            return os.path.join(self._base_path, "data", "gamedata")
        return os.path.join(self._app_dir, "data", "gamedata")
    
    def _load_json(self, filepath: str, default: Dict) -> Dict:
        """加载JSON文件，如果不存在则返回默认值"""
        if os.path.exists(filepath):
            try:
                content = self._file_guard.safe_read(filepath, validate_path=False)
                return json.loads(content)
            except (json.JSONDecodeError, IOError, FileSizeExceededError,
                    FileOperationTimeoutError, PathSecurityError) as e:
                get_logger(__name__).warning("加载配置文件失败: %s, 错误: %s", filepath, e)
                return default.copy()
        return default.copy()
    
    def _save_json(self, filepath: str, data: Dict):
        """保存JSON文件"""
        content = json.dumps(data, ensure_ascii=False, indent=2)
        self._file_guard.safe_write(filepath, content, validate_path=False)
    
    def _load_all(self):
        """加载所有配置文件"""
        config_dir = self._get_config_dir()
        gamedata_dir = self._get_gamedata_dir()
        
        # 加载设置
        settings_path = os.path.join(config_dir, "settings.json")
        self._settings = self._load_json(settings_path, self.DEFAULT_SETTINGS)
        
        # 如果设置中有base_path且当前没有，使用设置中的
        if not self._base_path and self._settings.get("base_path"):
            saved_path = self._settings["base_path"]
            if os.path.exists(saved_path):
                self._base_path = saved_path
                # 重新获取正确的目录
                config_dir = self._get_config_dir()
                gamedata_dir = self._get_gamedata_dir()
                # 重新加载设置
                settings_path = os.path.join(config_dir, "settings.json")
                self._settings = self._load_json(settings_path, self.DEFAULT_SETTINGS)
        
        # 加载工作区
        self._workspace = self._load_json(
            os.path.join(config_dir, "workspace.json"),
            self.DEFAULT_WORKSPACE
        )
        
        # 加载游戏存档
        if self._crypto_manager.is_encrypted():
            try:
                if self._encryption_password:
                    self._savegame = self._crypto_manager.decrypt_savegame(
                        self._encryption_password
                    )
                else:
                    self._savegame = self.DEFAULT_SAVEGAME.copy()
                    get_logger(__name__).info("存档已加密，需要密码才能解密")
            except DecryptionError as e:
                get_logger(__name__).warning("存档解密失败: %s", e)
                self._savegame = self.DEFAULT_SAVEGAME.copy()
        else:
            self._savegame = self._load_json(
                os.path.join(gamedata_dir, "savegame.json"),
                self.DEFAULT_SAVEGAME
            )
        
        # 合并默认值
        self._settings = self._merge_dict(self.DEFAULT_SETTINGS, self._settings)
        self._workspace = self._merge_dict(self.DEFAULT_WORKSPACE, self._workspace)
        self._savegame = self._merge_dict(self.DEFAULT_SAVEGAME, self._savegame)
    
    def _merge_dict(self, default: Dict, current: Dict) -> Dict:
        """递归合并字典"""
        result = default.copy()
        for key, value in current.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._merge_dict(result[key], value)
            else:
                result[key] = value
        return result
    
    def save(self):
        """保存所有配置"""
        self.save_settings()
        self.save_workspace()
        self.save_savegame()
        self._save_user_data_path()
    
    def save_settings(self):
        """保存设置"""
        config_dir = self._get_config_dir()
        os.makedirs(config_dir, exist_ok=True)
        self._save_json(os.path.join(config_dir, "settings.json"), self._settings)
        self._save_user_data_path()
    
    def save_workspace(self):
        """保存工作区状态"""
        config_dir = self._get_config_dir()
        os.makedirs(config_dir, exist_ok=True)
        self._save_json(os.path.join(config_dir, "workspace.json"), self._workspace)
    
    def save_savegame(self):
        """保存游戏存档"""
        gamedata_dir = self._get_gamedata_dir()
        os.makedirs(gamedata_dir, exist_ok=True)
        if self._encryption_password and self._crypto_manager.is_encrypted():
            try:
                self._crypto_manager.encrypt_savegame(
                    self._encryption_password, self._savegame
                )
            except Exception as e:
                get_logger(__name__).warning("存档加密保存失败，回退到明文: %s", e)
                self._save_json(
                    os.path.join(gamedata_dir, "savegame.json"), self._savegame
                )
        else:
            self._save_json(
                os.path.join(gamedata_dir, "savegame.json"), self._savegame
            )
    
    def get_base_path(self) -> str:
        """获取用户数据存储基础路径"""
        return self._base_path or self._app_dir
    
    def set_base_path(self, path: str):
        """设置用户数据存储路径"""
        self._settings["base_path"] = path
        self._base_path = path
        self._path_validator.add_allowed_root(path)
        self._save_user_data_path()
    
    def get_app_dir(self) -> str:
        """获取程序目录（代码和资源所在）"""
        return self._app_dir
    
    def get_notebooks_path(self) -> str:
        """获取笔记库路径（用户数据目录）"""
        return os.path.join(self.get_base_path(), "notebooks")
    
    def get_temp_path(self) -> str:
        """获取暂存目录路径（用户数据目录）"""
        return os.path.join(self.get_base_path(), "temp", "autosave")
    
    def get_assets_path(self) -> str:
        """获取资源目录路径（程序目录，不是用户数据目录！）"""
        return os.path.join(self._app_dir, "data", "assets")
    
    def get_portraits_path(self) -> str:
        """获取立绘目录路径"""
        return os.path.join(self.get_assets_path(), "portraits")
    
    def ensure_directories(self):
        """确保所有必要的目录存在（程序启动时调用）"""
        # 程序目录下的资源目录
        portraits = self.get_portraits_path()
        for subdir in ["原始/正常", "原始/大破", "皮肤/正常", "皮肤/大破"]:
            os.makedirs(os.path.join(portraits, subdir), exist_ok=True)
        
        # 用户数据目录
        base = self.get_base_path()
        for subdir in ["notebooks/工作", "notebooks/回忆", "notebooks/日记",
                        "data/config", "data/gamedata", "data/logs",
                        "temp/autosave"]:
            os.makedirs(os.path.join(base, subdir), exist_ok=True)
    
    # === 初始化状态 ===
    
    def is_initialized(self) -> bool:
        """检查是否已初始化"""
        if self._base_path and os.path.exists(self._base_path):
            settings_path = os.path.join(self._base_path, "data", "config", "settings.json")
            return os.path.exists(settings_path)
        return False
    
    def set_initialized(self, value: bool):
        """设置初始化状态"""
        self._settings["initialized"] = value
    
    # === 编辑器设置 ===
    
    def get_editor_setting(self, key: str, default=None):
        """获取编辑器设置"""
        return self._settings.get("editor", {}).get(key, default)
    
    def set_editor_setting(self, key: str, value):
        """设置编辑器配置"""
        if "editor" not in self._settings:
            self._settings["editor"] = {}
        self._settings["editor"][key] = value
    
    # === 游戏设置 ===
    
    def get_game_setting(self, key: str, default=None):
        """获取游戏设置"""
        return self._settings.get("game", {}).get(key, default)
    
    def set_game_setting(self, key: str, value):
        """设置游戏配置"""
        if "game" not in self._settings:
            self._settings["game"] = {}
        self._settings["game"][key] = value
    
    # === 小秘书设置 ===
    
    def get_secretary_setting(self, key: str, default=None):
        """获取小秘书设置"""
        return self._settings.get("secretary", {}).get(key, default)
    
    def set_secretary_setting(self, key: str, value):
        """设置小秘书配置"""
        if "secretary" not in self._settings:
            self._settings["secretary"] = {}
        self._settings["secretary"][key] = value
    
    # === 视图设置 ===
    
    def get_view_setting(self, key: str, default=None):
        """获取视图设置"""
        return self._settings.get("view", {}).get(key, default)
    
    def set_view_setting(self, key: str, value):
        """设置视图配置"""
        if "view" not in self._settings:
            self._settings["view"] = {}
        self._settings["view"][key] = value
    
    # === 窗口设置 ===
    
    def get_window_setting(self, key: str, default=None):
        """获取窗口设置"""
        return self._settings.get("window", {}).get(key, default)
    
    def set_window_setting(self, key: str, value):
        """设置窗口配置"""
        if "window" not in self._settings:
            self._settings["window"] = {}
        self._settings["window"][key] = value
    
    # === 通用设置 ===

    def get_setting(self, key: str, default=None):
        """获取设置项"""
        return self._settings.get(key, default)

    def set_setting(self, key: str, value):
        """设置配置项"""
        self._settings[key] = value

    # === 工作区状态 ===
    
    def get_workspace(self) -> Dict:
        """获取工作区状态"""
        return self._workspace
    
    def set_open_files(self, files: List[Dict]):
        """设置打开的文件列表"""
        self._workspace["last_session"]["open_files"] = files
    
    def get_open_files(self) -> List[Dict]:
        """获取打开的文件列表"""
        return self._workspace.get("last_session", {}).get("open_files", [])
    
    def set_active_tab_index(self, index: int):
        """设置当前激活的标签页索引"""
        self._workspace["last_session"]["active_tab_index"] = index
    
    def get_active_tab_index(self) -> int:
        """获取当前激活的标签页索引"""
        return self._workspace.get("last_session", {}).get("active_tab_index", 0)
    
    def set_current_view(self, view: str):
        """设置当前视图"""
        self._workspace["last_session"]["current_view"] = view
    
    def get_current_view(self) -> str:
        """获取当前视图"""
        return self._workspace.get("last_session", {}).get("current_view", "editor")
    
    def add_recent_file(self, filepath: str):
        """添加最近打开的文件"""
        recent = self._workspace.get("recent_files", [])
        if filepath in recent:
            recent.remove(filepath)
        recent.insert(0, filepath)
        self._workspace["recent_files"] = recent[:20]
    
    def get_recent_files(self) -> List[str]:
        """获取最近打开的文件列表"""
        return self._workspace.get("recent_files", [])
    
    def get_external_files(self) -> List[str]:
        """获取外部文件列表"""
        return self._workspace.get("external_files", [])
    
    def add_external_file(self, filepath: str):
        """添加外部文件"""
        if "external_files" not in self._workspace:
            self._workspace["external_files"] = []
        external = self._workspace["external_files"]
        if filepath not in external:
            external.append(filepath)
            self.save_workspace()
    
    def remove_external_file(self, filepath: str):
        """移除外部文件"""
        external = self._workspace.get("external_files", [])
        if filepath in external:
            external.remove(filepath)
            self.save_workspace()
    
    # === 游戏存档 ===
    
    def get_savegame(self) -> Dict:
        """获取游戏存档"""
        return self._savegame
    
    def get_resources(self) -> Dict[str, int]:
        """获取资源"""
        return self._savegame.get("resources", {
            "fuel": 0, "ammo": 0, "steel": 0, "bauxite": 0
        })
    
    def set_resources(self, resources: Dict[str, int]):
        """设置资源"""
        self._savegame["resources"] = resources
    
    def add_resource(self, resource_type: str, amount: int):
        """增加资源"""
        if "resources" not in self._savegame:
            self._savegame["resources"] = {"fuel": 0, "ammo": 0, "steel": 0, "bauxite": 0}
        current = self._savegame["resources"].get(resource_type, 0)
        self._savegame["resources"][resource_type] = max(0, current + amount)
    
    def get_cores(self) -> int:
        """获取核心数量"""
        return self._savegame.get("cores", 0)
    
    def set_cores(self, amount: int):
        """设置核心数量"""
        self._savegame["cores"] = max(0, amount)
    
    def add_cores(self, amount: int):
        """增加核心"""
        current = self.get_cores()
        self.set_cores(current + amount)
    
    def get_today_chars_typed(self) -> int:
        """获取今日打字数"""
        today = datetime.now().strftime("%Y-%m-%d")
        saved_date = self._savegame.get("today_date")
        if saved_date != today:
            self._savegame["today_date"] = today
            self._savegame["today_chars_typed"] = 0
        return self._savegame.get("today_chars_typed", 0)
    
    def add_chars_typed(self, count: int):
        """增加打字数"""
        self.get_today_chars_typed()
        self._savegame["today_chars_typed"] = self._savegame.get("today_chars_typed", 0) + count
        self._savegame["total_chars_typed"] = self._savegame.get("total_chars_typed", 0) + count
    
    def get_total_documents(self) -> int:
        """获取文档总数"""
        return self._savegame.get("total_documents", 0)
    
    def set_total_documents(self, count: int):
        """设置文档总数"""
        self._savegame["total_documents"] = count
    
    def update_last_login(self):
        """更新最后登录时间"""
        self._savegame["last_login"] = datetime.now().isoformat()
    
    def get_last_login(self) -> Optional[str]:
        """获取最后登录时间"""
        return self._savegame.get("last_login")

    # === 安全模块接口 ===

    def get_path_validator(self) -> PathValidator:
        """获取路径验证器"""
        return self._path_validator

    def get_file_guard(self) -> FileGuard:
        """获取文件安全守卫"""
        return self._file_guard

    def get_input_validator(self) -> InputValidator:
        """获取输入验证器"""
        return self._input_validator

    def is_savegame_encrypted(self) -> bool:
        """检查存档是否已加密"""
        return self._crypto_manager.is_encrypted()

    def set_encryption_password(self, password: str) -> None:
        """设置加密密码"""
        self._encryption_password = password

    def has_encryption_password(self) -> bool:
        """检查是否已设置加密密码"""
        return self._encryption_password is not None

    def enable_encryption(self, password: str) -> bool:
        """启用存档加密

        Args:
            password: 加密密码

        Returns:
            是否成功启用加密
        """
        try:
            self._crypto_manager.migrate_to_encrypted(password)
            self._encryption_password = password
            get_logger(__name__).info("存档加密已启用")
            return True
        except Exception as e:
            get_logger(__name__).error("启用存档加密失败: %s", e)
            return False

    def disable_encryption(self, password: str) -> bool:
        """禁用存档加密

        Args:
            password: 当前加密密码

        Returns:
            是否成功禁用加密
        """
        try:
            self._crypto_manager.migrate_to_plaintext(password)
            self._encryption_password = None
            get_logger(__name__).info("存档加密已禁用")
            return True
        except Exception as e:
            get_logger(__name__).error("禁用存档加密失败: %s", e)
            return False

    def verify_encryption_password(self, password: str) -> bool:
        """验证加密密码是否正确"""
        return self._crypto_manager.verify_password(password)

    def validate_setting_value(
        self,
        key: str,
        value: Any,
        expected_type: type,
        min_val=None,
        max_val=None,
        allowed_values=None,
    ) -> Any:
        """验证设置值"""
        return self._input_validator.validate_setting(
            key, value, expected_type,
            min_val=min_val,
            max_val=max_val,
            allowed_values=allowed_values,
        )
