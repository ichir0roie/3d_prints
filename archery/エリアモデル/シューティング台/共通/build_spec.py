"""共通/仕様.blend(エリアの範囲・地盤・人の大きさ)と 仕様.png を作る。

    blender -b --python 共通/build_spec.py
"""
import pathlib
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import shooting  # noqa: E402

shooting.build_spec()
