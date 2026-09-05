"""
Legacy services package.

Do not eagerly import optional translator/runtime modules here.
Some legacy modules depend on optional providers and outdated exceptions,
which should not break unrelated imports such as scheduler bootstrap.
"""

__all__: list[str] = []
