"""砂案のモデル・画像・見積を作る。

    blender -b --python 計画/砂/build.py
"""
import pathlib
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent / "共通"))
import shooting  # noqa: E402

shooting.build("砂")
