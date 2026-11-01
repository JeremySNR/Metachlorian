import json
import pytest

from metachlorian.place_references import reference_key, reference_notes


def test_optional_references_change_caption_key(lib):
    from metachlorian.analysers.caption import CaptionAnalyser

    s, _ = lib
    a = CaptionAnalyser()
    before = a.input_key(s, 'hash', {})
    assert reference_notes(s) == ''
    path = s.data_dir / 'place-references.json'
    path.write_text(json.dumps({'entries': [{'name': 'New Show', 'period': '2026', 'source_url': 'https://example.com'}]}))
    assert 'New Show' in reference_notes(s)
    assert a.input_key(s, 'hash', {}) != before
    key = reference_key(s)
    path.write_text(json.dumps({'entries': [{'name': 'Another Show'}]}))
    assert reference_key(s) != key


@pytest.mark.parametrize('data', [[], {}, {'entries': [1]}, {'entries': [{'venue': 'No name'}]}, {'entries': [{}] * 41}])
def test_malformed_catalogue_is_reported(lib, data):
    s, _ = lib
    (s.data_dir / 'place-references.json').write_text(json.dumps(data))
    with pytest.raises(ValueError):
        reference_notes(s)
