import math
from PIL import Image, ImageDraw, ImageFilter

def create_app_icon():
    # 4x Supersampling for ultra crispness (1024x1024 -> 256x256)
    size = 1024
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))

    # 1. Desktop Squircle Container
    # Margin 56px gives space for soft realistic drop shadow
    pad = 56
    x0, y0 = pad, pad
    x1, y1 = size - pad, size - pad
    radius = 200  # Modern continuous squircle curvature

    # Soft ambient drop shadow (Windows 11 / macOS desktop style)
    shadow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    s_draw = ImageDraw.Draw(shadow)
    # Layer 1: Broad soft shadow
    s_draw.rounded_rectangle([x0 + 4, y0 + 20, x1 + 4, y1 + 30], radius=radius, fill=(0, 0, 0, 90))
    shadow1 = shadow.filter(ImageFilter.GaussianBlur(30))
    # Layer 2: Tight darker shadow
    shadow2 = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    s2_draw = ImageDraw.Draw(shadow2)
    s2_draw.rounded_rectangle([x0 + 2, y0 + 10, x1 + 2, y1 + 16], radius=radius, fill=(0, 0, 0, 140))
    shadow2 = shadow2.filter(ImageFilter.GaussianBlur(12))

    img.alpha_composite(shadow1)
    img.alpha_composite(shadow2)

    # 2. Squircle Body with Deep Slate Gradient (Inspired by Android app #1B2633)
    bg = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    # Draw vertical rich gradient
    grad = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    g_draw = ImageDraw.Draw(grad)
    for y in range(y0, y1):
        t = (y - y0) / float(y1 - y0)
        # Deep premium slate navy gradient
        # Top: (30, 44, 60) -> Mid: (23, 34, 48) -> Bottom: (14, 22, 32)
        r = int(30 * (1 - t) + 14 * t)
        g = int(44 * (1 - t) + 22 * t)
        b = int(60 * (1 - t) + 32 * t)
        g_draw.line([(x0, y), (x1, y)], fill=(r, g, b, 255))

    mask = Image.new("L", (size, size), 0)
    m_draw = ImageDraw.Draw(mask)
    m_draw.rounded_rectangle([x0, y0, x1, y1], radius=radius, fill=255)
    bg.paste(grad, (0, 0), mask)

    # Outer border & Top rim highlight (gives physical glass / metallic feel)
    b_draw = ImageDraw.Draw(bg)
    b_draw.rounded_rectangle([x0, y0, x1, y1], radius=radius, outline=(60, 85, 115, 230), width=6)
    b_draw.rounded_rectangle([x0 + 3, y0 + 3, x1 - 3, y1 - 3], radius=radius - 3, outline=(255, 255, 255, 30), width=2)
    img.alpha_composite(bg)

    # 3. Quadcopter Drone Layer (Scaled from Android 108dp vector)
    # Center: (54, 54). Propeller centers: (40, 40), (68, 40), (40, 68), (68, 68).
    scale = (size - pad * 2) * 0.82 / 76.0
    cx, cy = size / 2.0, size / 2.0

    def t_pt(x, y):
        return cx + (x - 54.0) * scale, cy + (y - 54.0) * scale

    drone = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d_draw = ImageDraw.Draw(drone)

    # A. Drone Arms (Diagonal cross)
    p_tl = t_pt(40, 40)
    p_tr = t_pt(68, 40)
    p_bl = t_pt(40, 68)
    p_br = t_pt(68, 68)
    arm_w = int(4.5 * scale)

    # Soft drop shadow under arms & motors
    d_draw.line([p_tl, p_br], fill=(0, 0, 0, 160), width=arm_w + 10)
    d_draw.line([p_tr, p_bl], fill=(0, 0, 0, 160), width=arm_w + 10)

    # Carbon fiber arms (#C9CCD0 with metallic core)
    d_draw.line([p_tl, p_br], fill=(160, 165, 172, 255), width=arm_w)
    d_draw.line([p_tr, p_bl], fill=(160, 165, 172, 255), width=arm_w)
    d_draw.line([p_tl, p_br], fill=(215, 218, 222, 255), width=arm_w - 4)
    d_draw.line([p_tr, p_bl], fill=(215, 218, 222, 255), width=arm_w - 4)

    # B. Propeller Guard Rings
    centers = [p_tl, p_tr, p_bl, p_br]
    r_guard = 12.0 * scale
    ring_w = int(3.4 * scale)

    # Cyan motion discs under propellers
    for mx, my in centers:
        # Subtle cyan glow aura
        d_draw.ellipse([mx - r_guard - 8, my - r_guard - 8, mx + r_guard + 8, my + r_guard + 8],
                       fill=(14, 165, 233, 20), outline=(14, 165, 233, 60), width=ring_w + 6)
        # Transparent rotating propeller blur
        for angle in [20, 65, 110, 155]:
            rad = math.radians(angle)
            dx = math.cos(rad) * (r_guard - 4)
            dy = math.sin(rad) * (r_guard - 4)
            d_draw.line([(mx - dx, my - dy), (mx + dx, my + dy)], fill=(255, 255, 255, 40), width=int(1.8 * scale))

    # White Propeller Guard Rings (#FFFFFF) with micro bevel
    for mx, my in centers:
        ring_box = [mx - r_guard, my - r_guard, mx + r_guard, my + r_guard]
        # Ring shadow
        d_draw.ellipse([mx - r_guard, my - r_guard + 4, mx + r_guard, my + r_guard + 4], outline=(0, 0, 0, 120), width=ring_w)
        # Main white ring
        d_draw.ellipse(ring_box, outline=(255, 255, 255, 255), width=ring_w)
        # Inner subtle ring highlight
        d_draw.ellipse([mx - r_guard + 2, my - r_guard + 2, mx + r_guard - 2, my + r_guard - 2], outline=(230, 245, 255, 180), width=1)

        # Motor hub
        motor_r = 3.6 * scale
        d_draw.ellipse([mx - motor_r, my - motor_r, mx + motor_r, my + motor_r], fill=(24, 32, 44, 255), outline=(201, 204, 208, 255), width=2)
        d_draw.ellipse([mx - motor_r * 0.4, my - motor_r * 0.4, mx + motor_r * 0.4, my + motor_r * 0.4], fill=(201, 204, 208, 255))

    # C. Center Body: RoboMaster TT Orange Module (#E4572E)
    # Position: x in [45, 63], y in [47, 61]
    bx0, by0 = t_pt(45, 47)
    bx1, by1 = t_pt(63, 61)
    body_r = 3.2 * scale

    # Module shadow
    d_draw.rounded_rectangle([bx0, by0 + 8, bx1, by1 + 12], radius=body_r, fill=(0, 0, 0, 180))

    # Module background with vibrant RoboMaster TT orange gradient
    d_draw.rounded_rectangle([bx0, by0, bx1, by1], radius=body_r, fill=(235, 87, 46, 255), outline=(255, 130, 85, 255), width=int(1.6 * scale))

    # Front camera / sensor notch
    cam_w = 4.0 * scale
    cam_h = 2.0 * scale
    d_draw.rounded_rectangle([(cx - cam_w, by0 - cam_h * 0.5), (cx + cam_w, by0 + cam_h * 0.5)], radius=1.0 * scale, fill=(18, 24, 32, 255))

    # D. "TT" White Lettering (RoboMaster TT signature logo)
    tt_w = int(2.5 * scale)

    # First T:
    t1_h_a = t_pt(47.2, 51.5)
    t1_h_b = t_pt(52.8, 51.5)
    t1_v_a = t_pt(50.0, 51.5)
    t1_v_b = t_pt(50.0, 58.0)
    d_draw.line([t1_h_a, t1_h_b], fill=(255, 255, 255, 255), width=tt_w)
    d_draw.line([t1_v_a, t1_v_b], fill=(255, 255, 255, 255), width=tt_w)

    # Second T:
    t2_h_a = t_pt(55.2, 51.5)
    t2_h_b = t_pt(60.8, 51.5)
    t2_v_a = t_pt(58.0, 51.5)
    t2_v_b = t_pt(58.0, 58.0)
    d_draw.line([t2_h_a, t2_h_b], fill=(255, 255, 255, 255), width=tt_w)
    d_draw.line([t2_v_a, t2_v_b], fill=(255, 255, 255, 255), width=tt_w)

    # E. Green Status LED on Top
    led_x, led_y = t_pt(54.0, 48.2)
    led_r = 1.6 * scale
    d_draw.ellipse([led_x - led_r * 2.2, led_y - led_r * 2.2, led_x + led_r * 2.2, led_y + led_r * 2.2], fill=(16, 185, 129, 90))
    d_draw.ellipse([led_x - led_r, led_y - led_r, led_x + led_r, led_y + led_r], fill=(52, 211, 153, 255))

    img.alpha_composite(drone)

    # 4. Generate multi-resolution icons
    # Targets:
    # desktop/src/app.ico
    # desktop/resource/icons/app.ico
    # desktop/resource/icons/app.png (256x256)
    # dist/RoboMasterTT/resource/icons/app.ico
    # dist/RoboMasterTT/resource/icons/app.png

    png_256 = img.resize((256, 256), Image.Resampling.LANCZOS)
    png_256.save(r"desktop/resource/icons/app.png", "PNG")

    # ICO sizes for Windows Desktop, Explorer & Taskbar:
    ico_sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]
    ico_images = [img.resize(s, Image.Resampling.LANCZOS) for s in ico_sizes]

    # Save to desktop/src/app.ico
    ico_images[0].save(r"desktop/src/app.ico", format="ICO", sizes=ico_sizes, append_images=ico_images[1:])
    # Save to desktop/resource/icons/app.ico
    ico_images[0].save(r"desktop/resource/icons/app.ico", format="ICO", sizes=ico_sizes, append_images=ico_images[1:])

    print("Desktop mobile-app style icons generated successfully!")

if __name__ == "__main__":
    create_app_icon()
