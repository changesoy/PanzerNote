# -*- coding: utf-8 -*-
import logging
import os
import tempfile

from src.utils.logger import setup_logging, get_logger


class TestSetupLogging:
    def test_default_initialization(self):
        setup_logging()
        logger = get_logger("test_default")
        assert logger.name == "src.test_default"

    def test_console_only(self):
        setup_logging()
        root = logging.getLogger("src")
        handler_types = [type(h).__name__ for h in root.handlers]
        assert "StreamHandler" in handler_types

    def test_file_logging(self):
        import src.utils.logger as logger_mod
        logger_mod._initialized = False
        root = logging.getLogger("src")
        for h in root.handlers[:]:
            h.close()
            root.removeHandler(h)

        tmpdir = tempfile.mkdtemp()
        try:
            setup_logging(log_dir=tmpdir)
            logger = get_logger("test_file")
            logger.info("test file log message")

            log_file = os.path.join(tmpdir, "panzernote.log")
            assert os.path.exists(log_file)
        finally:
            for h in root.handlers[:]:
                h.close()
                root.removeHandler(h)
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_get_logger_auto_prefix(self):
        logger = get_logger("mymodule")
        assert logger.name == "src.mymodule"

    def test_get_logger_no_double_prefix(self):
        logger = get_logger("src.mymodule")
        assert logger.name == "src.mymodule"

    def test_idempotent_setup(self):
        import src.utils.logger as logger_mod
        logger_mod._initialized = True
        root = logging.getLogger("src")
        handler_count_before = len(root.handlers)

        setup_logging()
        assert len(root.handlers) == handler_count_before
