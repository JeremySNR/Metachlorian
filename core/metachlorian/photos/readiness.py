"""Small, actionable readiness facts shared by the app and MCP clients."""
from functools import lru_cache
from importlib import import_module
from pathlib import Path

CONNECTOR_VERSION = '0.2.0'


@lru_cache(maxsize=1)
def decoders() -> dict:
    result = {}
    for name, module in [('raw', 'rawpy'), ('heic', 'pi_heif')]:
        try:
            import_module(module)
            result[name] = {'available': True}
        except (ImportError, OSError) as exc:
            result[name] = {'available': False, 'reason': str(exc)[:200]}
    return result


def connector_files(data_dir: Path) -> dict:
    source = Path(__file__).parent / 'lightroom' / 'MetachlorianPhotos.lrplugin'
    path = data_dir / 'lightroom' / source.name
    installed = path / 'Info.lua'
    return {'path': str(path), 'files_copied': installed.is_file(),
            'files_current': installed.is_file() and installed.read_bytes() == (source / 'Info.lua').read_bytes(),
            'bundled_version': CONNECTOR_VERSION}


def connection_details(connection: dict, can_edit: bool) -> dict:
    state = dict(connection)
    caps = state.get('capabilities', {})
    supported = bool(caps.get('editing'))
    state['editing_supported'] = supported
    state['can_edit'] = bool(state.get('connected') and supported and can_edit)
    state['update_available'] = bool(state.get('connected') and state.get('connector_version') != CONNECTOR_VERSION)
    if state.get('busy'):
        state['label'] = 'Lightroom is working'
    elif state.get('connected'):
        state['label'] = 'Lightroom connected'
        if state['update_available']:
            state['message'] = 'Lightroom answered, but its connector needs updating for folder matching and Lightroom 14.2. Copy the current files, then reload the plug-in in Lightroom.'
        elif not supported:
            state['message'] = caps.get('reason') or 'This Lightroom version can supply previews, but editing is unavailable. See the compatibility details.'
        elif not can_edit:
            state['message'] = 'The connection works. This account or agent token needs photos:edit before it can create edited virtual copies.'
        else:
            state['message'] = 'Lightroom answered successfully. You can retrieve catalogue previews and create edits on virtual copies.'
    else:
        state['label'] = 'Connect Lightroom'
        state.setdefault('message', 'Open Lightroom Classic and enable the Metachlorian Photos connector, then check the connection.')
    return state
