"""Read originals in place, preserve framing, and normalise preview colour."""
from __future__ import annotations

import hashlib
import io
import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageCms, ImageOps

from .errors import PhotoError

RAW_EXTENSIONS = {'.dng', '.cr2', '.cr3', '.crw', '.nef', '.nrw', '.arw', '.srf', '.sr2', '.raf', '.orf', '.rw2', '.pef', '.srw', '.iiq', '.3fr', '.fff', '.rwl', '.mos', '.kdc', '.dcr', '.mef'}
PHOTO_EXTENSIONS = RAW_EXTENSIONS | {'.jpg', '.jpeg', '.heic', '.heif', '.tif', '.tiff', '.png', '.webp', '.avif'}


def fingerprint(path: Path) -> str:
    s = path.stat()
    return hashlib.sha256(f'{path.resolve()}:{s.st_size}:{s.st_mtime_ns}'.encode()).hexdigest()


def _colour(im: Image.Image) -> Image.Image:
    if im.mode.startswith('I;16') or im.mode == 'I':
        import numpy as np
        im = Image.fromarray(np.rint(np.clip(np.asarray(im, np.float32), 0, 65535)/257).astype(np.uint8))
    if im.mode == 'F':
        raise PhotoError('Floating-point/HDR originals require a Lightroom rendition')
    profile = im.info.get('icc_profile')
    if profile:
        try:
            im = ImageCms.profileToProfile(im, ImageCms.ImageCmsProfile(io.BytesIO(profile)), ImageCms.createProfile('sRGB'), outputMode='RGB')
        except (ValueError, OSError, ImageCms.PyCMSError) as exc:
            raise PhotoError('Embedded colour profile could not be converted to sRGB') from exc
    return im.convert('RGB')


def decode(path: Path, edge: int | None = 1600, *, native: bool = False) -> tuple[Image.Image, dict]:
    path = Path(path)
    if not path.is_file():
        raise PhotoError('Original is offline. Connect its drive or use a Lightroom Smart Preview.')
    source = 'original'
    if path.suffix.lower() in RAW_EXTENSIONS:
        try:
            import rawpy
        except ImportError as exc:
            raise PhotoError('Install the photos extra for RAW decoding, or connect Lightroom.') from exc
        with rawpy.imread(str(path)) as raw:
            im = None
            if not native:
                try:
                    thumb = raw.extract_thumb()
                    im = Image.open(io.BytesIO(thumb.data)) if thumb.format == rawpy.ThumbFormat.JPEG else Image.fromarray(thumb.data)
                    source = 'embedded_preview'
                    # Embedded thumbnails often omit the container's EXIF
                    # orientation. LibRaw postprocess applies this itself;
                    # extract_thumb does not. Do not rotate twice when present.
                    if not im.getexif().get(274):
                        rotation = {3: Image.Transpose.ROTATE_180, 5: Image.Transpose.ROTATE_90, 6: Image.Transpose.ROTATE_270}.get(raw.sizes.flip)
                        if rotation is not None:
                            im = im.transpose(rotation)
                except (rawpy.LibRawNoThumbnailError, rawpy.LibRawUnsupportedThumbnailError):
                    pass
            if im is None:
                im = Image.fromarray(raw.postprocess(use_camera_wb=True, half_size=not native, output_bps=8))
                source = 'raw_decode' if native else 'raw_half_size'
            im = ImageOps.exif_transpose(im)
            im.load()
            im = _colour(im)
    else:
        if path.suffix.lower() in {'.heic', '.heif'}:
            try:
                from pi_heif import register_heif_opener
                register_heif_opener()
            except ImportError as exc:
                raise PhotoError('Install the photos extra for HEIC decoding, or connect Lightroom.') from exc
        with Image.open(path) as original:
            im = _colour(ImageOps.exif_transpose(original))
    width, height = im.size
    if edge:
        im.thumbnail((edge, edge), Image.Resampling.LANCZOS)
    return im, {'source': source, 'source_width': width, 'source_height': height,
                'native_resolution': native and source in {'original', 'raw_decode'},
                'colour_space': 'sRGB', 'dynamic_range': 'SDR', 'raw_recovery_known': False}


def jpeg(im: Image.Image, edge: int | None = None) -> bytes:
    im = im.copy()
    if edge:
        im.thumbnail((edge, edge), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    im.convert('RGB').save(out, 'JPEG', quality=88, optimize=True)
    return out.getvalue()


def region(im: Image.Image, box: list[float]) -> Image.Image:
    import math
    if len(box) != 4 or any(not isinstance(x, (int, float)) or not math.isfinite(x) or not 0 <= x <= 1 for x in box):
        raise PhotoError('Region must be [left, top, right, bottom] in oriented, rendered-image coordinates from 0 to 1')
    l, t, r, b = box
    if l >= r or t >= b:
        raise PhotoError('Region has no area')
    w, h = im.size
    return im.crop((int(l*w), int(t*h), max(int(l*w)+1, int(r*w)), max(int(t*h)+1, int(b*h))))


def metadata(path: Path) -> dict:
    """Read only; never save metadata to the source or sidecar."""
    data: dict = {'filename': path.name, 'format': path.suffix[1:].upper()}
    exe = shutil.which('exiftool')
    if exe:
        proc = subprocess.run([exe, '-json', '-n', '-FileType', '-ImageWidth', '-ImageHeight', '-Orientation', '-Make', '-Model', '-LensModel',
                               '-DateTimeOriginal', '-OffsetTimeOriginal', '-FNumber', '-ExposureTime', '-ISO', '-FocalLength', '-GPSLatitude', '-GPSLongitude',
                               '-Subject', '-Title', '-Description', '-Rating', '--', str(path.resolve())], capture_output=True, timeout=30)
        if proc.returncode == 0:
            values = json.loads(proc.stdout)
            if values:
                data.update(values[0])
                data.pop('SourceFile', None)
    try:
        if path.suffix.lower() in {'.heic', '.heif'}:
            try:
                from pi_heif import register_heif_opener
                register_heif_opener()
            except ImportError:
                pass
        with Image.open(path) as im:
            exif = im.getexif()
            data.setdefault('ImageWidth', im.width)
            data.setdefault('ImageHeight', im.height)
            data.setdefault('Orientation', exif.get(274, 1))
            sub = exif.get_ifd(34665) if 34665 in exif else {}
            for tag, key in [(271, 'Make'), (272, 'Model'), (36867, 'DateTimeOriginal'), (36881, 'OffsetTimeOriginal'), (42036, 'LensModel'), (33437, 'FNumber'), (33434, 'ExposureTime'), (34855, 'ISO'), (37386, 'FocalLength')]:
                value = sub.get(tag, exif.get(tag))
                if value is not None:
                    data.setdefault(key, float(value) if hasattr(value, 'denominator') else value)
    except (OSError, ValueError, SyntaxError):
        pass  # Lightroom/ExifTool can still describe RAW files Pillow cannot open.
    capture = data.get('DateTimeOriginal')
    if capture:
        try:
            data['capture_time'] = datetime.strptime(str(capture)[:19], '%Y:%m:%d %H:%M:%S').isoformat()
            offset = data.get('OffsetTimeOriginal')
            if offset:
                data['capture_time'] += str(offset)
        except ValueError:
            data['capture_time'] = str(capture)
    data['capture_timezone_known'] = bool(data.get('OffsetTimeOriginal'))
    return data
