"""Photos sent to the assistant: re-encoded without metadata before they are
sent and stored (code_conventions.md §8.12, §11.2.10; study_conventions.md §7.1)."""

import io
from types import SimpleNamespace

import pytest
from PIL import Image

from DayBetes_food.domain.assistant import (
    ASSISTANT_PHOTO_MAX_SIDE_PX,
    ASSISTANT_PHOTO_PLACEHOLDER,
    ASSISTANT_PHOTO_STORED_TYPE,
    parse_assistant_photos,
    reencode_assistant_photo,
    turn_views,
)
from DayBetes_food.domain.constants import AssistantRole
from DayBetes_food.errors import ValidationError

# EXIF tags: GPS block and orientation.
_GPS_IFD = 0x8825
_ORIENTATION = 0x0112


def _jpeg(width, height, *, gps=False, orientation=None):
    image = Image.new("RGB", (width, height), (200, 120, 40))
    exif = Image.Exif()
    if gps:
        exif[_GPS_IFD] = {1: "N", 2: (40.0, 25.0, 0.0)}
    if orientation:
        exif[_ORIENTATION] = orientation
    output = io.BytesIO()
    image.save(output, format="JPEG", exif=exif.tobytes())
    return output.getvalue()


def _png_with_alpha():
    image = Image.new("RGBA", (40, 20), (0, 0, 0, 0))
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def test_the_gps_position_is_dropped():
    data = _jpeg(100, 80, gps=True)
    assert _GPS_IFD in Image.open(io.BytesIO(data)).getexif()

    result = Image.open(io.BytesIO(reencode_assistant_photo(data)))

    assert result.format == "JPEG"
    assert len(result.getexif()) == 0


def test_the_orientation_is_applied_before_dropping_it():
    # Orientation 6: the camera stored it sideways; upright, width and height swap.
    result = Image.open(io.BytesIO(reencode_assistant_photo(_jpeg(100, 40, orientation=6))))

    assert result.size == (40, 100)
    assert len(result.getexif()) == 0


def test_a_large_photo_is_reduced_to_the_longer_side_limit():
    result = Image.open(io.BytesIO(reencode_assistant_photo(_jpeg(3000, 1500))))

    assert max(result.size) == ASSISTANT_PHOTO_MAX_SIDE_PX
    assert result.size == (ASSISTANT_PHOTO_MAX_SIDE_PX, ASSISTANT_PHOTO_MAX_SIDE_PX // 2)


def test_a_small_photo_keeps_its_size():
    assert Image.open(io.BytesIO(reencode_assistant_photo(_jpeg(300, 200)))).size == (300, 200)


def test_a_transparent_png_becomes_a_jpeg_on_white():
    result = Image.open(io.BytesIO(reencode_assistant_photo(_png_with_alpha())))

    assert result.format == "JPEG"
    red, green, blue = result.convert("RGB").getpixel((10, 10))
    assert min(red, green, blue) > 240


def test_bytes_that_are_not_an_image_are_refused():
    with pytest.raises(ValidationError):
        reencode_assistant_photo(b"\xff\xd8\xff" + b"not a jpeg" * 10)


def test_parsed_photos_are_the_reencoded_jpeg():
    (photo,) = parse_assistant_photos([("image/png", _png_with_alpha())])

    assert photo.media_type == ASSISTANT_PHOTO_STORED_TYPE
    assert Image.open(io.BytesIO(photo.data)).format == "JPEG"


@pytest.mark.parametrize(
    "marker",
    [ASSISTANT_PHOTO_PLACEHOLDER, "[The user attached a photo here. Photos are not kept.]"],
)
def test_both_photo_markers_count_as_a_photo_and_are_not_shown_as_text(marker):
    message = SimpleNamespace(
        id=1,
        role=AssistantRole.USER,
        content=[{"type": "text", "text": marker}, {"type": "text", "text": "lentils"}],
    )

    (turn,) = turn_views([message])

    assert turn.photo_count == 1
    assert turn.user_text == "lentils"
