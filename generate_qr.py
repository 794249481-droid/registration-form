Warning: fs was declared with const; use let for reassignable variables.
#!/usr/bin/env python3
"""生成科技感/AI风格报名二维码。

用法:
  python generate_qr.py                          # 交互式输入 URL
  python generate_qr.py "https://example.com"    # 命令行传入 URL
  python generate_qr.py "https://..." dark       # 深色科技风
  python generate_qr.py "https://..." light      # 浅色科技风 (默认)
"""

import sys
import os
import qrcode
from qrcode.image.styledpil import StyledPilImage
from qrcode.image.styles.moduledrawers import RoundedModuleDrawer, GappedSquareModuleDrawer, CircleModuleDrawer
from qrcode.image.styles.colormasks import RadialGradiantColorMask, SolidFillColorMask, SquareGradiantColorMask

OUTPUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "qrcode.png")


def generate_qr(url, output_path=OUTPUT, style="light"):
    qr = qrcode.QRCode(
        version=3,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=12,
        border=2,
    )
    qr.add_data(url)
    qr.make(fit=True)

    if style == "dark":
        # 深色科技风: 暗底 + 蓝紫渐变亮色模块
        img = qr.make_image(
            image_factory=StyledPilImage,
            module_drawer=RoundedModuleDrawer(),
            color_mask=RadialGradiantColorMask(
                center_color=(0, 210, 255),    # 霓虹青
                edge_color=(120, 80, 255),      # 科技紫
                back_color=(18, 22, 40),        # 深空蓝黑
            ),
        )
    else:
        # 浅色科技风: 白底 + 蓝紫渐变模块 + 间隙方块 (电路板感)
        img = qr.make_image(
            image_factory=StyledPilImage,
            module_drawer=GappedSquareModuleDrawer(),
            color_mask=RadialGradiantColorMask(
                center_color=(30, 60, 180),      # 深蓝
                edge_color=(100, 50, 220),       # 紫蓝
                back_color=(255, 255, 255),      # 纯白底
            ),
        )

    img = img.convert("RGB")
    img.save(output_path, "PNG")
    size = img.size
    print(f"二维码已生成 [{style}]: {output_path}")
    print(f"尺寸: {size[0]}x{size[1]}px (300 DPI 印刷约 {size[0]/300*2.54:.1f}cm)")
    return output_path


if __name__ == "__main__":
    args = sys.argv[1:]
    url = None
    style = "light"

    for a in args:
        if a.startswith("http"):
            url = a
        elif a in ("dark", "light"):
            style = a

    if not url:
        url = input("请输入表单访问地址 (如 https://example.com): ").strip()

    if not url.startswith("http"):
        print("错误: URL 必须以 http:// 或 https:// 开头")
        sys.exit(1)

    generate_qr(url, style=style)
