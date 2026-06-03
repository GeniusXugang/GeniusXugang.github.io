from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "static" / "assets" / "share"
URL = "https://geniusxugang.github.io/"


def bch_digit(data: int) -> int:
    d = data << 10
    g = 0b10100110111
    while d.bit_length() >= 11:
        d ^= g << (d.bit_length() - 11)
    return ((data << 10) | d) ^ 0b101010000010010


def mask_bit(mask: int, r: int, c: int) -> bool:
    if mask == 0:
        return (r + c) % 2 == 0
    raise ValueError("only mask 0 is implemented")


def make_qr_matrix(text: str) -> list[list[int]]:
    """Version 5-L QR for byte-mode payloads up to 106 bytes."""
    data = text.encode("iso-8859-1")
    if len(data) > 106:
        raise ValueError("payload too long for version 5-L")

    # Byte mode, character count, payload, terminator.
    bits = "0100" + f"{len(data):08b}" + "".join(f"{b:08b}" for b in data)
    bits += "0" * min(4, 864 - len(bits))
    while len(bits) % 8:
        bits += "0"
    pads = [0xEC, 0x11]
    i = 0
    while len(bits) < 864:
        bits += f"{pads[i % 2]:08b}"
        i += 1
    data_codewords = [int(bits[i : i + 8], 2) for i in range(0, 864, 8)]

    # Reed-Solomon over GF(256), version 5-L: 1 block, 108 data + 26 EC.
    exp = [0] * 512
    log = [0] * 256
    x = 1
    for i in range(255):
        exp[i] = x
        log[x] = i
        x <<= 1
        if x & 0x100:
            x ^= 0x11D
    for i in range(255, 512):
        exp[i] = exp[i - 255]

    def gf_mul(a: int, b: int) -> int:
        if a == 0 or b == 0:
            return 0
        return exp[log[a] + log[b]]

    gen = [1]
    for i in range(26):
        nxt = [0] * (len(gen) + 1)
        for j, coef in enumerate(gen):
            nxt[j] ^= gf_mul(coef, exp[i])
            nxt[j + 1] ^= coef
        gen = nxt

    rem = [0] * 26
    for cw in data_codewords:
        factor = cw ^ rem[0]
        rem = rem[1:] + [0]
        for j, coef in enumerate(gen[1:]):
            rem[j] ^= gf_mul(coef, factor)
    codewords = data_codewords + rem
    stream = "".join(f"{cw:08b}" for cw in codewords)

    n = 37
    m = [[-1] * n for _ in range(n)]

    def set_mod(r: int, c: int, v: int) -> None:
        if 0 <= r < n and 0 <= c < n:
            m[r][c] = v

    def finder(r: int, c: int) -> None:
        for rr in range(-1, 8):
            for cc in range(-1, 8):
                set_mod(r + rr, c + cc, 0)
        for rr in range(7):
            for cc in range(7):
                val = 1 if rr in (0, 6) or cc in (0, 6) or (2 <= rr <= 4 and 2 <= cc <= 4) else 0
                set_mod(r + rr, c + cc, val)

    finder(0, 0)
    finder(0, n - 7)
    finder(n - 7, 0)

    for i in range(8, n - 8):
        set_mod(6, i, i % 2 == 0)
        set_mod(i, 6, i % 2 == 0)

    # Alignment patterns for version 5.
    for ar, ac in [(6, 30), (30, 6), (30, 30)]:
        for rr in range(-2, 3):
            for cc in range(-2, 3):
                val = 1 if max(abs(rr), abs(cc)) in (0, 2) else 0
                set_mod(ar + rr, ac + cc, val)

    set_mod(4 * 5 + 9, 8, 1)

    # Reserve format areas.
    for i in range(9):
        if m[8][i] == -1:
            m[8][i] = 0
        if m[i][8] == -1:
            m[i][8] = 0
    for i in range(8):
        if m[8][n - 1 - i] == -1:
            m[8][n - 1 - i] = 0
        if m[n - 1 - i][8] == -1:
            m[n - 1 - i][8] = 0

    bit_i = 0
    upward = True
    c = n - 1
    while c > 0:
        if c == 6:
            c -= 1
        rows = range(n - 1, -1, -1) if upward else range(n)
        for r in rows:
            for dc in (0, 1):
                cc = c - dc
                if m[r][cc] == -1:
                    bit = int(stream[bit_i]) if bit_i < len(stream) else 0
                    bit_i += 1
                    m[r][cc] = bit ^ int(mask_bit(0, r, cc))
        upward = not upward
        c -= 2

    fmt = bch_digit(0b01_000)  # L error correction, mask 0.
    fmt_bits = [int(x) for x in f"{fmt:015b}"]
    coords1 = [(8, 0), (8, 1), (8, 2), (8, 3), (8, 4), (8, 5), (8, 7), (8, 8), (7, 8), (5, 8), (4, 8), (3, 8), (2, 8), (1, 8), (0, 8)]
    coords2 = [(n - 1, 8), (n - 2, 8), (n - 3, 8), (n - 4, 8), (n - 5, 8), (n - 6, 8), (n - 7, 8), (8, n - 8), (8, n - 7), (8, n - 6), (8, n - 5), (8, n - 4), (8, n - 3), (8, n - 2), (8, n - 1)]
    for (r, c), b in zip(coords1, fmt_bits):
        m[r][c] = b
    for (r, c), b in zip(coords2, fmt_bits):
        m[r][c] = b
    return m


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        "C:/Windows/Fonts/msyhbd.ttc" if bold else "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def draw_qr(url: str, scale: int = 8, border: int = 4) -> Image.Image:
    matrix = make_qr_matrix(url)
    n = len(matrix)
    img = Image.new("RGB", ((n + border * 2) * scale, (n + border * 2) * scale), "white")
    d = ImageDraw.Draw(img)
    for r, row in enumerate(matrix):
        for c, val in enumerate(row):
            if val:
                x0 = (c + border) * scale
                y0 = (r + border) * scale
                d.rectangle([x0, y0, x0 + scale - 1, y0 + scale - 1], fill="#18313d")
    return img


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    w, h = 1400, 780
    card = Image.new("RGB", (w, h), "#f5f7f8")
    d = ImageDraw.Draw(card)
    d.rectangle([0, 0, w, 170], fill="#18313d")
    d.rectangle([0, 170, 28, h], fill="#8f5f2f")

    photo_path = ROOT / "static" / "assets" / "img" / "zheng-xugang.jpg"
    photo = Image.open(photo_path).convert("RGB")
    photo.thumbnail((230, 230))
    px, py = 80, 230
    d.rounded_rectangle([px - 8, py - 8, px + 238, py + 238], radius=8, fill="white")
    card.paste(photo, (px, py))

    d.text((70, 58), "郑旭刚  |  Xugang Zheng", fill="white", font=font(50, True))
    d.text((72, 124), "东北财经大学经济学院 · 劳动经济学博士研究生", fill="#d7e6ec", font=font(26))

    left = 340
    y = 232
    d.text((left, y), "研究方向", fill="#1f4b5f", font=font(30, True))
    y += 52
    for line in ["城镇化 · 数字经济 · 劳动力市场发展", "农业转移人口市民化 · 青年就业 · 公共服务标准化"]:
        d.text((left, y), line, fill="#202428", font=font(30))
        y += 46

    y += 20
    d.text((left, y), "学术主页", fill="#1f4b5f", font=font(30, True))
    y += 50
    d.text((left, y), URL, fill="#202428", font=font(31))
    y += 55
    d.text((left, y), "邮箱：m18735120795@163.com", fill="#66717a", font=font(24))
    y += 36
    d.text((left, y), "　　　zhengxugang1999@163.com", fill="#66717a", font=font(24))

    standard_qr = OUT_DIR / "homepage-qr.png"
    if standard_qr.exists():
        qr = Image.open(standard_qr).convert("RGB").resize((330, 330))
    else:
        qr = draw_qr(URL, scale=8)
    qx, qy = 1045, 275
    d.rounded_rectangle([qx - 28, qy - 28, qx + qr.width + 28, qy + qr.height + 92], radius=8, fill="white")
    card.paste(qr, (qx, qy))
    d.text((qx + 18, qy + qr.height + 26), "扫码访问学术主页", fill="#1f4b5f", font=font(24, True))

    footer = "论文全文、简历与科研经历：geniusxugang.github.io"
    d.text((70, 705), footer, fill="#66717a", font=font(24))

    png = OUT_DIR / "xugang-zheng-academic-card.png"
    pdf = OUT_DIR / "xugang-zheng-academic-card.pdf"
    card.save(png)
    card.save(pdf, "PDF", resolution=160.0)
    print(png)
    print(pdf)


if __name__ == "__main__":
    main()
