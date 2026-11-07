"""シューティング台 4 案のモデル作成と見積。

    python3 共通/shooting.py              各案の 見積.md と 共通/見積まとめ.md を書く
    blender -b --python 共通/build_spec.py  共通/仕様.blend と 仕様.png を作る
    blender -b --python 計画/<案>/build.py  その案の .blend・画像・見積.md を作る

座標: x が横(W)、y が縦(D)、z が上。地面は z=0。単位は m。
寸法・単価を変えるときは、このファイルの SPEC・SIZES・PRICES を直して作り直す。
"""

import functools
import math
import pathlib
from collections import OrderedDict

ROOT = pathlib.Path(__file__).resolve().parent.parent
COMMON = ROOT / "共通"
PLAN_DIR = ROOT / "計画"

# 標準サイズ(モデルと画像はこの寸法で作る)。範囲は横 7〜10m、縦 2〜3m。
SPEC = {"W": 8.0, "D": 2.5}
# 標準サイズを案ごとに変えるもの
PLAN_SIZE = {"パイプ台": (10.0, 2.5)}
# 見積を出すサイズ(最小・標準・最大)
SIZES = [(7.0, 2.0), (8.0, 2.5), (10.0, 3.0)]

# 税込単価。(単価, 単位, 定尺 m または None, 根拠)
# 根拠が「写真」のものは 共通/AmazonPhotos の値札(2026-11-07)。「仮」は写真に無く仮置き。
PRICES = {
    "単管パイプ φ48.6×1.8×4000": (2508, "本", 4.0, "写真"),
    "パイプ杭 φ48.6×1500": (1958, "本", None, "写真"),
    "単管打込みキャップ 先端": (276, "個", None, "仮: 通販 ナフコ(アラオ製)"),
    "兼用自在クランプ 48.6/42.7": (382, "個", None, "写真"),
    "単管ジョイント": (520, "個", None, "仮: 通販 470〜499円(税別)"),
    "根太止め金具(単管-木材)": (330, "個", None, "仮"),
    "赤松 乾燥材 60×60×2985": (2178, "本", 2.985, "写真"),
    "防腐加工 角材 90×90×3000": (4928, "本", 3.0, "写真"),
    "SPF 2×6 38×140×3650": (4928, "本", 3.65, "写真"),
    "重量ブロックC 390×150×190": (305, "個", None, "写真"),
    "砕石 20kg": (260, "袋", None, "仮: コメリ 238円・ナフコ 428円"),
    "砂 20kg": (330, "袋", None, "仮"),
    "透水シート 1m×10m": (1980, "巻", None, "仮"),
    "有孔管(暗渠管) φ50×4m": (1650, "本", 4.0, "仮"),
    "コーススレッド 75mm": (4, "本", None, "仮: 箱買いの1本あたり"),
}

PIPE_KG_PER_M = 2.08          # 単管 φ48.6×1.8
PILE_KG = 3.94                # パイプ杭 1本(値札)
GRAVEL_T_PER_M3 = 1.6         # 砕石のかさ密度(締固め前)
SAND_T_PER_M3 = 1.6           # 砂のかさ密度(湿り)
BAG_KG = 20
JOIST_PITCH = 0.455           # 根太の間隔
BOARD_W, BOARD_T, BOARD_GAP = 0.140, 0.038, 0.005
KERF = 0.003                  # のこ刃の厚み
PIPE_D = 0.0486

PLANS = OrderedDict([
    ("パイプ台", "単管を切った杭(先端キャップ付き)と単管の梁に、赤松の根太と 2×6 の床板を張る台。射手が 1m おきに立ち、後ろに荷物を置いても持つ杭の配置"),
    ("排水作戦", "溝を掘って暗渠管と砕石を入れ、端の浸透ますへ水を逃がす"),
    ("ブロック", "砕石を敷き、ブロックを並べて防腐角材の根太と 2×6 の床板を張る"),
    ("砂", "透水シートの上に砂を 10cm 敷いて嵩上げし、周りをブロックで留める"),
])


# ---------------------------------------------------------------- 部品と計算

def box(group, mat, p0, p1):
    return ("box", group, mat, tuple(p0), tuple(p1))


def cyl(group, mat, axis, p0, length, r):
    return ("cyl", group, mat, axis, tuple(p0), length, r)


def cone_down(group, mat, base, h, r):
    """base を底面の中心にして、下向きに尖る円錐。"""
    return ("cone", group, mat, tuple(base), h, r)


def plan_size(name):
    return PLAN_SIZE.get(name, (SPEC["W"], SPEC["D"]))


def spaced(a, b, max_span):
    """a から b までを max_span 以下の等間隔で区切った位置。"""
    n = max(1, math.ceil((b - a) / max_span - 1e-9))
    return [a + i * (b - a) / n for i in range(n + 1)]


def split_len(total, stock):
    """total を定尺 stock で切り出す長さの並び(端数は最後)。"""
    segs = []
    while total > stock + 1e-9:
        segs.append(stock)
        total -= stock
    segs.append(total)
    return segs


def cut_stock(pieces, stock):
    """大きい順に詰める切り出し計算。戻り値は定尺の本数と、各本の切り出し長さ。"""
    bins = []
    for p in sorted(pieces, reverse=True):
        if p > stock + 1e-9:
            raise ValueError(f"{p:.3f}m は定尺 {stock}m より長い")
        for b in bins:
            need = p + (KERF if b else 0)
            if stock - sum(b) - KERF * (len(b) - 1 if b else 0) >= need - 1e-9:
                b.append(p)
                break
        else:
            bins.append([p])
    return len(bins), bins


def deck(W, D, z0, sec, joist_key, parts):
    """根太(y 向き)と 2×6 床板(x 向き)。z0 は根太の下端。"""
    n = math.ceil((W - sec) / JOIST_PITCH - 1e-9)
    xs = [sec / 2 + i * (W - sec) / n for i in range(n + 1)]
    jl = D - 0.02
    for x in xs:
        parts.append(box("根太", "treated" if "防腐" in joist_key else "pine",
                         (x - sec / 2, 0.01, z0), (x + sec / 2, 0.01 + jl, z0 + sec)))
    z1 = z0 + sec
    pieces, y, row = [], 0.0, 0
    stock = PRICES["SPF 2×6 38×140×3650"][2]
    while y < D - 1e-6:
        w = min(BOARD_W, D - y)
        start, first = 0.0, True
        while start < W - 1e-6:
            lim = start + (stock / 2 if (first and row % 2) else stock)
            end = W if lim >= W - 1e-9 else max(x for x in xs if start < x <= lim)
            parts.append(box("床板", "spf", (start, y, z1), (end, y + w, z1 + BOARD_T)))
            pieces.append(end - start)
            start, first = end, False
        y += BOARD_W + BOARD_GAP
        row += 1
    splices = len(pieces) - row
    return {
        "xs": xs, "rows": row, "joist_pieces": [jl] * len(xs), "board_pieces": pieces,
        "screws": 2 * row * len(xs) + 2 * splices,
        "top": z1 + BOARD_T,
        "wood_m3": sec * sec * jl * len(xs) + BOARD_T * sum(
            min(BOARD_W, D - i * (BOARD_W + BOARD_GAP)) for i in range(row)) * W,
    }


def stock_row(key, pieces):
    stock = PRICES[key][2]
    n, bins = cut_stock(pieces, stock)
    waste = n * stock - sum(pieces)
    lens = OrderedDict()
    for p in sorted(pieces, reverse=True):
        k = f"{p:.2f}m"
        lens[k] = lens.get(k, 0) + 1
    note = "切り出し " + "・".join(f"{k}×{v}" for k, v in lens.items()) + f"(端材 {waste:.1f}m)"
    return (key, n, note)


def bags(m3, t_per_m3):
    return math.ceil(m3 * t_per_m3 * 1000 / BAG_KG)


# ---------------------------------------------------------------- 4 案

def plan_pipe(W, D, pile="単管", cols=None, rows=None):
    """pile: "既製" はパイプ杭を買う。"単管" は単管を切って先端キャップを付ける。
    cols・rows: 杭の列数・行数。None なら間隔 1.8m・1.25m 以下になるように決める。"""
    parts, bom = [], []
    r = PIPE_D / 2
    xs = spaced(0.15, W - 0.15, 1.8 if cols is None else (W - 0.3) / (cols - 1))
    ys = spaced(0.15, D - 0.15, 1.25 if rows is None else (D - 0.3) / (rows - 1))
    z_top, z_beam, z_cross, L = 0.29, 0.26, 0.16, 1.5
    for x in xs:
        for y in ys:
            parts.append(cyl("杭", "steel", "z", (x, y, z_top - L), L, r))
            if pile == "単管":
                parts.append(cone_down("杭の先端キャップ", "clamp", (x, y, z_top - L), 0.09, r + 0.004))
            parts.append(box("クランプ", "clamp", (x - 0.037, y - 0.01, z_beam - 0.035),
                             (x + 0.037, y + PIPE_D + 0.01, z_beam + 0.035)))
            parts.append(box("クランプ", "clamp", (x - 0.01, y - 0.037, z_cross - 0.035),
                             (x + PIPE_D + 0.01, y + 0.037, z_cross + 0.035)))
    pipe, joints = [], 0
    for y in ys:
        x = 0.05
        segs = split_len(W - 0.1, 4.0)
        for s in segs:
            parts.append(cyl("梁(単管)", "steel", "x", (x, y + PIPE_D, z_beam), s, r))
            x += s
        pipe += segs
        joints += len(segs) - 1
    for x in xs:
        parts.append(cyl("つなぎ(単管)", "steel", "y", (x + PIPE_D, 0.05, z_cross), D - 0.1, r))
        pipe.append(D - 0.1)
    d = deck(W, D, z_beam + r, 0.06, "赤松 乾燥材 60×60×2985", parts)
    n_pile = len(xs) * len(ys)
    where = f"{len(xs)}列×{len(ys)}行、地中 {L - z_top:.2f}m 打ち込み"
    if pile == "単管":
        pipe += [L] * n_pile
        bom.append(("単管打込みキャップ 先端", n_pile, "杭1本に1個。" + where))
        steel = sum(pipe) * PIPE_KG_PER_M
    else:
        bom.append(("パイプ杭 φ48.6×1500", n_pile, where))
        steel = sum(pipe) * PIPE_KG_PER_M + n_pile * PILE_KG
    cuts = sum(1 for x in pipe if x < 4.0 - 1e-6)
    bom += [
        stock_row("単管パイプ φ48.6×1.8×4000", pipe),
        ("兼用自在クランプ 48.6/42.7", 2 * n_pile, "杭と梁・杭とつなぎの交点"),
        ("単管ジョイント", joints, "梁の継ぎ"),
        ("根太止め金具(単管-木材)", len(d["xs"]) * len(ys), "根太と梁の交点"),
        stock_row("赤松 乾燥材 60×60×2985", d["joist_pieces"]),
        stock_row("SPF 2×6 38×140×3650", d["board_pieces"]),
        ("コーススレッド 75mm", d["screws"], "床板1枚・根太1本あたり2本"),
    ]
    q = OrderedDict([
        ("鉄(単管+杭)", f"{steel:.0f} kg"),
        ("単管の切断", f"{cuts} か所"),
        ("木材(使う分の体積)", f"{d['wood_m3']:.2f} m³"),
        ("床の高さ", f"{d['top']:.2f} m"),
    ])
    notes = [
        "杭は地中に約1.2m打ち込む前提。地盤が柔らかいと沈む・傾く。",
        "赤松・SPF は屋外で腐りやすい。防腐塗料(未計上)を塗るか、床板をウッドデッキ材に替える。",
        "単管の切断はホームセンターのカットサービス(料金未計上)を使う前提。",
    ]
    if pile == "単管":
        notes.insert(0, "杭は単管を 1.5m に切り、先端に打込みキャップを付けて打ち込む。単管は肉厚 1.8mm で、"
                        "既製のパイプ杭(1.5m で 3.94kg)より軽い(約 3.1kg)。硬い地盤だと頭が潰れやすいので、"
                        "打つときは頭に当て木をする。")
    else:
        notes.insert(0, "杭は既製のパイプ杭(1.5m、3.94kg)を買って打ち込む。単管より重く、先が尖っていて打ち込みやすい。")
    z_joist = z_beam + r
    views = [("断面X", "x", xs[len(xs) // 2] + 0.003, "杭の列で切り、横(x 方向)から見る"),
             ("断面Y", "y", ys[len(ys) // 2] + 0.003, "真ん中の杭の行で切り、前(y 方向)から見る"),
             ("断面Z", "z", z_joist + 0.03, "根太の高さで切って床板を外し、上から見る")]
    return dict(parts=parts, bom=bom, q=q, notes=notes, xs=xs, ys=ys, views=views, glass=True)


def plan_drain(W, D):
    parts, bom = [], []
    yc, tw, td = D / 2, 0.3, 0.5          # 溝の中心・幅・深さ
    pit, pd = 0.6, 1.0                    # 浸透ますの辺・深さ
    tl = W + 0.2
    parts.append(box("砕石(溝)", "gravel", (0, yc - tw / 2, -td), (tl, yc + tw / 2, 0.005)))
    parts.append(box("砕石(浸透ます)", "gravel", (tl, yc - pit / 2, -pd), (tl + pit, yc + pit / 2, 0.005)))
    t = 0.004
    parts.append(box("透水シート", "sheet", (0, yc - tw / 2 - t, -td - t), (tl, yc - tw / 2, 0.006)))
    parts.append(box("透水シート", "sheet", (0, yc + tw / 2, -td - t), (tl, yc + tw / 2 + t, 0.006)))
    parts.append(box("透水シート", "sheet", (0, yc - tw / 2, -td - t), (tl, yc + tw / 2, -td)))
    pipe_len = tl + pit / 2
    parts.append(cyl("有孔管", "pvc", "x", (0, yc, -td + 0.08), pipe_len, 0.03))
    v_trench = tw * td * tl
    v_pit = pit * pit * pd
    v = v_trench + v_pit
    sheet = (2 * td + 2 * tw) * tl + (4 * pit * pd + 2 * pit * pit)
    bom += [
        ("砕石 20kg", bags(v, GRAVEL_T_PER_M3), f"{v:.2f} m³ × {GRAVEL_T_PER_M3} t/m³"),
        ("透水シート 1m×10m", math.ceil(sheet * 1.1 / 10), f"{sheet:.1f} m² + 重ね代1割"),
        stock_row("有孔管(暗渠管) φ50×4m", split_len(pipe_len, 4.0)),
    ]
    q = OrderedDict([
        ("掘削・残土", f"{v:.2f} m³(約 {v * 1.8:.1f} t)"),
        ("砕石", f"{v:.2f} m³(約 {v * GRAVEL_T_PER_M3:.1f} t)"),
        ("溝", f"幅 {tw}m × 深さ {td}m × 長さ {tl:.1f}m"),
        ("浸透ます", f"{pit}m 角 × 深さ {pd}m(エリアの右端の外)"),
    ])
    notes = [
        "台は作らず、地面の水はけだけを良くする案。上に床が要るなら他の案と組み合わせる。",
        "地面を溝に向けて少し勾配を付ける前提(作業のみ)。粘土質で地下に浸みない土だと、浸透ますが溢れて効かない。",
        "掘った土(残土)の処分費は未計上。砕石は量が多いので、袋より業者のバラ配達が安いことがある。",
    ]
    return dict(parts=parts, bom=bom, q=q, notes=notes, views=[("断面", "x", W / 2, "")])


def plan_block(W, D):
    parts, bom = [], []
    gt = 0.05
    parts.append(box("砕石", "gravel", (-0.1, -0.1, -gt), (W + 0.1, D + 0.1, 0.003)))
    bh = 0.19
    d = deck(W, D, 0.003 + bh, 0.09, "防腐加工 角材 90×90×3000", parts)
    ys = spaced(0.205, D - 0.205, 1.2)
    for x in d["xs"]:
        for y in ys:
            parts.append(box("ブロック", "block", (x - 0.075, y - 0.195, 0.003),
                             (x + 0.075, y + 0.195, 0.003 + bh)))
    v = (W + 0.2) * (D + 0.2) * gt
    nb = len(d["xs"]) * len(ys)
    bom += [
        ("砕石 20kg", bags(v, GRAVEL_T_PER_M3), f"厚さ {gt * 100:.0f}cm、{v:.2f} m³"),
        ("重量ブロックC 390×150×190", nb, f"根太1本に {len(ys)} 個"),
        stock_row("防腐加工 角材 90×90×3000", d["joist_pieces"]),
        stock_row("SPF 2×6 38×140×3650", d["board_pieces"]),
        ("コーススレッド 75mm", d["screws"], "床板1枚・根太1本あたり2本"),
    ]
    q = OrderedDict([
        ("砕石", f"{v:.2f} m³(約 {v * GRAVEL_T_PER_M3:.1f} t)"),
        ("ブロック", f"{nb} 個(約 {nb * 14} kg)"),
        ("木材(使う分の体積)", f"{d['wood_m3']:.2f} m³"),
        ("掘削・すき取り", f"{v:.2f} m³"),
        ("床の高さ", f"{d['top']:.2f} m"),
    ])
    notes = [
        "地面を 5cm すき取って砕石を敷き、ブロックを水平に据える前提。ブロックと根太は固定しない置き基礎。",
        "根太は地面に近いので防腐材にした。赤松 60×60 にすると根太代は半分以下になるが、腐りやすい。",
        "床板の SPF は屋外で腐りやすい。防腐塗料は未計上。",
    ]
    return dict(parts=parts, bom=bom, q=q, notes=notes, views=[("断面", "x", d["xs"][len(d["xs"]) // 2], "")])


def plan_sand(W, D):
    parts, bom = [], []
    st = 0.10
    parts.append(box("透水シート", "sheet", (0, 0, 0.001), (W, D, 0.004)))
    parts.append(box("砂", "sand", (0, 0, 0.004), (W, D, st)))
    bl, bw, bh = 0.39, 0.19, 0.15    # ブロックを寝かせて使う
    z0 = st - bh
    nx = math.ceil((W + 2 * bw) / bl - 1e-9)
    ny = math.ceil(D / bl - 1e-9)
    for i in range(nx):
        x = -bw + i * bl
        x1 = min(x + bl, W + bw)
        parts.append(box("縁ブロック", "block", (x, -bw, z0), (x1, 0, st)))
        parts.append(box("縁ブロック", "block", (x, D, z0), (x1, D + bw, st)))
    for j in range(ny):
        y = j * bl
        y1 = min(y + bl, D)
        parts.append(box("縁ブロック", "block", (-bw, y, z0), (0, y1, st)))
        parts.append(box("縁ブロック", "block", (W, y, z0), (W + bw, y1, st)))
    v = W * D * st
    nb = 2 * nx + 2 * ny
    bom += [
        ("砂 20kg", bags(v, SAND_T_PER_M3), f"厚さ {st * 100:.0f}cm、{v:.2f} m³"),
        ("透水シート 1m×10m", math.ceil(W * D * 1.1 / 10), f"{W * D:.1f} m² + 重ね代1割"),
        ("重量ブロックC 390×150×190", nb, "寝かせて周囲を囲う"),
    ]
    q = OrderedDict([
        ("砂", f"{v:.2f} m³(約 {v * SAND_T_PER_M3:.1f} t)"),
        ("ブロック", f"{nb} 個(約 {nb * 14} kg)"),
        ("掘削(ブロックの据え付け)", f"{2 * (W + D) * bw * 0.05:.2f} m³"),
        ("仕上がり高さ", f"{st:.2f} m"),
    ])
    notes = [
        "床は作らず、砂で 10cm 嵩上げして水たまりを避ける案。雨で砂が締まって減るので、たまに足す。",
        "砂は量が多く、袋で買うと重い。業者のバラ配達(料金未調査)の方が安くて楽なことがある。",
        "シートは泥と砂が混ざるのを防ぐ。地面自体の水はけが悪いと、砂の下に水が溜まる。",
    ]
    return dict(parts=parts, bom=bom, q=q, notes=notes, views=[("断面", "x", W / 2, "")])


# ---------------------------------------------------------------- パイプ台の強さ

DEAD = 0.3          # kN/m² 床板と根太の重さ(全面)
# 荷重の場合。射手: 前の帯に射手が 1m おきに立ち、後ろは荷物置き場。床いっぱい: 全面に人が乗る。
LOADS = OrderedDict([
    ("射手", dict(front=1.0, person=0.8, stand=(0.2, 0.8), luggage=1.0, live=0.0)),
    ("床いっぱい", dict(front=0.0, person=0.0, stand=(0.2, 0.8), luggage=0.0, live=1.8)),
])
DESIGN_LOAD = "射手"
PERSON_JOISTS = 2   # 射手1人の重さを受ける根太の本数(床板が2本以上にまたがる)
PIPE_I = math.pi / 64 * (48.6**4 - 45.0**4)      # mm⁴ 単管 φ48.6×1.8
PIPE_Z = PIPE_I / 24.3
STEEL_E, STEEL_FB = 205000, 355 / 1.5            # N/mm² STK500 相当の長期許容曲げ
WOOD_E, WOOD_FB = 8000, 26.4 * 1.1 / 3           # N/mm² 赤松 無等級の長期許容曲げ
JOIST_I, JOIST_Z = 60**4 / 12, 60**3 / 6         # 赤松 60×60
CLAMP_KN = 2.45     # kN 自在クランプ1個で支える許容(一般的な値。買う品で確かめる)
DEFL = 300          # たわみの限度 L/300


def cont_reactions(sup, loads):
    """支点 sup(昇順)に載る多径間の連続梁で、点荷重 loads=[(位置, 力)] の各支点の反力。三連モーメント式。"""
    n = len(sup)
    Ls = [sup[i + 1] - sup[i] for i in range(n - 1)]

    def span_of(y):
        for i in range(n - 1):
            if y <= sup[i + 1] + 1e-12:
                return i
        return n - 2

    T = [[0.0, 0.0] for _ in Ls]   # 各径間の左支点側・右支点側の荷重項
    for y, P in loads:
        i = span_of(y)
        a = y - sup[i]
        b = Ls[i] - a
        T[i][1] += P * a * (Ls[i] ** 2 - a * a) / Ls[i]
        T[i][0] += P * b * (Ls[i] ** 2 - b * b) / Ls[i]
    m = n - 2
    A = [[0.0] * m for _ in range(m)]
    rhs = [0.0] * m
    for i in range(m):
        if i > 0:
            A[i][i - 1] = Ls[i]
        A[i][i] = 2 * (Ls[i] + Ls[i + 1])
        if i < m - 1:
            A[i][i + 1] = Ls[i + 1]
        rhs[i] = -(T[i][1] + T[i + 1][0])
    for i in range(m):
        for j in range(i + 1, m):
            f = A[j][i] / A[i][i]
            A[j] = [x - f * y for x, y in zip(A[j], A[i])]
            rhs[j] -= f * rhs[i]
    M = [0.0] * m
    for i in reversed(range(m)):
        M[i] = (rhs[i] - sum(A[i][k] * M[k] for k in range(i + 1, m))) / A[i][i]
    M = [0.0] + M + [0.0]
    R = [0.0] * n
    for y, P in loads:
        i = span_of(y)
        R[i] += P * (sup[i + 1] - y) / Ls[i]
        R[i + 1] += P * (y - sup[i]) / Ls[i]
    for i, L in enumerate(Ls):
        d = (M[i + 1] - M[i]) / L      # 支点モーメント(負が上に凸)による反力の増減
        R[i] += d
        R[i + 1] -= d
    return R


def _strip(a, b, q, step=0.005):
    return [(a + (i + 0.5) * step, q * step) for i in range(max(0, int(round((b - a) / step))))]


def pipe_check(W, D, cols=None, rows=None, case=DESIGN_LOAD):
    """梁(単管)・根太・クランプの確かめ。比は 1 以下なら合格。
    梁と根太は単純梁で曲げとたわみを出す(安全側)。各梁への荷重の分かれ方だけ、根太を連続梁として解く。"""
    c = LOADS[case]
    p = plan_pipe(W, D, cols=cols, rows=rows)
    xs, ys = p["xs"], p["ys"]
    sp, rs = xs[1] - xs[0], ys[1] - ys[0]
    clamp = lambda y: min(max(y, ys[0]), ys[-1])  # 張り出し部分の荷重は端の梁に寄せる
    # 根太1本(幅 JOIST_PITCH)あたりの分布荷重 → 各梁の線荷重 kN/m
    uni = (_strip(0, D, (DEAD + c["live"]) * JOIST_PITCH)
           + _strip(c["front"], D, c["luggage"] * JOIST_PITCH))
    w_rows = [r / JOIST_PITCH for r in cont_reactions(ys, [(clamp(y), f) for y, f in uni])]
    # 射手1人が各梁へ行く割合(立つ位置を前の帯の中で動かした最大)
    share = [0.0] * len(ys)
    if c["person"]:
        lo, hi = c["stand"]
        for k in range(13):
            y = lo + (hi - lo) * k / 12
            share = [max(f, r) for f, r in zip(share, cont_reactions(ys, [(clamp(y), 1.0)]))]
    bL = sp * 1000
    bsig = bdl = R = 0.0
    for w, f in zip(w_rows, share):
        P = f * c["person"] * 1000                  # N。人は梁の真ん中に立つ
        bsig = max(bsig, (w * bL**2 / 8 + P * bL / 4) / PIPE_Z / STEEL_FB)
        bdl = max(bdl, (5 * w * bL**4 / 384 + P * bL**3 / 48) / (STEEL_E * PIPE_I) / (bL / DEFL))
        R = max(R, w * sp + f * c["person"])         # 人は杭の真上に立つ
    jL = rs * 1000
    jw = (DEAD + c["live"] + c["luggage"]) * JOIST_PITCH
    jP = c["person"] * 1000 / PERSON_JOISTS
    return OrderedDict([
        ("配置", f"{len(xs)}×{len(ys)}"), ("杭", len(xs) * len(ys)),
        ("間隔", f"{sp:.2f}m × {rs:.2f}m"),
        ("梁の曲げ", bsig), ("梁のたわみ", bdl),
        ("根太の曲げ", (jw * jL**2 / 8 + jP * jL / 4) / JOIST_Z / WOOD_FB),
        ("根太のたわみ", (5 * jw * jL**4 / 384 + jP * jL**3 / 48) / (WOOD_E * JOIST_I) / (jL / DEFL)),
        ("杭1本の荷重", R / CLAMP_KN),
        ("杭1本の荷重kN", R),
    ])


RATIOS = ["梁の曲げ", "梁のたわみ", "根太の曲げ", "根太のたわみ", "杭1本の荷重"]


@functools.lru_cache(maxsize=None)
def safe_layout(W, D, case=DESIGN_LOAD):
    """全部の比が 1 以下になる配置のうち、一番安いもの(列数, 行数)。"""
    best = None
    for rows in range(3, 7):
        for cols in range(3, 40):
            c = pipe_check(W, D, cols, rows, case)
            if all(c[k] <= 1 for k in RATIOS):
                t = priced(plan_pipe(W, D, pile="単管", cols=cols, rows=rows)["bom"])[1]
                if best is None or t < best[0]:
                    best = (t, cols, rows)
                break
    return best[1], best[2]


SAFE_W = 10.0


def check_row(label, W, D, cols, rows, case=DESIGN_LOAD):
    c = pipe_check(W, D, cols, rows, case)
    return (f"| {label} | {c['配置']} | {c['間隔']} | " + " | ".join(f"{c[k]:.2f}" for k in RATIOS[:-1])
            + f" | {c['杭1本の荷重kN']:.2f}kN({c['杭1本の荷重']:.2f}) |")


def pipe_safe_section():
    W0, D0 = plan_size("パイプ台")
    c = LOADS[DESIGN_LOAD]
    full = LOADS["床いっぱい"]
    head = ("| 案 | 杭の配置(列×行) | 杭の間隔(横×縦) | 梁の曲げ | 梁のたわみ | 根太の曲げ | 根太のたわみ "
            "| 杭1本の荷重 |")
    sep = "|---|---|---|---:|---:|---:|---:|---:|"
    L = ["", "## 強さの確かめ", "",
         "使い方に合わせて、次の荷重で杭の配置を決めた。構造は杭・単管の梁・根太・床板だけで、筋交いや二重の梁は使わない。",
         "",
         f"- 射手: 体重 {c['person'] * 100:.0f}kg の人が横に 1m おきに立つ。立つ位置は前の端から "
         f"{c['stand'][0]}〜{c['stand'][1]}m の間のどこでもよい。1 人の重さは根太 {PERSON_JOISTS} 本で受ける",
         f"- 荷物置き場: 前の端から {c['front']}m より後ろ。荷物は {c['luggage']}kN/m²(1m² に約 "
         f"{c['luggage'] * 100:.0f}kg)",
         f"- 床板と根太の重さ: 全面に {DEAD}kN/m²",
         "",
         "合格の条件は次の 3 つ。その中で一番安い配置にした。表の比は 1 以下で合格。", "",
         f"- 単管の梁と赤松の根太が、長期許容曲げ応力以内(単管 {STEEL_FB:.0f}N/mm²、赤松 {WOOD_FB:.1f}N/mm²)",
         f"- たわみがスパンの 1/{DEFL} 以内",
         f"- 杭1本の荷重が、自在クランプ1個で支えられる {CLAMP_KN}kN 以内",
         "",
         "梁は人が梁の真ん中に、杭は人が杭の真上に立つとして、一番厳しい所の値を出した。",
         "", head, sep,
         check_row(f"この設計({W0:g}m × {D0:g}m)", W0, D0, *safe_layout(W0, D0))]
    for W, D in [(SAFE_W, 2.0), (SAFE_W, 3.0)]:
        L.append(check_row(f"縦を変えた場合({W:g}m × {D:g}m)", W, D, *safe_layout(W, D)))
    L.append(check_row(f"元の案の杭 4×3({W0:g}m × {D0:g}m)", W0, D0, 4, 3))
    L.append(check_row(f"杭を 1.8m 間隔にした前の案({SPEC['W']:g}m × {SPEC['D']:g}m)",
                       SPEC["W"], SPEC["D"], None, None))
    fc, fr = safe_layout(W0, D0, "床いっぱい")
    ft = priced(plan_pipe(W0, D0, "単管", fc, fr)["bom"])[1]
    L += ["", f"### 床いっぱいに人が乗る場合({full['live']}kN/m²、住宅の床と同じ荷重)", "",
          f"後ろにも人が詰めて乗るなら、この設計では足りない。{W0:g}m × {D0:g}m で杭 {fc}×{fr}"
          f"(杭 {fc * fr} 本)が要り、合計は {yen(ft)}。", "", head, sep,
          check_row(f"この設計 {W0:g}m × {D0:g}m", W0, D0, *safe_layout(W0, D0), case="床いっぱい"),
          check_row(f"床いっぱい用の配置 {W0:g}m × {D0:g}m", W0, D0, fc, fr, case="床いっぱい")]
    L += ["", f"### 横 {SAFE_W:g}m で縦を変えた場合の合計", "",
          "| 縦 | 杭の配置 | 合計(単管を切る) | 合計(既製のパイプ杭) |", "|---|---|---:|---:|"]
    for D in (2.0, 2.5, 3.0):
        cols, rows = safe_layout(SAFE_W, D)
        t1 = priced(plan_pipe(SAFE_W, D, "単管", cols, rows)["bom"])[1]
        t2 = priced(plan_pipe(SAFE_W, D, "既製", cols, rows)["bom"])[1]
        L.append(f"| {D:g}m | {cols}×{rows}(杭 {cols * rows} 本) | {yen(t1)} | {yen(t2)} |")
    L += ["", "### 強さの注意", "",
          "- 梁と根太の曲げ・たわみは単純梁として計算した。実際は継ぎ目の無い所で連続梁になるので、もう少し余裕がある。",
          f"- クランプの許容 {CLAMP_KN}kN は一般的な値で、買う品の表示を確かめていない。表示が低ければ、"
          "梁の下にもう1個クランプを付けて受ける。",
          "- 杭1本の荷重を地面が支えられるかは、土によって違う。柔らかい土だと沈む。"
          "1 本試しに打ち込み、2 人くらい乗って沈まないか確かめる。",
          "- 荷物置き場に人が何人も入って立つと、この荷重を超える。後ろは荷物だけにする。"]
    return L


EXTRA_SECTIONS = {"パイプ台": pipe_safe_section}


VARIANTS = {
    "パイプ台": [("杭に既製のパイプ杭を使う", "単管を切る代わりに、既製のパイプ杭(1.5m)を買う",
                 lambda W, D: plan_pipe(W, D, "既製", *safe_layout(W, D)))],
}

PLAN_FUNCS = {"パイプ台": lambda W, D: plan_pipe(W, D, "単管", *safe_layout(W, D)), "排水作戦": plan_drain, "ブロック": plan_block, "砂": plan_sand}


def priced(bom):
    rows, total = [], 0
    for key, qty, note in bom:
        price, unit, _, src = PRICES[key]
        sub = price * qty
        total += sub
        rows.append((key, qty, unit, price, sub, note, src))
    return rows, total


# ---------------------------------------------------------------- 見積.md

def yen(v):
    return f"{v:,}円"


def bom_table(bom, W, D):
    rows, total = priced(bom)
    L = ["| 品目 | 数量 | 単価(税込) | 小計 | 内訳 |", "|---|---:|---:|---:|---|"]
    for key, qty, unit, price, sub, note, _ in rows:
        L.append(f"| {key} | {qty} {unit} | {yen(price)} | {yen(sub)} | {note} |")
    L.append(f"| 合計 | | | {yen(total)} | 1m² あたり {yen(round(total / (W * D)))} |")
    return L, total


def write_estimate(name):
    W, D = plan_size(name)
    p = PLAN_FUNCS[name](W, D)
    variants = VARIANTS.get(name, [])
    table, total = bom_table(p["bom"], W, D)
    L = [f"# {name} の見積", "", PLANS[name] + "。", "",
         f"![全体]({name}_全体.png)", ""]
    for suffix, _, _, cap in p["views"]:
        L += ([f"{suffix}: {cap}", ""] if cap else []) + [f"![{suffix}]({name}_{suffix}.png)", ""]
    if p.get("glass"):
        L += ["図の木(根太・床板)は半透明にして、下のパイプが見えるようにした。", ""]
    L += [f"## 部材(標準 {W:g}m × {D:g}m)", ""] + table
    L += ["", "## 量", "", "| 項目 | 量 |", "|---|---|"]
    L += [f"| {k} | {v} |" for k, v in p["q"].items()]
    for title, desc, fn in variants:
        v = fn(W, D)
        vt, vtotal = bom_table(v["bom"], W, D)
        diff = vtotal - total
        L += ["", f"## {title}場合(標準 {W:g}m × {D:g}m)", "", desc + "。"
              f"上の案より {yen(abs(diff))}{'安い' if diff < 0 else '高い'}。", ""] + vt
        L += ["", "| 項目 | 量 |", "|---|---|"] + [f"| {k} | {x} |" for k, x in v["q"].items()]
        L += ["", v["notes"][0]]
    if name in EXTRA_SECTIONS:
        L += EXTRA_SECTIONS[name]()
    head = ["サイズ", "面積", "合計(税込)", "1m² あたり"] + [f"{t}場合" for t, _, _ in variants]
    L += ["", "## サイズ別の合計", "", "| " + " | ".join(head) + " |", "|---|" + "---:|" * (len(head) - 1)]
    for w, d in SIZES:
        _, t = priced(PLAN_FUNCS[name](w, d)["bom"])
        cells = [f"{w:g}m × {d:g}m", f"{w * d:g} m²", yen(t), yen(round(t / (w * d)))]
        cells += [yen(priced(fn(w, d)["bom"])[1]) for _, _, fn in variants]
        L.append("| " + " | ".join(cells) + " |")
    L += ["", "## 前提と含まないもの", ""]
    L += [f"- {n}" for n in p["notes"]]
    L += ["- 工具・運搬・人手、作業中に出る予備の部材は含まない。",
          "- 写真の値札に無かった品目は仮の単価(一覧は 共通/見積まとめ.md)。共通/shooting.py の PRICES を直すと作り直せる。",
          "", "## 作り直し方", "", "```sh",
          f"blender -b --python 計画/{name}/build.py", "```", ""]
    (PLAN_DIR / name / "見積.md").write_text("\n".join(L), encoding="utf-8")
    return total


def write_summary():
    L = ["# 4 案の見積まとめ", "",
         "各案の詳細は、それぞれのフォルダの 見積.md。単価は税込で、"
         "共通/AmazonPhotos の値札(2026-11-07)と、写真に無いものの仮の単価から出した。", "",
         "| 案 | 中身 | " + " | ".join(f"{w:g}×{d:g}m" for w, d in SIZES) + " |",
         "|---|---|" + "---:|" * len(SIZES)]
    for name, desc in PLANS.items():
        cells = []
        for w, d in SIZES:
            _, t = priced(PLAN_FUNCS[name](w, d)["bom"])
            cells.append(yen(t))
        L.append(f"| [{name}](../計画/{name}/見積.md) | {desc} | " + " | ".join(cells) + " |")
        for title, vdesc, fn in VARIANTS.get(name, []):
            vcells = [yen(priced(fn(w, d)["bom"])[1]) for w, d in SIZES]
            L.append(f"| [{name}({title})](../計画/{name}/見積.md) | {vdesc} | " + " | ".join(vcells) + " |")
    L += ["", "## 仮の単価(写真に無かったもの。店で確かめる)", "", "| 品目 | 単価(税込) |", "|---|---:|"]
    for k, (price, unit, _, src) in PRICES.items():
        if src.startswith("仮"):
            L.append(f"| {k} | {yen(price)}/{unit} |")
    L += ["", "## 値札はあったが使っていない材料", "",
          "赤松 75×75・90×90、SPF 2×8・1×6、杉野地板、値札だけで品名が読めないクランプ類(218円・598円)。", ""]
    (COMMON / "見積まとめ.md").write_text("\n".join(L), encoding="utf-8")


# ---------------------------------------------------------------- Blender

COLORS = {
    "steel": (0.55, 0.57, 0.62), "pine": (0.80, 0.58, 0.32), "spf": (0.92, 0.80, 0.58),
    "treated": (0.50, 0.52, 0.30), "block": (0.62, 0.62, 0.62), "gravel": (0.35, 0.35, 0.37),
    "sand": (0.88, 0.76, 0.50), "sheet": (0.97, 0.97, 0.97), "pvc": (0.10, 0.10, 0.10),
    "soil": (0.42, 0.30, 0.20), "grass": (0.33, 0.55, 0.28), "line": (1.0, 1.0, 1.0),
    "person": (0.85, 0.28, 0.22), "text": (0.05, 0.05, 0.05), "clamp": (0.72, 0.62, 0.30),
}


def _material(bpy, key):
    m = bpy.data.materials.get(key)
    if m is None:
        m = bpy.data.materials.new(key)
        m.diffuse_color = (*COLORS[key], 1.0)
    return m


def _add_parts(bpy, parts, coll):
    groups = OrderedDict()
    for p in parts:
        g = groups.setdefault(p[1], {"mat": p[2], "v": [], "f": []})
        v, f = g["v"], g["f"]
        o = len(v)
        if p[0] == "box":
            (x0, y0, z0), (x1, y1, z1) = p[3], p[4]
            v += [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
                  (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
            f += [(o, o + 3, o + 2, o + 1), (o + 4, o + 5, o + 6, o + 7), (o, o + 1, o + 5, o + 4),
                  (o + 1, o + 2, o + 6, o + 5), (o + 2, o + 3, o + 7, o + 6), (o + 3, o, o + 4, o + 7)]
        elif p[0] == "cone":
            _, _, _, (px, py, pz), h, r = p
            n = 16
            v += [(px + r * math.cos(2 * math.pi * i / n), py + r * math.sin(2 * math.pi * i / n), pz)
                  for i in range(n)] + [(px, py, pz - h)]
            f += [(o + i, o + (i + 1) % n, o + n) for i in range(n)]
            f += [tuple(o + i for i in reversed(range(n)))]
        else:
            _, _, _, axis, (px, py, pz), length, r = p
            n = 16
            for end in (0, length):
                for i in range(n):
                    a, b = r * math.cos(2 * math.pi * i / n), r * math.sin(2 * math.pi * i / n)
                    v.append({"x": (px + end, py + a, pz + b), "y": (px + a, py + end, pz + b),
                              "z": (px + a, py + b, pz + end)}[axis])
            f += [(o + i, o + (i + 1) % n, o + n + (i + 1) % n, o + n + i) for i in range(n)]
            f += [tuple(o + i for i in reversed(range(n))), tuple(o + n + i for i in range(n))]
    for name, g in groups.items():
        me = bpy.data.meshes.new(name)
        me.from_pydata(g["v"], [], g["f"])
        me.update()
        me.materials.append(_material(bpy, g["mat"]))
        ob = bpy.data.objects.new(name, me)
        coll.objects.link(ob)


def _text(bpy, coll, body, loc, rot_z=0.0, size=0.3):
    cu = bpy.data.curves.new(body, "FONT")
    cu.body, cu.size, cu.align_x = body, size, "CENTER"
    cu.materials.append(_material(bpy, "text"))
    ob = bpy.data.objects.new(body, cu)
    ob.location, ob.rotation_euler = loc, (0, 0, rot_z)
    coll.objects.link(ob)


def _scene_setup(bpy):
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_WORKBENCH"
    sc.render.resolution_x, sc.render.resolution_y = 1600, 900
    sc.view_settings.view_transform = "Standard"
    sh = sc.display.shading
    sh.light, sh.color_type = "STUDIO", "MATERIAL"
    sh.show_shadows, sh.show_cavity = True, True
    sc.display.shadow_focus = 0.6
    if sc.world is None:
        sc.world = bpy.data.worlds.new("World")
    sc.world.color = (0.78, 0.84, 0.90)
    sc.unit_settings.system, sc.unit_settings.length_unit = "METRIC", "METERS"
    return sc


def _camera(bpy, sc, name, W, D, axis=None, value=0.0):
    """axis=None は斜め上からの全体。"x"・"y"・"z" はその向きの断面を正面から見る平行投影。"""
    cd = bpy.data.cameras.new(name)
    cam = bpy.data.objects.new(name, cd)
    sc.collection.objects.link(cam)
    res = (1600, 900)
    if axis is None:
        cd.lens = 35
        cam.location = (W / 2 - 0.30 * W, D / 2 - 1.05 * W - 1.0, 0.55 * W + 1.0)
        tgt = bpy.data.objects.new(name + "_注視点", None)
        tgt.location = (W / 2, D / 2, -0.2)
        sc.collection.objects.link(tgt)
        c = cam.constraints.new("TRACK_TO")
        c.target, c.track_axis, c.up_axis = tgt, "TRACK_NEGATIVE_Z", "UP_Y"
    elif axis == "x":
        cd.type, cd.ortho_scale = "ORTHO", D + 2.0
        cam.location = (value - 30.0, D / 2, -0.4)
        cam.rotation_euler = (math.pi / 2, 0, -math.pi / 2)
    elif axis == "y":
        cd.type, cd.ortho_scale = "ORTHO", W + 1.2
        cam.location = (W / 2, value - 30.0, -0.4)
        cam.rotation_euler = (math.pi / 2, 0, 0)
        res = (2400, 800)
    else:
        cd.type, cd.ortho_scale = "ORTHO", W + 1.2
        cam.location = (W / 2, D / 2, 30.0)
        cam.rotation_euler = (0, 0, 0)
        res = (2400, 900)
    cam["解像度"] = res
    return cam


def _render(bpy, sc, cam, path):
    sc.camera = cam
    sc.render.resolution_x, sc.render.resolution_y = cam["解像度"]
    sc.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)


SOIL_MARGIN = 1.3
CUT_BACK = {"soil": 0.03, "gravel": 0.02, "sand": 0.02, "sheet": 0.01}


def spec_parts(W, D):
    m = SOIL_MARGIN
    parts = [
        box("地盤", "soil", (-m, -m, -1.6), (W + m, D + m, 0)),
        box("エリア", "grass", (0, 0, 0), (W, D, 0.001)),
        box("人(1.7m)", "person", (-0.75, D / 2 - 0.2, 0), (-0.35, D / 2 + 0.2, 1.7)),
    ]
    lw = 0.03
    for p0, p1 in [((0, 0), (W, lw)), ((0, D - lw), (W, D)), ((0, 0), (lw, D)), ((W - lw, 0), (W, D))]:
        parts.append(box("エリア枠", "line", (*p0, 0.001), (*p1, 0.002)))
    return parts


def _section(bpy, sc, parts, name, axis, value):
    """axis の value で切り、見る側の手前を捨てて切り口を塞いだ写しを name のコレクションに作る。
    x・y は小さい側を捨てる。z は上を捨てる(上から見る)。"""
    import bmesh
    k = "xyz".index(axis)
    no = [0.0, 0.0, 0.0]
    no[k] = 1.0
    coll = bpy.data.collections.new(name)
    sc.collection.children.link(coll)
    _add_parts(bpy, parts, coll)
    for ob in list(coll.objects):
        bm = bmesh.new()
        bm.from_mesh(ob.data)
        geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
        # 中身を包む物ほど少し奥で切り、切り口が重なって隠れないようにする
        back = CUT_BACK.get(ob.data.materials[0].name, 0.0)
        co = [0.0, 0.0, 0.0]
        co[k] = value - back if axis == "z" else value + back
        res = bmesh.ops.bisect_plane(bm, geom=geom, plane_co=co, plane_no=no,
                                     clear_inner=axis != "z", clear_outer=axis == "z")
        cut_edges = [e for e in res["geom_cut"] if isinstance(e, bmesh.types.BMEdge)]
        if cut_edges:
            bmesh.ops.holes_fill(bm, edges=cut_edges, sides=0)
        bm.to_mesh(ob.data)
        bm.free()
        if not ob.data.polygons:
            bpy.data.objects.remove(ob)
    return coll


def _spec_texts(bpy, coll, W, D):
    _text(bpy, coll, f"W {W:g} m (7-10 m)", (W / 2, -0.7, 0.01))
    _text(bpy, coll, f"D {D:g} m (2-3 m)", (W + 1.05, D / 2, 0.01), rot_z=math.pi / 2)


GLASS_ALPHA = 0.22


def build_spec():
    import bpy
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = _scene_setup(bpy)
    W, D = SPEC["W"], SPEC["D"]
    coll = bpy.data.collections.new("仕様")
    sc.collection.children.link(coll)
    parts = spec_parts(W, D)
    _add_parts(bpy, parts, coll)
    _spec_texts(bpy, coll, W, D)
    cond = bpy.data.objects.new("条件", None)
    cond["W_m"], cond["D_m"] = W, D
    cond["W_範囲"], cond["D_範囲"] = "7-10 m", "2-3 m"
    coll.objects.link(cond)
    cam = _camera(bpy, sc, "全体", W, D)
    _render(bpy, sc, cam, COMMON / "仕様.png")
    bpy.ops.wm.save_as_mainfile(filepath=str(COMMON / "仕様.blend"))


def build(name):
    import bpy
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = _scene_setup(bpy)
    W, D = plan_size(name)
    if (W, D) == (SPEC["W"], SPEC["D"]):
        # 標準サイズの案は 共通/仕様.blend をリンクする
        spec_path = COMMON / "仕様.blend"
        if not spec_path.exists():
            raise SystemExit("共通/仕様.blend が無い。先に blender -b --python 共通/build_spec.py を流す")
        with bpy.data.libraries.load(str(spec_path), link=True, relative=True) as (src, dst):
            dst.collections = ["仕様"]
        spec = bpy.data.objects.new("仕様", None)
        spec.instance_type, spec.instance_collection = "COLLECTION", dst.collections[0]
        sc.collection.objects.link(spec)
    else:
        # 寸法の違う案は、同じ作りの地盤とエリアをその寸法で置く
        spec = bpy.data.collections.new(f"仕様({W:g}m×{D:g}m)")
        sc.collection.children.link(spec)
        _add_parts(bpy, spec_parts(W, D), spec)
        _spec_texts(bpy, spec, W, D)
    p = PLAN_FUNCS[name](W, D)
    coll = bpy.data.collections.new(name)
    sc.collection.children.link(coll)
    _add_parts(bpy, p["parts"], coll)
    if p.get("glass"):
        for key in ("pine", "spf", "treated"):
            m = _material(bpy, key)
            m.diffuse_color = (*COLORS[key], GLASS_ALPHA)
            m.surface_render_method = "BLENDED"
    folder = PLAN_DIR / name
    _render(bpy, sc, _camera(bpy, sc, "全体", W, D), folder / f"{name}_全体.png")
    spec.hide_render = coll.hide_render = True
    sc.display.shading.show_shadows = False      # 断面図は影を落とさない
    for suffix, axis, value, _ in p["views"]:
        sec = _section(bpy, sc, spec_parts(W, D) + p["parts"], suffix, axis, value)
        _render(bpy, sc, _camera(bpy, sc, suffix, W, D, axis, value), folder / f"{name}_{suffix}.png")
        sec.hide_render = sec.hide_viewport = True
    spec.hide_render = coll.hide_render = False
    sc.display.shading.show_shadows = True
    blend = folder / f"{name}.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(blend), relative_remap=True)
    write_estimate(name)
    write_summary()


if __name__ == "__main__":
    for n in PLANS:
        print(n, yen(write_estimate(n)))
    write_summary()
