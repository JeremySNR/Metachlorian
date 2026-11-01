"""The write allowlist shared with the bundled Lightroom connector.

These are develop-setting units, not guessed UI percentages. Lightroom's
runtime capabilities further restrict this list for each photo/version.
"""
from __future__ import annotations

import math
from typing import Any

from .errors import PhotoError

CONTROLS: dict[str, dict] = {}


def _numbers(names: str, lo: float, hi: float, family: str):
    for name in names.split():
        CONTROLS[name] = {'type': 'number', 'min': lo, 'max': hi, 'family': family}


_numbers('Exposure2012', -5, 5, 'tone')
_numbers('Contrast2012 Highlights2012 Shadows2012 Whites2012 Blacks2012 Texture Clarity2012 Dehaze Vibrance Saturation', -100, 100, 'tone')
_numbers('Temperature', 2000, 50000, 'white_balance')
_numbers('Tint', -150, 150, 'white_balance')
_numbers('ParametricShadows ParametricDarks ParametricLights ParametricHighlights', -100, 100, 'curves')
_numbers('ParametricShadowSplit ParametricMidtoneSplit ParametricHighlightSplit', 0, 100, 'curves')
for axis in ('Hue', 'Saturation', 'Luminance'):
    _numbers(' '.join(f'{axis}Adjustment{c}' for c in ('Red', 'Orange', 'Yellow', 'Green', 'Aqua', 'Blue', 'Purple', 'Magenta')), -100, 100, 'colour_mixer')
_numbers('SplitToningShadowHue SplitToningHighlightHue ColorGradeMidtoneHue ColorGradeGlobalHue', 0, 360, 'colour_grading')
_numbers('SplitToningShadowSaturation SplitToningHighlightSaturation ColorGradeMidtoneSat ColorGradeGlobalSat ColorGradeBlending', 0, 100, 'colour_grading')
_numbers('SplitToningBalance ColorGradeShadowLum ColorGradeMidtoneLum ColorGradeHighlightLum ColorGradeGlobalLum', -100, 100, 'colour_grading')
_numbers('Sharpness', 0, 150, 'detail')
_numbers('SharpenRadius', .5, 3, 'detail')
_numbers('SharpenDetail SharpenEdgeMasking LuminanceSmoothing LuminanceNoiseReductionDetail LuminanceNoiseReductionContrast ColorNoiseReduction ColorNoiseReductionDetail ColorNoiseReductionSmoothness', 0, 100, 'detail')
_numbers('LensManualDistortionAmount PerspectiveVertical PerspectiveHorizontal PerspectiveAspect', -100, 100, 'geometry')
_numbers('PerspectiveRotate', -10, 10, 'geometry')
_numbers('PerspectiveScale', 50, 150, 'geometry')
_numbers('PerspectiveUpright', 0, 5, 'geometry')
_numbers('CropTop CropLeft CropBottom CropRight', 0, 1, 'crop')
_numbers('CropAngle', -45, 45, 'crop')
_numbers('PostCropVignetteAmount', -100, 100, 'effects')
_numbers('PostCropVignetteRoundness', -100, 100, 'effects')
_numbers('PostCropVignetteMidpoint PostCropVignetteFeather PostCropVignetteHighlightContrast GrainAmount GrainSize GrainFrequency', 0, 100, 'effects')
_numbers('LensProfileEnable AutoLateralCA', 0, 1, 'optics')
for selector in ('LensProfileEnable', 'AutoLateralCA'):
    CONTROLS[selector] = {'type': 'enum', 'values': [0, 1], 'family': 'optics'}
CONTROLS['PerspectiveUpright'] = {'type': 'enum', 'values': [0, 1, 2, 3, 4], 'family': 'geometry'}
CONTROLS['ConvertToGrayscale'] = {'type': 'boolean', 'family': 'colour_mixer'}
CONTROLS['WhiteBalance'] = {'type': 'enum', 'values': ['As Shot', 'Auto', 'Custom', 'Daylight', 'Cloudy', 'Shade', 'Tungsten', 'Fluorescent', 'Flash'], 'family': 'white_balance'}
CONTROLS['CameraProfile'] = {'type': 'string', 'family': 'profiles'}
for curve in ('ToneCurvePV2012', 'ToneCurvePV2012Red', 'ToneCurvePV2012Green', 'ToneCurvePV2012Blue'):
    CONTROLS[curve] = {'type': 'curve', 'family': 'curves'}

LOCAL = {f'local_{name}': {'type': 'number', 'min': -100, 'max': 100} for name in
         'Contrast Highlights Shadows Whites Blacks Texture Clarity Dehaze Temperature Tint Saturation Sharpness LuminanceNoise'.split()}
LOCAL['local_Exposure'] = {'type': 'number', 'min': -4, 'max': 4}


def validate_values(values: dict, controls: dict) -> dict:
    if not isinstance(values, dict) or not values or len(values) > 128:
        raise PhotoError('Supply between 1 and 128 supported settings')
    for key, value in values.items():
        spec = controls.get(key)
        if spec is None:
            raise PhotoError(f'Unsupported Lightroom control: {key}')
        kind = spec['type']
        valid = False
        if kind == 'number':
            valid = type(value) in (float, int) and math.isfinite(value) and spec['min'] <= value <= spec['max']
        elif kind == 'boolean':
            valid = isinstance(value, bool)
        elif kind == 'enum':
            valid = type(value) in (str, int, float) and value in spec['values']
        elif kind == 'string':
            valid = isinstance(value, str) and 0 < len(value) <= 200 and not any(ord(c) < 32 for c in value)
        elif kind == 'curve':
            valid = isinstance(value, list) and 4 <= len(value) <= 64 and len(value) % 2 == 0
            valid = valid and all(type(n) in (int, float) and math.isfinite(n) and 0 <= n <= 255 for n in value)
            valid = valid and all(value[i] < value[i+2] for i in range(0, len(value)-2, 2))
        if not valid:
            raise PhotoError(f'Invalid value for {key}; expected {spec}')
    return values


def validate_operations(operations: list[dict], capabilities: dict, current: dict, creative: bool = False) -> list[dict]:
    if not isinstance(operations, list) or not 1 <= len(operations) <= 12:
        raise PhotoError('Supply 1 to 12 edit operations')
    controls = capabilities.get('controls', {})
    combined = dict(current)
    for operation in operations:
        if not isinstance(operation, dict):
            raise PhotoError('Each operation must be an object')
        op = operation.get('op')
        if op == 'settings':
            if set(operation) - {'op', 'values'}:
                raise PhotoError('Unknown settings operation field')
            values = validate_values(operation.get('values'), controls)
            if not creative and values.get('ConvertToGrayscale') is True:
                raise PhotoError('Black and white conversion needs a creative editing session')
            combined.update(values)
        elif op == 'mask':
            if set(operation) - {'op', 'type', 'adjustments'}:
                raise PhotoError('Unknown mask operation field')
            if operation.get('type') not in capabilities.get('mask_types', []):
                raise PhotoError('This mask type has not been verified on the connected Lightroom version')
            validate_values(operation.get('adjustments'), LOCAL)
        elif op == 'auto':
            if set(operation) - {'op', 'tone', 'white_balance'} or not capabilities.get('auto'):
                raise PhotoError('Unsupported Auto operation')
            if any(type(operation.get(k, False)) is not bool for k in ('tone', 'white_balance')) or not any(operation.get(k) for k in ('tone', 'white_balance')):
                raise PhotoError('Choose tone and/or white_balance as booleans')
        else:
            raise PhotoError(f'Unsupported operation: {op}')
    if combined.get('CropLeft', 0) >= combined.get('CropRight', 1) or combined.get('CropTop', 0) >= combined.get('CropBottom', 1):
        raise PhotoError('Crop must retain a positive area')
    splits = [combined.get(k, d) for k, d in zip(('ParametricShadowSplit', 'ParametricMidtoneSplit', 'ParametricHighlightSplit'), (25, 50, 75))]
    if not splits[0] < splits[1] < splits[2]:
        raise PhotoError('Parametric curve splits must be ordered')
    return operations


GUIDANCE = {
    'selection': 'Prioritise the requested person, moment and story. Compare bursts and retain varied moments. A laughing or sleeping child with closed eyes can be the best photograph. Aperture and ISO are context, not merit scores. Never infer fine focus or RAW recovery from a small preview.',
    'profiles': 'Start from the current edit. A profile changes the baseline colour/tone response; inspect skin and highlights before adjusting other controls. Use only a profile installed in Lightroom. Do not change the process version implicitly.',
    'white_balance': 'Correct unwanted casts while retaining the scene lighting. Avoid making sunset light neutral or forcing all skin tones to one colour. JPEG temperature uses relative units; RAW temperature is Kelvin. Check mixed lighting locally.',
    'tone': 'Establish subject brightness, then shape highlights, shadows, whites and blacks. Preserve important texture. Clipped preview pixels do not prove the RAW is unrecoverable. Texture, clarity and dehaze can exaggerate skin or create halos.',
    'curves': 'Use restrained tonal shaping; inspect shadow detail and highlight rolloff. RGB curves also change colour. Keep point x coordinates ordered and parametric splits distinct.',
    'colour_mixer': 'Separate hue, saturation and luminance intentions. Inspect skin, foliage and adjacent colours after each targeted change. Point Color is a distinct control and is unavailable unless explicitly exposed.',
    'colour_grading': 'Use shadow, midtone and highlight wheels for a coherent mood, then check blending and balance. Preserve believable skin and neutral references. A matched set should have consistent appearance, not identical slider values.',
    'crop': 'Preserve the subject, useful gesture and context. Consider horizon, distracting edges, breathing room and intended aspect ratio. Thirds are a suggestion. Coordinates refer to the oriented image; check the rendered result and remaining pixels.',
    'geometry': 'Correct distracting perspective and lens distortion without stretching faces. Inspect corners and crop loss. Geometric edits can invalidate masks; establish geometry before detailed local work.',
    'detail': 'Inspect native-resolution subject/eye regions before sharpening or denoising. Avoid halos and plastic skin. A Smart Preview cannot establish original-resolution focus. Denoise/Enhance, when available, precede dependent AI masks.',
    'optics': 'Use the correct installed lens profile and inspect architectural lines, faces at the frame edge and chromatic aberrations. Do not assume every lens needs the same correction.',
    'masks': 'Make selective tonal/colour improvements, preserving transitions and skin texture. Recompute subject/sky/background masks per image. Inspect spill, hair edges and halos; never copy image-specific AI data between photographs.',
    'effects': 'Vignetting should guide attention subtly. Grain and simulated lens blur are creative choices. Preserve natural skin texture and inspect the intended output size.',
    'advanced': 'People/range/gradient geometry, Point Color, healing, Generative Remove, reflection removal, lens blur, Enhance, HDR/panorama merges and HDR output are capability-gated. If unavailable, describe the Lightroom handoff; never simulate success or pass undocumented settings through.',
    'review': 'Compare a fresh Lightroom render with the baseline and the set reference. Look for skin shifts, clipped important detail, halos, mask edges, oversmoothing, awkward crops and inconsistency. Keep the original appearance when it is better. Finish only a visually reviewed revision.',
}

SOURCES = ['https://jkost.com/blog/lightroom-training-videos',
           'https://helpx.adobe.com/lightroom-classic/desktop/process-and-develop-photos/image-tone-color.html',
           'https://www.adobe.com/learn/lightroom-cc/web/lightroom-ai-order-of-operations']


def guidance(families: list[str] | None = None) -> dict[str, Any]:
    keys = families or list(GUIDANCE)
    return {'version': 1, 'default_style': 'natural', 'entries': {k: GUIDANCE[k] for k in keys if k in GUIDANCE}, 'sources': SOURCES}
