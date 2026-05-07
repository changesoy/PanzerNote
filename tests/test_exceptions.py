# -*- coding: utf-8 -*-
from src.utils.exceptions import safe_call


class TestSafeCall:
    def test_normal_execution(self):
        @safe_call()
        def add(a: int, b: int) -> int:
            return a + b

        assert add(1, 2) == 3

    def test_exception_returns_default(self):
        @safe_call(default=-1)
        def failing() -> int:
            raise ValueError("boom")

        assert failing() == -1

    def test_default_none(self):
        @safe_call()
        def failing():
            raise RuntimeError("fail")

        assert failing() is None

    def test_reraise(self):
        @safe_call(reraise=True)
        def failing():
            raise ValueError("reraise this")

        try:
            failing()
            assert False, "Should have raised"
        except ValueError as e:
            assert "reraise this" in str(e)

    def test_catch_specific(self):
        @safe_call(catch=ValueError, default="caught")
        def raise_type_error():
            raise TypeError("wrong type")

        try:
            result = raise_type_error()
            assert False, "Should have raised TypeError"
        except TypeError:
            pass

    def test_catch_specific_match(self):
        @safe_call(catch=ValueError, default="caught")
        def raise_value_error():
            raise ValueError("expected")

        assert raise_value_error() == "caught"

    def test_preserves_function_name(self):
        @safe_call()
        def my_func():
            pass

        assert my_func.__name__ == "my_func"

    def test_log_level_warning(self):
        @safe_call(log_level="warning", default=0)
        def failing():
            raise RuntimeError("warn level")

        assert failing() == 0
