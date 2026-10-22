"""Generate the app's geometric icon with Pillow; no external artwork is used."""

from pathlib import Path

from PIL import Image, ImageDraw


def main():
    destination = Path(__file__).resolve().parents[1] / "custompresence/assets/icons"
    destination.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGBA", (1024, 1024))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((32, 32, 992, 992), radius=224, fill="#8c83ff")
    draw.polygon(((512, 208), (594, 430), (816, 512), (594, 594),
                  (512, 816), (430, 594), (208, 512), (430, 430)), fill="#1b1c23")
    draw.ellipse((720, 720, 984, 984), fill="#1b1c23")
    draw.ellipse((754, 754, 950, 950), fill="#7ee2b8")
    image.resize((512, 512), Image.Resampling.LANCZOS).save(destination / "app.png")
    image.save(destination / "app.ico", sizes=[(size, size) for size in (16, 20, 24, 32, 40, 48, 64, 128, 256)])
    image.save(destination / "app.icns")


if __name__ == "__main__":
    main()
