# -*- coding: utf-8 -*-
"""
文件访问上下文枚举

定义文件读写的访问上下文，替代模糊的 validate_path=False，
为每个文件操作提供明确的语义来源。
"""

from enum import Enum


class FileAccessContext(Enum):
    USER_DOCUMENT_READ = "user_document_read"
    USER_DOCUMENT_SAVE = "user_document_save"
    TEMP_AUTOSAVE = "temp_autosave"
    INTERNAL_CONFIG = "internal_config"
    INTERNAL_SAVEGAME = "internal_savegame"
    PLUGIN_REQUEST = "plugin_request"
    SESSION_RESTORE = "session_restore"
    SETTINGS_IMPORT = "settings_import"
    EXPORT_TARGET = "export_target"
